#!/usr/bin/env python3
"""Collect unit_tests verification evidence for production skills (issue #496).

For every production skill whose ``unit_tests`` axis is ``not_verified`` in
``skills-index.yaml``, this collector:

1. enumerates executable scripts with the same rule as
   ``scripts.ci_test_matrix.executable_test_inventory`` (recursive ``rglob("*.py")``,
   excluding ``__init__.py`` and any ``tests`` path segment);
2. gathers candidate test modules from both canonical skill locations
   (``skills/<id>/scripts/tests`` and ``skills/<id>/tests``) and the repo-level
   integration suite (``scripts/tests``);
3. proposes a script-to-test mapping (advisory; must be reviewer-confirmed before
   it is recorded in the verification baseline);
4. runs the replayable evidence command pair
   ``python3 scripts/ci_test_matrix.py install <id> && python3 scripts/ci_test_matrix.py run <id>``
   and records exit codes;
5. records advisory signals for error-path/fail-closed coverage and per-skill
   output-schema conformance assertions;
6. emits a JSON evidence report with a proposed ``passed``/``gap`` value per skill.
   The script never writes YAML; the human/agent reviewer confirms proposals and
   applies index/baseline edits separately.

Usage::

    python3 scripts/backfill_unit_tests_evidence.py                # all skills
    python3 scripts/backfill_unit_tests_evidence.py --skill position-sizer
    python3 scripts/backfill_unit_tests_evidence.py --skip-run    # structural only
    python3 scripts/backfill_unit_tests_evidence.py --output-dir reports/
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402  (ci_test_matrix already requires PyYAML)

INDEX_PATH = ROOT / "skills-index.yaml"

SCHEMA_QUESTION_RE = re.compile(
    r"schema\.json|jsonschema|required[_ ](?:keys|fields)|declared[_ ]outputs", re.IGNORECASE
)
SCHEMA_ASSERT_RE = re.compile(r"assert |\.issubset\(", re.IGNORECASE)
FAILOPEN_ASSERT_RE = re.compile(
    r"pytest\.raises|assert .*returncode|assert .*exit|assert .*invalid|assert .*error",
    re.IGNORECASE,
)


def load_index(path: Path = INDEX_PATH) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        index = yaml.safe_load(handle)
    skills = index.get("skills") or []
    return [skill for skill in skills if skill.get("status") == "production"]  # type: ignore[misc]


def executable_scripts(skill_dir: Path) -> list[Path]:
    scripts_dir = skill_dir / "scripts"
    return [
        path
        for path in sorted(scripts_dir.rglob("*.py"))
        if path.is_file()
        and path.name != "__init__.py"
        and "tests" not in path.relative_to(scripts_dir).parts
    ]


def test_locations(skill_dir: Path) -> dict[str, list[Path]]:
    skill_dir = skill_dir.resolve()
    locations: dict[str, list[Path]] = {
        "skill_local": [],
        "repo_level": [],
    }
    for relative in (Path("scripts/tests"), Path("tests")):
        directory = skill_dir / relative
        if directory.is_dir():
            locations["skill_local"].extend(
                sorted(p.relative_to(ROOT) for p in directory.glob("*.py"))
            )
    repo_tests = ROOT / "scripts" / "tests"
    if repo_tests.is_dir():
        locations["repo_level"].extend(sorted(p.relative_to(ROOT) for p in repo_tests.glob("*.py")))
    return locations


def rel_root(path: Path) -> str:
    base = ROOT.resolve()
    resolved = path.resolve()
    if base in resolved.parents:
        return resolved.relative_to(base).as_posix()
    return path.as_posix()


def propose_mapping(
    scripts: Iterable[Path], locations: dict[str, list[Path]]
) -> tuple[dict[str, list[str]], list[str]]:
    """Propose candidate test modules per executable script via name/mention match."""
    test_texts: list[tuple[str, str]] = []
    for group in ("skill_local", "repo_level"):
        for test_path in locations[group]:
            try:
                text = test_path.read_text(errors="replace")
            except OSError:
                try:
                    text = (ROOT / test_path).read_text(errors="replace")
                except OSError:
                    continue
            test_texts.append((rel_root(test_path), text))
    mapping: dict[str, list[str]] = {}
    unmatched: list[str] = []
    for script in scripts:
        script_rel = rel_root(script)
        stem_word = re.compile(rf"\b{re.escape(script.stem)}\b")
        hits: set[str] = set()
        for test_rel, text in test_texts:
            if stem_word.search(text) or script_rel in text:
                hits.add(test_rel)
        if hits:
            mapping[script_rel] = sorted(hits)
        else:
            unmatched.append(script_rel)
    return mapping, unmatched


def signals(
    skill_local_files: Iterable[Path],
    candidate_files: Iterable[Path],
    excluded_files: Iterable[Path] = (),
) -> tuple[dict[str, bool], list[str]]:
    """Assertion-shaped signals.

    Only skill-local mapped tests (``skills/<id>/scripts/tests``) can source a
    signal: repo-level suites such as ``test_provider_contracts.py`` assert
    provider input contracts (issue #332), not the skill's own output schema,
    and must not back an ``output-schema conformance`` claim. ``excluded_files``
    removes repo-level test files that would otherwise be counted as mapping
    sources by name coincidence (e.g. this PR's own test file). Returns
    (signals, source_files); the reviewer-confirmation flag starts False and is
    only set True by the human/agent reviewer before baseline edits.
    """
    excluded = {rel_root(path) for path in excluded_files}
    schema_files: list[str] = []
    failopen_files: list[str] = []
    for path in skill_local_files:
        if path.name == "conftest.py":
            continue
        source = rel_root(path)
        if source in excluded:
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if SCHEMA_QUESTION_RE.search(text) and SCHEMA_ASSERT_RE.search(text):
            schema_files.append(source)
        if FAILOPEN_ASSERT_RE.search(text):
            failopen_files.append(source)
    candidate_set = {rel_root(path) for path in candidate_files}
    sig = {
        "schema_conformance_signal": bool(schema_files),
        "fail_closed_signal": bool(failopen_files),
        "schema_conformance_confirmed_by_reviewer": False,
        "signal_sources_schema": "; ".join(schema_files) if schema_files else "none",
        "signal_sources_fail_closed": "; ".join(failopen_files) if failopen_files else "none",
        "fixture_type_signal": "not_assessed",
        "signal_scope": "skill_local_scripts_tests_only",
        "repo_level_candidates_present": sorted(
            source for source in candidate_set if source.startswith("scripts/tests/")
        ),
    }
    return sig, sorted(set(schema_files) | set(failopen_files))


def run_row(entry_id: str, check_only: bool = False) -> dict[str, object]:
    results: dict[str, object] = {"run_exit": None}
    install_cmd = [sys.executable, "scripts/ci_test_matrix.py", "install", entry_id]
    if check_only:
        install_cmd.append("--check")
    command = [sys.executable, "scripts/ci_test_matrix.py", "run", entry_id]
    for label, cmd in (("install", install_cmd), ("run", command)):
        try:
            completed = subprocess.run(cmd, cwd=ROOT, check=False, capture_output=True, text=True)
            results[f"{label}_exit"] = completed.returncode
            results[f"{label}_stderr_tail"] = "\n".join(completed.stderr.splitlines()[-10:])
        except OSError as exc:  # pragma: no cover - defensive
            results[f"{label}_exit"] = 127
            results[f"{label}_stderr_tail"] = str(exc)
        if label == "install" and results["install_exit"] != 0:
            break
    check_flag = " --check" if check_only else ""
    results["recorded_command"] = (
        f"python3 scripts/ci_test_matrix.py install {entry_id}{check_flag} && "
        f"python3 scripts/ci_test_matrix.py run {entry_id}"
    )
    return results


def repo_scripts_row_check() -> dict[str, object]:
    """Record the repo-scripts row (integration coverage for mapped repo-level tests)."""
    return run_row("repo-scripts", check_only=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", action="append", help="restrict to one skill id (repeatable)")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    parser.add_argument(
        "--skip-run", action="store_true", help="structural analysis only; no test execution"
    )
    args = parser.parse_args(argv)

    production = load_index()
    only = set(args.skill or [])

    collection: list[dict[str, object]] = []
    for skill in production:
        skill_id = str(skill["id"])
        if only and skill_id not in only:
            continue
        verification = skill.get("verification")
        current = "unknown"
        if isinstance(verification, dict):
            current = str(verification.get("unit_tests", "unknown"))
        skill_dir = ROOT / "skills" / skill_id
        scripts = executable_scripts(skill_dir)
        if not scripts:
            collection.append(
                {
                    "skill_id": skill_id,
                    "current_value": current,
                    "proposed_value": "not_applicable",
                    "scripts": [],
                    "gap_reasons": [],
                    "reason": "no executable helper scripts (out of scope for #496 step 1)",
                }
            )
            continue
        locations = test_locations(skill_dir)
        mapping, unmatched = propose_mapping(scripts, locations)
        all_candidate_tests = sorted(
            {str(path) for group, paths in locations.items() for path in paths}
        )
        mapped_tests = sorted({rel for rels in mapping.values() for rel in rels})
        mapped_skill_local = [rel for rel in mapped_tests if rel.startswith(f"skills/{skill_id}/")]
        mapped_repo_level = [rel for rel in mapped_tests if rel.startswith("scripts/tests/")]
        self_file = ROOT / "scripts" / "tests" / "test_backfill_unit_tests_evidence.py"
        sig, signal_sources = signals(
            [(ROOT / rel) for rel in mapped_skill_local],
            [(ROOT / rel) for rel in mapped_repo_level],
            excluded_files=[self_file],
        )
        row: dict[str, object] = {}
        if not args.skip_run:
            row = run_row(skill_id)
            if mapped_repo_level:
                row["repo_scripts_row"] = repo_scripts_row_check()
        proposed = "gap"
        reasons: list[str] = []
        if unmatched:
            reasons.append(f"{len(unmatched)} executable script(s) without a mapped test module")
        if not mapping:
            reasons.append("no test modules proposed for any executable script")
        if args.skip_run:
            reasons.append("test execution skipped (--skip-run); exit status not recorded")
        else:
            if row.get("install_exit") != 0:
                reasons.append("recorded ci_test_matrix install did not exit 0")
            if row.get("run_exit") != 0:
                reasons.append("recorded ci_test_matrix row did not exit 0")
            if mapped_repo_level:
                repo_row = row.get("repo_scripts_row", {})
                if repo_row.get("install_exit") != 0 or repo_row.get("run_exit") != 0:
                    reasons.append("mapped repo-scripts install/run did not both exit 0")
        if mapping and not sig["fail_closed_signal"]:
            reasons.append("no assertion-shaped error-path/fail-closed test among mapped tests")
        if mapping and not sig["schema_conformance_signal"]:
            reasons.append("no assertion-shaped output-schema conformance test among mapped tests")
        if not reasons:
            proposed = "passed"
        entry: dict[str, object] = {
            "skill_id": skill_id,
            "current_value": current,
            "proposed_value": proposed,
            "unmatched_scripts": unmatched,
            "script_test_mapping": mapping,
            "candidate_tests": all_candidate_tests,
            "signals": sig,
            "row_execution": row,
            "gap_reasons": reasons,
        }
        collection.append(entry)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "assessment_date": date.today().isoformat(),
        "command": "python3 scripts/backfill_unit_tests_evidence.py",
        "issue": "https://github.com/tradermonty/claude-trading-skills/issues/496",
        "note": "proposals are advisory; reviewer confirmation required before baseline edits. Note: script_test_mapping counts repo-level suites for coverage-mapping purposes only; signals are always skill-local (see signal_scope).",
        "results": collection,
    }
    target = args.output_dir / "unit_tests_evidence.json"
    target.write_text(json.dumps(output, indent=2, sort_keys=False), encoding="utf-8")

    print(json.dumps({"results_written": str(target), "skills": len(collection)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
