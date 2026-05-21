#!/usr/bin/env python3
"""Look up an economic indicator's explainer card from references/indicators.md.

Usage:
    lookup_indicator.py "CPI YoY"
    lookup_indicator.py "Consumer Price Index (CPI) YoY"   # FMP event name alias
    lookup_indicator.py --json "Core PCE"
    lookup_indicator.py --list

The knowledge base lives in ../references/indicators.md as a sequence of
frontmatter-tagged cards. We parse on every call (fast — file is <100KB).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

INDICATORS_PATH = Path(__file__).parent.parent / "references" / "indicators.md"

CARD_PATTERN = re.compile(
    r"^---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*?)(?=\n---\n|\Z)",
    re.DOTALL | re.MULTILINE,
)


def parse_cards(text: str) -> list[dict]:
    cards: list[dict] = []
    for match in CARD_PATTERN.finditer(text):
        fm = match.group("frontmatter")
        body = match.group("body").strip()
        meta: dict = {"fmp_aliases": []}

        in_aliases = False
        for raw in fm.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue
            if line.startswith("fmp_aliases:"):
                in_aliases = True
                continue
            if in_aliases and line.startswith("  -"):
                alias = line.lstrip(" -").strip().strip('"').strip("'")
                if alias:
                    meta["fmp_aliases"].append(alias)
                continue
            if in_aliases and not line.startswith("  "):
                in_aliases = False

            if ":" in line and not line.startswith(" "):
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip('"').strip("'")

        meta["body"] = body
        if meta.get("canonical"):
            cards.append(meta)
    return cards


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def find_card(cards: list[dict], query: str) -> dict | None:
    q = _normalize(query)
    if not q:
        return None

    # Pass 1: exact canonical / short_name match
    for c in cards:
        if _normalize(c.get("canonical", "")) == q:
            return c
        if _normalize(c.get("short_name", "")) == q:
            return c

    # Pass 2: exact alias match
    for c in cards:
        for alias in c.get("fmp_aliases", []):
            if _normalize(alias) == q:
                return c

    # Pass 3: substring match (alias contains query OR query contains alias)
    best = None
    best_score = 0
    for c in cards:
        candidates = [c.get("canonical", ""), c.get("short_name", "")] + c.get("fmp_aliases", [])
        for cand in candidates:
            nc = _normalize(cand)
            if not nc:
                continue
            score = 0
            if q in nc:
                score = len(q) / max(len(nc), 1)
            elif nc in q:
                score = len(nc) / max(len(q), 1)
            if score > best_score:
                best_score = score
                best = c
    if best_score >= 0.4:
        return best
    return None


def parse_body_sections(body: str) -> dict:
    sections: dict = {}
    current = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buffer).strip()
            current = line[3:].strip().lower().replace(" ", "_")
            buffer = []
        else:
            buffer.append(line)
    if current:
        sections[current] = "\n".join(buffer).strip()
    return sections


def main() -> int:
    ap = argparse.ArgumentParser(description="Look up an economic indicator explainer card.")
    ap.add_argument("indicator", nargs="?", help="Indicator name or FMP event name")
    ap.add_argument("--list", action="store_true", help="List all known indicators")
    ap.add_argument("--json", action="store_true", help="Output as JSON")
    args = ap.parse_args()

    if not INDICATORS_PATH.exists():
        print(f"ERROR: indicators.md not found at {INDICATORS_PATH}", file=sys.stderr)
        return 1

    cards = parse_cards(INDICATORS_PATH.read_text(encoding="utf-8"))

    if args.list:
        for c in cards:
            short = c.get("short_name", "?")
            canonical = c.get("canonical", "?")
            country = c.get("country", "?")
            category = c.get("category", "?")
            print(f"  {short:<18} [{country}/{category:<10}] {canonical}")
        print(f"\nTotal: {len(cards)} indicators")
        return 0

    if not args.indicator:
        ap.print_help()
        return 1

    card = find_card(cards, args.indicator)
    if not card:
        print(
            f"No match for '{args.indicator}'. Use --list to see known indicators.",
            file=sys.stderr,
        )
        return 2

    if args.json:
        out = {k: v for k, v in card.items() if k != "body"}
        out["sections"] = parse_body_sections(card["body"])
        print(json.dumps(out, indent=2))
        return 0

    print(f"# {card.get('canonical', '?')}")
    for k in (
        "short_name",
        "category",
        "country",
        "release_time_et",
        "frequency",
        "release_source",
        "importance",
    ):
        if k in card:
            print(f"**{k}**: {card[k]}")
    if card.get("fmp_aliases"):
        print(f"**aliases**: {', '.join(card['fmp_aliases'])}")
    print()
    print(card["body"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
