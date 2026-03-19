"""Parse git log output for methodology enrichment."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitCorpus:
    """Parsed git history data for methodology enrichment."""
    commit_patterns: list[str] = field(default_factory=list)
    file_categories: dict[str, int] = field(default_factory=dict)
    review_patterns: list[str] = field(default_factory=list)
    workflow_signals: list[str] = field(default_factory=list)

    def to_enrichment(self) -> dict[str, str]:
        """Convert to methodology enrichment context."""
        examples = "\n\n".join(self.review_patterns[:10])
        workflow = "\n".join(f"- {s}" for s in self.workflow_signals[:5])
        file_focus = ", ".join(
            f"{ext} ({count})" for ext, count in
            sorted(self.file_categories.items(), key=lambda x: x[1], reverse=True)[:5]
        )
        operational = []
        if workflow:
            operational.append(f"Workflow patterns:\n{workflow}")
        if file_focus:
            operational.append(f"Primary file types worked on: {file_focus}")
        return {
            "examples": examples,
            "operational_context": "\n\n".join(operational),
        }


class GitLogParser:
    """Parse git log output for methodology enrichment."""

    def parse(
        self,
        log_text: str | None = None,
        repo_path: Path | None = None,
        author_filter: str | None = None,
        since: str | None = None,
        max_commits: int = 200,
    ) -> GitCorpus:
        """Parse git log text or read from a repo path."""
        if log_text is None and repo_path:
            log_text = self._read_git_log(repo_path, author_filter, since, max_commits)

        if not log_text:
            return GitCorpus()

        commits = self._parse_commits(log_text)
        if author_filter:
            commits = [c for c in commits if author_filter.lower() in c.get("author", "").lower()]

        return GitCorpus(
            commit_patterns=self._extract_commit_patterns(commits),
            file_categories=self._extract_file_categories(commits),
            review_patterns=self._extract_review_patterns(commits),
            workflow_signals=self._extract_workflow_signals(commits),
        )

    def _read_git_log(
        self, repo_path: Path, author: str | None, since: str | None, max_commits: int
    ) -> str:
        import subprocess

        cmd = [
            "git", "-C", str(repo_path), "log",
            f"--max-count={max_commits}",
            "--format=COMMIT_START%nHash: %H%nAuthor: %an <%ae>%nDate: %ai%nSubject: %s%nBody: %b%nFiles: ",
            "--name-only",
        ]
        if author:
            cmd.append(f"--author={author}")
        if since:
            cmd.append(f"--since={since}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.stdout
        except (subprocess.SubprocessError, FileNotFoundError):
            return ""

    def _parse_commits(self, log_text: str) -> list[dict]:
        commits = []
        blocks = log_text.split("COMMIT_START")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            commit: dict = {"files": []}
            for line in block.splitlines():
                if line.startswith("Hash: "):
                    commit["hash"] = line[6:].strip()
                elif line.startswith("Author: "):
                    commit["author"] = line[8:].strip()
                elif line.startswith("Date: "):
                    commit["date"] = line[6:].strip()
                elif line.startswith("Subject: "):
                    commit["subject"] = line[9:].strip()
                elif line.startswith("Body: "):
                    commit["body"] = line[6:].strip()
                elif line.startswith("Files: "):
                    pass  # Next lines are files
                elif line.strip() and "hash" in commit:
                    commit["files"].append(line.strip())

            if commit.get("subject"):
                commits.append(commit)

        return commits

    def _extract_commit_patterns(self, commits: list[dict]) -> list[str]:
        """Identify commit message patterns (conventional commits, etc.)."""
        patterns = set()
        type_counts: dict[str, int] = {}

        for c in commits:
            subject = c.get("subject", "")
            # Check for conventional commits
            match = re.match(r"^(feat|fix|docs|style|refactor|test|chore|ci|perf|build)(\(.+?\))?:", subject)
            if match:
                ctype = match.group(1)
                type_counts[ctype] = type_counts.get(ctype, 0) + 1

        if type_counts:
            patterns.add("Uses conventional commits: " + ", ".join(
                f"{k} ({v})" for k, v in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
            ))

        # Check for PR merge patterns
        merge_count = sum(1 for c in commits if c.get("subject", "").startswith("Merge"))
        if merge_count > 5:
            patterns.add(f"PR/merge-based workflow ({merge_count} merges)")

        return list(patterns)

    def _extract_file_categories(self, commits: list[dict]) -> dict[str, int]:
        """Count file extensions touched."""
        ext_counts: dict[str, int] = {}
        for c in commits:
            for f in c.get("files", []):
                ext = Path(f).suffix.lower() or "(no ext)"
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
        return ext_counts

    def _extract_review_patterns(self, commits: list[dict]) -> list[str]:
        """Extract PR descriptions and detailed commit messages as work samples."""
        patterns = []
        for c in commits:
            body = c.get("body", "")
            if len(body) > 100:
                patterns.append(body[:500])
        return patterns[:10]

    def _extract_workflow_signals(self, commits: list[dict]) -> list[str]:
        """Identify workflow patterns from commit history."""
        signals = []

        # Branch naming patterns
        subjects = [c.get("subject", "") for c in commits]
        if any("Merge pull request" in s for s in subjects):
            signals.append("GitHub PR workflow (merge commits detected)")
        if any("squash" in s.lower() for s in subjects):
            signals.append("Squash merge strategy in use")

        # CI/CD signals
        ci_files = set()
        for c in commits:
            for f in c.get("files", []):
                if any(ci in f.lower() for ci in [".github/workflows", "jenkinsfile", ".circleci", ".gitlab-ci"]):
                    ci_files.add(f)
        if ci_files:
            signals.append(f"CI/CD configuration: {', '.join(list(ci_files)[:3])}")

        return signals
