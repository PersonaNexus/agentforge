# Feature Roadmap: Next Three Capabilities

Three high-leverage features that extend AgentSkillFactory from a one-shot forge into a closed-loop agent development platform.

---

## Feature 1: Skill Testing & Validation

**Problem:** You forge a skill and hope it works. There's no feedback loop — no way to know if the skill actually produces quality output before deploying it.

**Solution:** A test harness that generates scenarios from the extraction data, runs the skill against Claude, and scores the output against the skill's own quality criteria.

### Architecture

**New files:**
```
src/agentforge/testing/
    __init__.py
    scenario_generator.py   # Generate test cases from extraction
    skill_runner.py          # Execute skill against LLM with test input
    evaluator.py             # Score output against quality criteria
    models.py                # TestScenario, TestResult, TestReport
```

**New pipeline stage:** `TestStage` (optional, after Generate)
```python
class TestStage(PipelineStage):
    name = "test"
    def run(self, context):
        scenarios = ScenarioGenerator().generate(
            extraction=context["extraction"],
            methodology=context["methodology"],
        )
        results = SkillRunner().run_scenarios(
            skill_md=context["skill_folder"].skill_md,
            scenarios=scenarios,
            llm_client=context["llm_client"],
        )
        report = Evaluator().evaluate(
            results=results,
            quality_criteria=context["methodology"].quality_criteria,
        )
        context["test_report"] = report
        return context
```

### Scenario Generation

`ScenarioGenerator` builds test cases from three sources:

**1. Trigger-based scenarios** (from `methodology.trigger_mappings`):
Each trigger mapping already defines "when the user asks X, respond with technique Y in format Z." These are natural test cases:
```python
@dataclass
class TestScenario:
    name: str                    # e.g. "trigger: code review request"
    input_prompt: str            # Synthetic user request matching trigger
    expected_technique: str      # From trigger_mapping.technique
    expected_format: str | None  # From trigger_mapping.output_format
    quality_criteria: list[str]  # Applicable criteria for this scenario
    source: str                  # "trigger" | "responsibility" | "edge_case"
```

For each `TriggerTechniqueMapping`, generate a concrete user request that matches the trigger pattern. Use the LLM to expand the pattern into a realistic request:
```
Trigger: "code review request"
→ Input: "Can you review this pull request? It adds a new caching layer to our API. Here's the diff: [synthetic diff]"
```

**2. Responsibility-based scenarios** (from `extraction.responsibilities`):
Each responsibility implies a task the agent should handle. Generate one scenario per top-5 responsibility:
```
Responsibility: "Design and maintain data pipelines"
→ Input: "We need a new pipeline to ingest clickstream data from Kafka into our Snowflake warehouse. What's your approach?"
```

**3. Edge-case scenarios** (generated):
- Out-of-scope request (should be deflected per guardrails)
- Ambiguous request (should ask for clarification)
- Multi-step request requiring workflow orchestration

Target: 5–10 scenarios per skill (configurable).

### Skill Runner

`SkillRunner` executes each scenario against the forged skill:

```python
class SkillRunner:
    def run_scenarios(
        self,
        skill_md: str,
        scenarios: list[TestScenario],
        llm_client: LLMClient,
    ) -> list[TestExecution]:
        results = []
        for scenario in scenarios:
            # Build system prompt from SKILL.md (same as Claude Code would)
            system = f"Follow this skill specification:\n\n{skill_md}"

            response = llm_client.generate(
                system=system,
                prompt=scenario.input_prompt,
                max_tokens=2048,
            )

            results.append(TestExecution(
                scenario=scenario,
                response=response,
                tokens_used=token_count,
                latency_ms=elapsed,
            ))
        return results
```

Note: This requires adding a plain `generate()` method to `LLMClient` (currently only has `extract_structured()`). Simple addition — just call the API without tool/function calling.

### Evaluator

`Evaluator` scores each execution against quality criteria:

