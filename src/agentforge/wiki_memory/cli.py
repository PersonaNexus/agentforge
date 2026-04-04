"""CLI entrypoint for wiki-memory.

Usage (as a standalone module)::

    python -m agentforge.wiki_memory.cli init --root ~/wiki
    python -m agentforge.wiki_memory.cli add --title "AI Gateway" \\
        --type entity --kind project --alias gateway \\
        --fact "Runs on port 8900" --source "session:2026-04-04"
    python -m agentforge.wiki_memory.cli show ai-gateway
    python -m agentforge.wiki_memory.cli search gateway
    python -m agentforge.wiki_memory.cli candidate --subject "AI Gateway" \\
        --claim "Uses Gemma 4 E4B" --type entity --kind project \\
        --source session:2026-04-04
    python -m agentforge.wiki_memory.cli pending
    python -m agentforge.wiki_memory.cli promote --accept-all
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .promote import promote
from .schema import CandidateFact
from .store import WikiStore

DEFAULT_ROOT = Path.home() / "personal-ai-org" / "shared" / "wiki"


def _store(args: argparse.Namespace) -> WikiStore:
    return WikiStore(args.root)


def cmd_init(args: argparse.Namespace) -> int:
    store = _store(args)
    print(f"Initialized wiki at {store.root}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    store = _store(args)
    page = store.get_or_create(
        args.title, type=args.type, kind=args.kind, aliases=args.alias or [],
    )
    if args.fact:
        page.add_fact(
            claim=args.fact,
            source=args.source or "manual",
            confidence=args.confidence,
            contributor=args.contributor,
        )
    if args.tag:
        for t in args.tag:
            if t not in page.tags:
                page.tags.append(t)
    path = store.save(page)
    print(f"Saved {page.id} → {path}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = _store(args)
    page = store.load(args.page_id) or store.resolve(args.page_id)
    if page is None:
        print(f"not found: {args.page_id}", file=sys.stderr)
        return 1
    print(f"# {page.title} [{page.type}{'/' + page.kind if page.kind else ''}]")
    print(f"  id: {page.id}")
    print(f"  aliases: {', '.join(page.aliases) or '-'}")
    print(f"  updated: {page.updated}  confidence: {page.confidence}")
    print(f"  facts ({len(page.facts)}):")
    for f in page.facts:
        print(f"    - {f.claim}  [{f.source}, {f.confidence}]")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    store = _store(args)
    hits = store.search(args.query)
    if not hits:
        print("no matches")
        return 0
    for page in hits:
        print(f"{page.id}\t{page.type}\t{page.title}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = _store(args)
    for page in store.list_pages():
        tag = f"{page.type}/{page.kind}" if page.kind else page.type
        print(f"{page.id}\t{tag}\t{page.title}")
    return 0


def cmd_candidate(args: argparse.Namespace) -> int:
    store = _store(args)
    cf = CandidateFact(
        subject_hint=args.subject,
        claim=args.claim,
        page_type=args.type,
        kind=args.kind,
        source=args.source or "",
        confidence=args.confidence,
        contributor=args.contributor or "",
    )
    store.queue_candidate(cf)
    print(f"queued: {cf.subject_hint} — {cf.claim[:60]}")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    store = _store(args)
    items = store.pending()
    if not items:
        print("no pending candidates")
        return 0
    for i, cf in enumerate(items):
        print(f"[{i}] {cf.captured}  {cf.subject_hint}")
        print(f"     {cf.claim}")
        print(f"     type={cf.page_type} kind={cf.kind} conf={cf.confidence} src={cf.source}")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    store = _store(args)
    items = store.pending()
    if not items:
        print("no pending candidates")
        return 0
    if args.accept_all:
        for cf in items:
            page = promote(store, cf, decision="accept")
            if page is not None:
                print(f"accepted: {cf.subject_hint} → {page.id}")
        return 0
    # Interactive y/n/e.
    for cf in items:
        print(f"\n{cf.subject_hint}: {cf.claim}")
        print(f"  type={cf.page_type} kind={cf.kind} src={cf.source} conf={cf.confidence}")
        ans = input("  [a]ccept / [r]eject / [e]dit / [s]kip? ").strip().lower()
        if ans == "a":
            page = promote(store, cf, decision="accept")
            print(f"  → {page.id if page else '(none)'}")
        elif ans == "r":
            promote(store, cf, decision="reject")
            print("  → rejected")
        elif ans == "e":
            new_claim = input("  new claim: ").strip()
            page = promote(store, cf, decision="edit", edited_claim=new_claim)
            print(f"  → {page.id if page else '(none)'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentforge-wiki", description="wiki-memory CLI")
    p.add_argument("--root", default=str(DEFAULT_ROOT), help="wiki root dir")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    a = sub.add_parser("add")
    a.add_argument("--title", required=True)
    a.add_argument("--type", choices=["entity", "concept"], required=True)
    a.add_argument("--kind", choices=["person", "project", "system", "org", "place", "other"])
    a.add_argument("--alias", action="append")
    a.add_argument("--tag", action="append")
    a.add_argument("--fact")
    a.add_argument("--source")
    a.add_argument("--confidence", choices=["high", "medium", "low"], default="medium")
    a.add_argument("--contributor")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("show")
    s.add_argument("page_id")
    s.set_defaults(func=cmd_show)

    sr = sub.add_parser("search")
    sr.add_argument("query")
    sr.set_defaults(func=cmd_search)

    sub.add_parser("list").set_defaults(func=cmd_list)

    c = sub.add_parser("candidate")
    c.add_argument("--subject", required=True)
    c.add_argument("--claim", required=True)
    c.add_argument("--type", choices=["entity", "concept"], required=True)
    c.add_argument("--kind", choices=["person", "project", "system", "org", "place", "other"])
    c.add_argument("--source")
    c.add_argument("--confidence", choices=["high", "medium", "low"], default="medium")
    c.add_argument("--contributor")
    c.set_defaults(func=cmd_candidate)

    sub.add_parser("pending").set_defaults(func=cmd_pending)

    pr = sub.add_parser("promote")
    pr.add_argument("--accept-all", action="store_true")
    pr.set_defaults(func=cmd_promote)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
