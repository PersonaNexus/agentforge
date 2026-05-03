"""Department — synthesize a multi-agent team from a JD corpus.

Takes a directory of JDs (one per role) and produces an integrated
multi-agent team where cross-cutting concerns are factored into shared
resources. Phase 1.0 ships the skill-landscape analysis (extract per
role + cluster skills across roles + report). Phase 1.1 will add the
synthesis layer — per-role identities, shared resource generation,
conductor + orchestration.yaml.

Read-only on the corpus; never edits source JD files.
"""

from agentforge.department.cluster import (
    SkillCluster,
    SkillLandscape,
    cluster_skills,
)

__all__ = ["SkillCluster", "SkillLandscape", "cluster_skills"]