```python
class Evaluator:
    def evaluate(
        self,
        results: list[TestExecution],
        quality_criteria: list[QualityCriterion],
    ) -> TestReport:
        scored = []
        for execution in results:
            # LLM-as-judge: score the response against criteria
            scores = self._judge(execution, quality_criteria)
            scored.append(ScoredExecution(
                execution=execution,
                criterion_scores=scores,  # {criterion: 0-1 score + rationale}
                overall_score=mean(scores.values()),
            ))

        return TestReport(
            scored_executions=scored,
            overall_score=mean(e.overall_score for e in scored),
            weakest_criteria=self._find_weakest(scored),
            recommendations=self._generate_recommendations(scored),
        )
```

**Scoring rubric** (LLM-as-judge prompt):
```
Given this quality criterion: "{criterion}"
And this agent response to the prompt "{input}":

{response}

Score 0.0-1.0 on how well the response meets this criterion.
- 0.0: Completely fails
- 0.5: Partially meets, significant gaps
- 1.0: Fully satisfies

Return: score (float), rationale (1 sentence)
```

### Output: TestReport

```python
@dataclass
class TestReport:
    scored_executions: list[ScoredExecution]
    overall_score: float          # 0-1, mean across all scenarios
    weakest_criteria: list[str]   # Criteria that scored lowest
    recommendations: list[str]    # "Add more detail to output templates for X"
    pass_rate: float              # % of scenarios scoring > 0.7

    def summary(self) -> str:
        # "7/10 scenarios passed (70%). Weakest: output formatting (0.4)"
```

### Integration Points

**CLI:**
```bash
agentforge test job.txt                      # Forge + test
agentforge test --skill .claude/skills/x/    # Test existing skill
agentforge forge job.txt --test              # Auto-test after forge
```

**Web UI:**
- New "Test" button on forge results page (step 4)
- Shows scenario cards with pass/fail, expand to see response + scores
- Overall score badge on skill card
- Link weakest criteria back to Review & Refine (feed directly into edits)

**API:**
```
POST /api/test/{job_id}              → Run tests against forged skill
POST /api/test/skill                 → Upload SKILL.md + run tests
GET  /api/test/{job_id}/report       → Get test report
```

### Feedback Loop

The key value: test results feed back into refinement.

```
Forge → Test → Review gaps → Refine → Re-test → Ship
```

If a scenario fails because of weak output templates, the `recommendations` field tells the user exactly what to add. The Review & Refine UI can pre-populate edit prompts with test failure context.

### Cost Estimate

Per skill test run:
- Scenario generation: 1 LLM call (~500 tokens)
- Skill execution: 5-10 calls (~2K tokens each = 10-20K tokens)
- Evaluation: 5-10 judge calls (~300 tokens each = 1.5-3K tokens)
- **Total: ~15-25K tokens per test run (~$0.05-0.10 with Sonnet)**

---

## Feature 2: Non-JD Input Sources

**Problem:** Job descriptions are thin signals. They describe what a role *should* do, not how experts *actually* do it. The methodology layer suffers — heuristics are generic, templates are vague, trigger mappings are sparse. Users can manually add examples in the "Enhance" section, but that's friction-heavy.

**Solution:** Ingest rich operational sources (Slack exports, git logs, runbooks, meeting notes) alongside the JD to automatically build thick methodology layers.

### Architecture

**New files:**
```
src/agentforge/ingestion/
    slack.py           # Parse Slack JSON exports
    git_log.py         # Parse git log output
    runbook.py         # Parse runbook/SOP documents (markdown/confluence)
    meeting_notes.py   # Parse meeting transcripts
    multi_source.py    # Orchestrate multi-source ingestion
```

**New pipeline stage:** `MultiIngestStage` (replaces or wraps `IngestStage`)

```python
class MultiIngestStage(PipelineStage):
    name = "multi_ingest"

    def run(self, context):
        jd = ingest_file(context["input_path"])
        context["jd"] = jd

        supplementary = []
        for source in context.get("supplementary_sources", []):
            parsed = self._ingest_source(source)
            supplementary.append(parsed)

        context["supplementary_sources_parsed"] = supplementary
        return context
```

