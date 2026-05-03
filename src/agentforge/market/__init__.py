"""Market — JD-corpus observability for AgentForge.

Where Department synthesizes a *team* from a JD corpus, Market answers
the *meta* question: what does the corpus say about skill demand, and
how does an existing agent measure up?

Phase 1.0 ships two deterministic surfaces:

- ``market trends`` — aggregate statistics across a corpus: top skills
  by frequency, breakdowns by category and importance, role-domain
  distribution, optional recency split when JD frontmatter carries a
  date.
- ``market gap`` — compare a drill SkillInventory (an agent's actual
  capability surface) to a Department SkillLandscape (what the corpus
  demands). Surfaces market-only skills (high-demand gaps), agent-only
  skills (unique value worth reviewing), and a coverage score.

Phase 1.1 will add ``market propose`` — gap → forge → integrate loop.
That's the only LLM-bearing surface and is intentionally deferred.

Market shares the corpus layer with Department (``agentforge.corpus``)
and reuses ``agentforge.day2`` for finding rendering, CLI validation,
and frontmatter parsing.
"""

from agentforge.market.gap import (
    GapReport,
    GapSkill,
    compute_gap,
    render_gap_markdown,
    write_gap_report,
)
from agentforge.market.models import (
    CategoryBreakdown,
    RecencyBucket,
    SkillTrend,
    TrendsReport,
)
from agentforge.market.trends import (
    compute_trends,
    render_trends_markdown,
    write_trends_report,
)

__all__ = [
    "CategoryBreakdown",
    "GapReport",
    "GapSkill",
    "RecencyBucket",
    "SkillTrend",
    "TrendsReport",
    "compute_gap",
    "compute_trends",
    "render_gap_markdown",
    "render_trends_markdown",
    "write_gap_report",
    "write_trends_report",
]
