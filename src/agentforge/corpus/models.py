"""Pydantic models for the JD corpus."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JDFrontmatter(BaseModel):
    """Required + optional frontmatter fields for a JD entry.

    The minimum schema is small on purpose — ``title`` is the only thing
    the corpus loader treats as required. Everything else is optional so
    a user can drop in raw JDs and progressively enrich the metadata.

    The ``posted`` field accepts the more natural ``date:`` key in YAML
    via alias.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str
    seniority: str | None = None  # e.g. "junior" / "mid" / "senior" / "staff"
    domain: str | None = None     # e.g. "software-engineering"
    source: str | None = None     # e.g. "linkedin", "synthetic-fixture"
    posted: str | None = Field(default=None, alias="date")  # ISO date string; aliases YAML key 'date'

    @field_validator("posted", mode="before")
    @classmethod
    def _coerce_date(cls, v):
        # YAML auto-parses unquoted ISO dates into datetime.date — coerce to str
        return None if v is None else str(v)

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("frontmatter 'title' must be non-empty")
        return v


class JDEntry(BaseModel):
    """One JD parsed from a corpus directory: frontmatter + body."""

    path: str  # absolute path on disk
    role_id: str  # filesystem-safe slug derived from filename (no extension)
    frontmatter: JDFrontmatter
    body: str  # markdown JD body, frontmatter stripped

    @property
    def title(self) -> str:
        return self.frontmatter.title


class Corpus(BaseModel):
    """A directory of JDs as a single load-able unit."""

    root: str
    entries: list[JDEntry] = Field(default_factory=list)

    def __iter__(self):  # type: ignore[override]
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def by_role(self, role_id: str) -> JDEntry | None:
        for e in self.entries:
            if e.role_id == role_id:
                return e
        return None