### Source Parsers

#### Slack Export Parser (`slack.py`)

Input: Slack JSON export (channel export ZIP or individual JSON files).

```python
class SlackParser:
    def parse(
        self,
        path: Path,                    # ZIP or directory
        channel_filter: list[str] | None = None,
        date_range: tuple[date, date] | None = None,
        user_filter: list[str] | None = None,  # Focus on specific users
    ) -> SlackCorpus:
        ...

@dataclass
class SlackCorpus:
    messages: list[SlackMessage]
    threads: list[SlackThread]        # Threaded conversations
    decision_points: list[str]        # Messages with decisions/conclusions
    recurring_patterns: list[str]     # Frequently discussed topics
```

**What we extract for methodology:**
- **Decision patterns:** Messages containing "let's go with", "decided to", "the approach is" → become Heuristics
- **Request/response patterns:** Question → answer threads → become TriggerMappings
- **Common formats:** Shared templates, checklists, status updates → become OutputTemplates
- **Escalation signals:** "looping in", "need help with", "blocked on" → become scope boundaries

#### Git Log Parser (`git_log.py`)

Input: Output of `git log --format` or direct repo access.

```python
class GitLogParser:
    def parse(
        self,
        repo_path: Path | None = None,
        log_text: str | None = None,
        author_filter: str | None = None,
        since: str | None = None,        # "6 months ago"
    ) -> GitCorpus:
        ...

@dataclass
class GitCorpus:
    commit_patterns: list[str]          # Common commit message structures
    file_categories: dict[str, int]     # File types touched + frequency
    review_patterns: list[str]          # PR descriptions, review comments
    workflow_signals: list[str]         # CI/CD patterns, branch naming
```

**What we extract:**
- **Commit patterns:** Message structure reveals workflow (conventional commits → structured process, ad-hoc → flexible process)
- **File touch frequency:** Shows what the role actually works on vs. what the JD claims
- **PR descriptions:** Real output templates — how the person explains their work
- **Review comments:** Quality criteria in action — what they check for

#### Runbook/SOP Parser (`runbook.py`)

Input: Markdown, Confluence export, or plain text documents.

```python
class RunbookParser:
    def parse(self, path: Path) -> RunbookCorpus:
        ...

@dataclass
class RunbookCorpus:
    procedures: list[Procedure]         # Step-by-step processes
    decision_trees: list[str]           # If/then/else blocks
    checklists: list[list[str]]         # Bulleted check items
    templates: list[str]                # Fill-in-the-blank sections
```

**What we extract:**
- Procedures → Heuristics (trigger + steps)
- Decision trees → TriggerMappings
- Checklists → QualityCriteria
- Templates → OutputTemplates

This is the highest-signal source — runbooks are already structured methodology.

#### Meeting Notes Parser (`meeting_notes.py`)

Input: Markdown/text transcripts or summaries.

```python
class MeetingNotesParser:
    def parse(self, path: Path) -> MeetingCorpus:
        ...

@dataclass
class MeetingCorpus:
    decisions: list[str]                # "Decided: ..."
    action_items: list[str]             # "TODO: ...", "Action: ..."
    recurring_topics: list[str]         # Topics that appear across meetings
    stakeholder_patterns: list[str]     # Who talks to whom about what
```

### Multi-Source Methodology Enrichment

The key innovation: supplementary sources feed directly into `MethodologyStage`, enriching the LLM prompt with real operational data.

