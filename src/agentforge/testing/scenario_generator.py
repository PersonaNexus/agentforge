"""Generate test scenarios from extraction results."""
from __future__ import annotations
from agentforge.models.extracted_skills import ExtractionResult, MethodologyExtraction
from agentforge.testing.models import TestScenario


class ScenarioGenerator:
    """Generate test scenarios from extraction and methodology data."""

    def __init__(self, max_scenarios: int = 10):
        self.max_scenarios = max_scenarios

    def generate(
        self,
        extraction: ExtractionResult,
        methodology: MethodologyExtraction | None = None,
    ) -> list[TestScenario]:
        scenarios: list[TestScenario] = []

        # 1. Trigger-based scenarios from methodology
        if methodology:
            scenarios.extend(self._from_triggers(methodology))

        # 2. Responsibility-based scenarios
        scenarios.extend(self._from_responsibilities(extraction))

        # 3. Edge case scenarios
        scenarios.extend(self._edge_cases(extraction))

        return scenarios[:self.max_scenarios]

    def _from_triggers(self, methodology: MethodologyExtraction) -> list[TestScenario]:
        scenarios = []
        for mapping in methodology.trigger_mappings:
            scenario = TestScenario(
                name=f"trigger: {mapping.trigger_pattern[:50]}",
                input_prompt=self._expand_trigger(mapping.trigger_pattern),
                expected_technique=mapping.technique,
                expected_format=mapping.output_format,
                source="trigger",
            )
            scenarios.append(scenario)

        for heuristic in methodology.heuristics:
            scenario = TestScenario(
                name=f"heuristic: {heuristic.trigger[:50]}",
                input_prompt=self._expand_trigger(heuristic.trigger),
                expected_technique=heuristic.procedure[:200],
                source="trigger",
            )
            scenarios.append(scenario)

        # Add quality criteria to all trigger scenarios
        if methodology.quality_criteria:
            criteria = [c.criterion for c in methodology.quality_criteria]
            for s in scenarios:
                s.quality_criteria = criteria

        return scenarios

    def _from_responsibilities(self, extraction: ExtractionResult) -> list[TestScenario]:
        scenarios = []
        criteria = []
        if extraction.suggested_traits.defined_traits():
            # Use traits to inform quality expectations
            traits = extraction.suggested_traits.defined_traits()
            if traits.get("rigor", 0) > 0.6:
                criteria.append("Response should be thorough and detailed")
            if traits.get("directness", 0) > 0.6:
                criteria.append("Response should be clear and actionable")

        for resp in extraction.responsibilities[:5]:
            scenario = TestScenario(
                name=f"responsibility: {resp[:50]}",
                input_prompt=f"I need help with the following: {resp}. Please provide a detailed approach.",
                quality_criteria=criteria,
                source="responsibility",
            )
            scenarios.append(scenario)
        return scenarios

    def _edge_cases(self, extraction: ExtractionResult) -> list[TestScenario]:
        scenarios = []
        # Out-of-scope request
        domain = extraction.role.domain
        scenarios.append(TestScenario(
            name="edge: out-of-scope request",
            input_prompt=(
                f"I know you specialize in {domain}, but can you help me write "
                "a poem about my cat? It's for a birthday card."
            ),
            quality_criteria=["Should acknowledge this is outside scope or redirect appropriately"],
            source="edge_case",
        ))

        # Ambiguous request
        if extraction.role.scope_primary:
            scope = extraction.role.scope_primary[0]
            scenarios.append(TestScenario(
                name="edge: ambiguous request",
                input_prompt="Can you help me with something?",
                quality_criteria=["Should ask for clarification before proceeding"],
                source="edge_case",
            ))

        return scenarios

    def _expand_trigger(self, trigger_pattern: str) -> str:
        """Expand a trigger pattern into a realistic user request."""
        # Strip common prefixes
        text = trigger_pattern
        for prefix in ["When asked to ", "When ", "If ", "For "]:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return f"Can you help me {text.rstrip('.')}? Please provide a thorough response."
