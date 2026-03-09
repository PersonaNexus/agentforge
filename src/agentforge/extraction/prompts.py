"""Prompt templates for LLM-powered skill extraction."""

SYSTEM_PROMPT = """You are an expert HR analyst and AI agent architect. Your job is to analyze \
job descriptions and extract structured skill, role, and automation data.

You must be precise and thorough. Extract ALL skills mentioned or implied in the job description, \
categorize them correctly, and assess the automation potential of this role.

For personality traits, consider what traits an AI agent performing this role would need, \
using a 0-1 scale where 0.5 is neutral:
- warmth: How warm/friendly vs. reserved the agent should be
- verbosity: How detailed/verbose vs. concise
- assertiveness: How assertive/confident vs. deferential
- humor: How much humor to incorporate
- empathy: How empathetic/understanding
- directness: How direct/blunt vs. diplomatic
- rigor: How rigorous/precise vs. flexible
- creativity: How creative/innovative vs. conventional
- epistemic_humility: How willing to say "I don't know"
- patience: How patient with users"""

EXTRACTION_PROMPT = """Analyze this job description and extract structured data.

JOB DESCRIPTION:
---
{jd_text}
---

Extract the following:

1. **Role**: The job title, its core purpose (1-2 sentences), primary scope (main responsibilities), \
secondary scope (nice-to-have duties), target audience, seniority level, and domain.

2. **Skills**: Every skill mentioned or strongly implied. For each skill:
   - name: The skill name (e.g., "Python", "stakeholder management")
   - category: "hard" (technical), "soft" (interpersonal), "domain" (industry knowledge), or "tool" (specific tool/platform)
   - proficiency: "beginner", "intermediate", "advanced", or "expert" (based on JD requirements)
   - importance: "required", "preferred", or "nice_to_have"
   - context: Brief note on how this skill is used in the role
   - examples: For tool/platform/domain skills, list specific tools, libraries, or applications \
(e.g., ["Salesforce for pipeline management", "Hugging Face for NLP"]). Leave empty for generic skills.
   - genai_application: For domain and tool skills, briefly describe how GenAI/ML could augment \
or automate this skill area (e.g., "ML models for demand forecasting and anomaly detection"). \
Leave empty if not applicable.

3. **Responsibilities**: List of key responsibilities (verbatim or lightly cleaned from JD).

4. **Qualifications**: List of stated qualifications (education, certifications, years of experience).

5. **Suggested personality traits**: What personality traits (0-1 scale) would make an AI agent \
effective in this role? Only set traits that are clearly relevant — leave others as null.

6. **Automation potential**: What percentage (0-1) of this role could an AI agent realistically \
automate? Consider which tasks are routine vs. requiring human judgment.

7. **Automation rationale**: Brief explanation of what can and cannot be automated.

8. **Salary range**: If the job description mentions a salary or compensation range, extract \
salary_min and salary_max as annual USD amounts (numeric values only, no currency symbols). \
If the JD states an hourly rate, multiply by 2080 to convert to annual. \
If no salary information is provided, set both to null."""