```python
class EnrichedMethodologyStage(PipelineStage):
    name = "methodology"

    def run(self, context):
        extraction = context["extraction"]
        supplements = context.get("supplementary_sources_parsed", [])

        # Build enrichment context from all sources
        enrichment = self._compile_enrichment(supplements)

        # Enhanced prompt includes real examples
        methodology = self.extractor.extract(
            extraction=extraction,
            user_examples=context.get("user_examples", "") + enrichment.examples,
            user_frameworks=context.get("user_frameworks", "") + enrichment.frameworks,
            operational_context=enrichment.operational_context,
        )

        context["methodology"] = methodology
        return context

    def _compile_enrichment(self, supplements) -> MethodologyEnrichment:
        examples = []
        frameworks = []
        operational = []

        for source in supplements:
            if isinstance(source, SlackCorpus):
                examples.extend(source.decision_points[:10])
                frameworks.extend(source.recurring_patterns[:5])
            elif isinstance(source, GitCorpus):
                examples.extend(source.review_patterns[:10])
                operational.extend(source.workflow_signals[:5])
            elif isinstance(source, RunbookCorpus):
                frameworks.extend(
                    f"Procedure: {p.name}\n{p.steps}" for p in source.procedures[:5]
                )
                examples.extend(source.templates[:5])
            elif isinstance(source, MeetingCorpus):
                frameworks.extend(source.decisions[:10])
                operational.extend(source.stakeholder_patterns[:5])

        return MethodologyEnrichment(
            examples="\n\n".join(examples),
            frameworks="\n\n".join(frameworks),
            operational_context="\n\n".join(operational),
        )
```

### Integration Points

**CLI:**
```bash
# Forge with supplementary sources
agentforge forge job.txt \
  --source slack-export.zip \
  --source runbook.md \
  --source meeting-notes.md \
  --git-repo ./my-project --git-author "jane@co.com"

# Extract from sources without a JD
agentforge extract-sources \
  --slack slack-export.zip \
  --runbook ops-guide.md \
  --output enrichment.yaml
```

**Web UI:**
- New "Sources" panel in forge wizard step 2 (Configure)
- Drag-and-drop zone for supplementary files
- Source type auto-detection (Slack JSON, git log, markdown)
- Preview: show what was extracted from each source before forging
- Source contribution indicator on final skill: "Methodology enriched by: 3 Slack threads, 2 runbook procedures, 15 git PR descriptions"

**API:**
```
POST /api/forge
  file: jd.txt
  supplementary_files: [slack.zip, runbook.md]
  supplementary_types: ["slack", "runbook"]     # Optional, auto-detected
  git_repo_path: "/path/to/repo"                # Optional
  git_author: "jane@co.com"                     # Optional
```

### Privacy & Security

Supplementary sources contain real operational data — this requires careful handling:

- **Anonymization:** Run all parsed content through `AnonymizeStage` before sending to LLM
- **PII detection:** Flag and strip emails, names, internal URLs, credentials
- **Source retention:** Parsed corpora are NOT stored in the database — only the enriched methodology is kept
- **Consent indicator:** UI shows exactly what text will be sent to the LLM, with opt-out per source

### Impact Estimate

Based on the current quality gaps flagged by `SkillReviewer`:
- **Without supplementary sources:** Average skill has 4-5 gaps (generic methodology, weak triggers, no templates)
- **With runbook + Slack:** Expect 1-2 gaps (persona and scope still need user input)
- **With all sources:** Most methodology gaps auto-resolve; remaining gaps are preference-based

---

## Feature 3: Skill Composition & Multi-Agent Orchestration

**Problem:** `TeamComposer` already identifies that a role should be split into 3-5 specialized agents. But the output is just a roster — names, archetypes, and skill lists. Users still have to manually forge each teammate and figure out how they coordinate.

**Solution:** Automatically forge the full team — a conductor agent plus specialized sub-agents — with handoff protocols, shared context specs, and a ready-to-deploy orchestration config.

### Architecture

**New files:**
```
src/agentforge/composition/
    __init__.py
    team_forger.py          # Forge all teammates from a single JD
    conductor_generator.py  # Generate the orchestrator skill
    handoff_protocol.py     # Define agent-to-agent communication
    orchestration_config.py # Export deployment config
    models.py               # AgentTeam, ConductorSkill, HandoffProtocol
```

