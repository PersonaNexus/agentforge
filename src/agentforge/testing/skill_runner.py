"""Execute skills against LLM with test scenarios."""
from __future__ import annotations
import time
from agentforge.testing.models import TestExecution, TestScenario


class SkillRunner:
    """Run test scenarios against a skill using an LLM client."""

    def run_scenarios(
        self,
        skill_md: str,
        scenarios: list[TestScenario],
        llm_client: object,
    ) -> list[TestExecution]:
        results = []
        for scenario in scenarios:
            execution = self._run_single(skill_md, scenario, llm_client)
            results.append(execution)
        return results

    def _run_single(
        self,
        skill_md: str,
        scenario: TestScenario,
        llm_client: object,
    ) -> TestExecution:
        system = f"Follow this skill specification exactly:\n\n{skill_md}"

        start = time.monotonic()
        try:
            response = llm_client.generate(
                prompt=scenario.input_prompt,
                system=system,
                max_tokens=2048,
            )
        except AttributeError:
            # LLMClient doesn't have generate() yet — fall back to extract_structured
            # with a simple wrapper model
            response = self._fallback_generate(llm_client, scenario.input_prompt, system)

        elapsed_ms = (time.monotonic() - start) * 1000

        return TestExecution(
            scenario=scenario,
            response=response,
            latency_ms=elapsed_ms,
        )

    def _fallback_generate(self, llm_client: object, prompt: str, system: str) -> str:
        """Fallback: use the raw provider client for plain text generation."""
        if hasattr(llm_client, '_anthropic_client') and llm_client._anthropic_client:
            resp = llm_client._anthropic_client.messages.create(
                model=llm_client.model,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
        elif hasattr(llm_client, '_openai_client') and llm_client._openai_client:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]
            resp = llm_client._openai_client.chat.completions.create(
                model=llm_client.model,
                max_tokens=2048,
                messages=messages,
            )
            return resp.choices[0].message.content or ""
        return "[Error: No LLM client available for text generation]"