**New pipeline mode:** `ForgePipeline.team()`
```python
@classmethod
def team(cls) -> ForgePipeline:
    """Full team forge: extract once, compose team, forge each member + conductor."""
    return cls(stages=[
        IngestStage(),
        AnonymizeStage(),
        ExtractStage(),
        MethodologyStage(),
        MapStage(),
        CultureStage(),
        TeamComposeStage(),     # Existing — produces AgentTeamComposition
        TeamForgeStage(),       # NEW — forges each teammate
        ConductorGenerateStage(),  # NEW — generates conductor skill
        AnalyzeStage(),
    ])
```

### Team Forging

`TeamForgeStage` takes the `AgentTeamComposition` and produces a full skill for each teammate:

```python
class TeamForgeStage(PipelineStage):
    name = "team_forge"

    def run(self, context):
        team = context["agent_team"]          # AgentTeamComposition
        extraction = context["extraction"]     # Full ExtractionResult
        methodology = context["methodology"]   # Full MethodologyExtraction
        culture = context.get("culture_profile")

        forged_teammates = []
        for teammate in team.teammates:
            # Create a scoped extraction for this teammate's skills only
            scoped_extraction = self._scope_extraction(extraction, teammate)
            scoped_methodology = self._scope_methodology(methodology, teammate)

            # Generate identity + skill for this teammate
            identity_gen = IdentityGenerator()
            identity, identity_yaml = identity_gen.generate(scoped_extraction)

            folder_gen = SkillFolderGenerator()
            skill_folder = folder_gen.generate(
                extraction=scoped_extraction,
                identity=identity,
                methodology=scoped_methodology,
            )

            forged_teammates.append(ForgedTeammate(
                teammate=teammate,
                identity=identity,
                identity_yaml=identity_yaml,
                skill_folder=skill_folder,
            ))

        context["forged_team"] = forged_teammates
        return context

    def _scope_extraction(self, extraction, teammate):
        """Create a focused ExtractionResult with only this teammate's skills."""
        scoped = extraction.model_copy(deep=True)
        scoped.skills = teammate.skills
        # Adjust role title to teammate's name
        scoped.role = scoped.role.model_copy(update={
            "title": teammate.name,
            "purpose": teammate.description,
        })
        # Filter responsibilities to those matching this teammate's skills
        scoped.responsibilities = self._filter_responsibilities(
            extraction.responsibilities, teammate.skills
        )
        return scoped

    def _scope_methodology(self, methodology, teammate):
        """Filter methodology to relevant heuristics/triggers for this teammate."""
        if not methodology:
            return None
        skill_names = {s.name.lower() for s in teammate.skills}
        skill_keywords = set()
        for s in teammate.skills:
            skill_keywords.update(s.name.lower().split())
            if s.context:
                skill_keywords.update(s.context.lower().split()[:10])

        return MethodologyExtraction(
            heuristics=[h for h in methodology.heuristics
                       if self._matches_skills(h, skill_keywords)],
            trigger_mappings=[t for t in methodology.trigger_mappings
                            if self._matches_skills(t, skill_keywords)],
            output_templates=[t for t in methodology.output_templates
                            if self._matches_skills(t, skill_keywords)],
            quality_criteria=methodology.quality_criteria,  # Keep all — shared standards
        )
```

### Conductor Generation

The conductor is a special skill that routes requests to the right teammate and orchestrates multi-step workflows.

```python
class ConductorGenerator:
    def generate(
        self,
        team: AgentTeamComposition,
        forged_teammates: list[ForgedTeammate],
        extraction: ExtractionResult,
    ) -> ConductorSkill:

        # Build routing table from team composition
        routing_table = self._build_routing_table(forged_teammates)

        # Build orchestration workflows for multi-agent tasks
        workflows = self._build_workflows(forged_teammates, extraction)

        # Generate conductor SKILL.md
        skill_md = self._render_conductor_skill(
            role_title=extraction.role.title,
            routing_table=routing_table,
            workflows=workflows,
            teammates=forged_teammates,
        )

        return ConductorSkill(
            skill_md=skill_md,
            routing_table=routing_table,
            workflows=workflows,
        )
```

**Conductor SKILL.md structure:**

```markdown
---
name: {role}-conductor
description: "Orchestrate the {role} agent team"
allowed-tools: ["Read", "Glob", "Grep", "Agent"]
---

# {Role Title} — Team Conductor

You coordinate a team of {N} specialized agents. Route requests to the right
agent, orchestrate multi-step workflows, and synthesize results.

## Team Roster

| Agent | Specialization | Invoke When |
|-------|---------------|-------------|
| {name} | {archetype} | {trigger_summary} |
| ... | ... | ... |

## Routing Rules

When a request arrives:

1. **Single-agent tasks:** Route to the best-matching agent based on keywords:
   - Keywords [{kw1}, {kw2}] → {agent_name}
   - Keywords [{kw3}, {kw4}] → {agent_name}
   - ...

2. **Multi-agent workflows:** When a task requires multiple specializations:
   {workflow descriptions}

3. **Ambiguous requests:** Ask the user to clarify scope before routing.

4. **Out-of-scope:** If no agent matches, state what the team can and cannot do.

## Workflows

### {Workflow Name}
Trigger: {when this workflow activates}
Steps:
1. {Agent A}: {task} → produces {artifact}
2. {Agent B}: uses {artifact} → produces {result}
3. Conductor: synthesizes {result} into final output

## Handoff Protocol

When delegating to an agent:
- Provide: task description, relevant context, expected output format
- Receive: completed work product, confidence level, blockers (if any)
- If blocked: escalate to user or try alternative agent
```

### Handoff Protocol

Defines how agents pass work to each other:

```python
@dataclass
class HandoffProtocol:
    from_agent: str
    to_agent: str
    trigger: str              # When this handoff occurs
    context_passed: list[str] # What the receiving agent needs
    expected_output: str      # What the receiving agent produces
    fallback: str             # What to do if the receiving agent fails

@dataclass
class OrchestratedWorkflow:
    name: str
    trigger: str
    steps: list[WorkflowStep]

@dataclass
class WorkflowStep:
    agent: str
    task: str
    inputs: list[str]         # From previous steps or initial context
    outputs: list[str]        # Artifacts produced
    parallel_with: list[str]  # Steps that can run concurrently
```

### Orchestration Config Export

Generate deployment-ready configs for different runtimes:

```python
class OrchestrationConfigExporter:
    def export_claude_code(self, team, conductor) -> dict[str, str]:
        """Export as .claude/skills/ directory structure."""
        files = {}
        # Conductor skill
        files[f".claude/skills/{conductor.skill_name}/SKILL.md"] = conductor.skill_md
        # Teammate skills
        for tm in team:
            files[f".claude/skills/{tm.skill_folder.skill_name}/SKILL.md"] = (
                tm.skill_folder.skill_md
            )
        return files

    def export_agent_sdk(self, team, conductor) -> str:
        """Export as Claude Agent SDK Python scaffolding."""
        # Generate agent definitions + orchestration loop
        return rendered_python_code

    def export_mcp_multi(self, team) -> dict:
        """Export combined MCP config for all teammates."""
        combined = {"mcpServers": {}}
        for tm in team:
            if tm.tool_profile:
                combined["mcpServers"].update(tm.tool_profile.mcp_config)
        return combined
```

### Integration Points

**CLI:**
```bash
# Forge full team from a single JD
agentforge team job.txt --output-dir ./agents/

# Output structure:
# ./agents/
#   conductor/SKILL.md
#   code-architect/SKILL.md
#   devops-pilot/SKILL.md
#   quality-guardian/SKILL.md
#   orchestration.yaml
#   .mcp.json (combined)
```

**Web UI:**
- New "Team Forge" mode in pipeline selector (alongside default/quick/deep)
- Team visualization: node graph showing agents + handoff arrows
- Click any agent node → view/edit its skill
- Download entire team as ZIP (drop into `.claude/skills/`)
- Orchestration workflow diagram (mermaid or similar)

**API:**
```
POST /api/forge
  file: jd.txt
  mode: "team"
  → Returns job with forged_team in result

GET /api/forge/{job_id}/team
  → Team structure with all skills

GET /api/forge/{job_id}/team/download
  → ZIP with all skills + conductor + orchestration config
```

### Scoping Rules for Teammate Skills

Each teammate skill should be **narrower** than the original full skill:

1. **Explicit scope:** Only the skills assigned to this teammate
2. **Explicit guardrails:** "Delegate {X} to {other agent} rather than attempting it yourself"
3. **Handoff awareness:** Each skill knows about the conductor and can request delegation
4. **Shared standards:** Quality criteria are shared across all teammates (consistency)

### Cost Estimate

Per team forge (assuming 4 teammates + conductor):
- Base extraction: 1 LLM call (shared across team)
- Per teammate generation: lightweight (template-based, no extra LLM calls)
- Conductor generation: 1 LLM call for workflow planning
- **Total: ~2 LLM calls beyond a standard forge (~$0.02-0.05 extra)**

Team forge is cheap because most of the work (extraction, methodology) is done once and scoped per teammate without additional LLM calls.

---

## Implementation Priority

### Phase 1: Skill Testing (2-3 weeks)
Why first: Closes the quality feedback loop. Every subsequent feature benefits from being testable. Also the smallest scope — mostly new code, minimal changes to existing pipeline.

**Milestones:**
1. `ScenarioGenerator` + `TestScenario` model
2. `SkillRunner` with plain `generate()` on LLMClient
3. `Evaluator` with LLM-as-judge
4. `TestStage` pipeline integration
5. CLI: `agentforge test`
6. Web UI: test panel on forge results
7. Feedback loop: test failures → Review & Refine pre-population

### Phase 2: Multi-Agent Orchestration (2-3 weeks)
Why second: Builds on existing `TeamComposer` (already done), uses existing `SkillFolderGenerator` and `IdentityGenerator` per teammate. High user value — goes from "here's a roster" to "here's a deployable team."

**Milestones:**
1. `TeamForgeStage` with scoped extraction/methodology
2. `ConductorGenerator` with routing table + workflow builder
3. `HandoffProtocol` model + generation
4. `ForgePipeline.team()` mode
5. CLI: `agentforge team`
6. Web UI: team visualization + per-agent editing
7. Export: Claude Code skills + Agent SDK scaffold + combined MCP

### Phase 3: Non-JD Input Sources (3-4 weeks)
Why third: Highest complexity (multiple parsers, privacy handling, LLM prompt engineering for enrichment). Also the highest impact on methodology quality — but testing and team forge create immediate value without it.

**Milestones:**
1. `RunbookParser` (highest signal, simplest format)
2. `SlackParser` (JSON export handling, thread reconstruction)
3. `GitLogParser` (commit + PR pattern extraction)
4. `MeetingNotesParser` (transcript processing)
5. `MultiIngestStage` + `EnrichedMethodologyStage`
6. Privacy: anonymization pass on all parsed content
7. CLI: `--source` flag on forge
8. Web UI: sources panel in configure step
9. Source contribution indicators on output

### Cross-Cutting Concerns

**Testing all three features:**
- Feature 1 (Skill Testing) becomes the test harness for Features 2 and 3
- Team-forged skills should pass the same test suite
- Enriched skills (from supplementary sources) should score higher on tests

**Documentation:**
- Update USER_GUIDE.md with each feature
- Add examples directory with sample inputs (mock Slack export, sample runbook, etc.)

**Database:**
- New tables/columns: `test_reports`, `team_compositions`, `supplementary_sources`
- Migration strategy: additive only (new tables, no schema changes to existing)
