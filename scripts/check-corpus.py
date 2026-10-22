#!/usr/bin/env python3
"""Check bench/corpus.toml, the Phase 0 benchmark corpus (docs/phase-0.md §1).

Every workspace must be pinned to an exact commit and toolchain and carry the
size facts the plan asks for, so that a run on another machine can be read
against the same inputs. With --verify-pins, each `ref` is resolved at the
remote with `git ls-remote` and must point at the recorded commit.

    python3 scripts/check-corpus.py bench/corpus.toml
    python3 scripts/check-corpus.py --verify-pins bench/corpus.toml   # CI

Standard library only (Python 3.11 or newer for tomllib).
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import tomllib

SCHEMA = 1
COMMIT = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
NIGHTLY = re.compile(r"^nightly-\d{4}-\d{2}-\d{2}$")
TOOLCHAIN = re.compile(r"^(stable|\d+\.\d+\.\d+)$")
COUNTS = (
    "manifests",
    "lock_packages",
    "rs_files",
    "rs_lines",
    "integration_tests",
    "build_scripts",
)
REQUIRED = (
    "name",
    "repo",
    "ref",
    "commit",
    "date",
    "toolchain",
    "shape",
    "why",
    "touch_leaf",
    "touch_core",
    "system_libs",
) + COUNTS
OPTIONAL = ("notes",)


class Problems:
    def __init__(self, path: str) -> None:
        self.path = path
        self.count = 0

    def add(self, message: str) -> None:
        self.count += 1
        print(f"::error file={self.path}::{message}")


def check_workspace(ws: dict, index: int, problems: Problems) -> None:
    label = ws.get("name") or f"workspace #{index}"
    for key in REQUIRED:
        if key not in ws:
            problems.add(f"{label}: missing `{key}`")
    for key in ws:
        if key not in REQUIRED and key not in OPTIONAL:
            problems.add(f"{label}: unknown key `{key}`")
    name = ws.get("name", "")
    if not isinstance(name, str) or not NAME.match(name):
        problems.add(f"{label}: `name` must match {NAME.pattern}")
    repo = ws.get("repo", "")
    if not isinstance(repo, str) or not repo.startswith("https://") or repo.endswith("/"):
        problems.add(f"{label}: `repo` must be an https URL without a trailing slash")
    if not isinstance(ws.get("ref"), str) or not ws.get("ref"):
        problems.add(f"{label}: `ref` must be a tag or branch name")
    commit = ws.get("commit", "")
    if not isinstance(commit, str) or not COMMIT.match(commit):
        problems.add(f"{label}: `commit` must be the full 40-character SHA")
    if not isinstance(ws.get("date"), dt.date):
        problems.add(f"{label}: `date` must be a TOML date (the commit's date)")
    toolchain = ws.get("toolchain", "")
    if not isinstance(toolchain, str) or not TOOLCHAIN.match(toolchain):
        problems.add(f"{label}: `toolchain` must be `stable` or an exact version such as 1.97.1")
    for key in ("shape", "why"):
        if not isinstance(ws.get(key), str) or not ws.get(key):
            problems.add(f"{label}: `{key}` must be a non-empty string")
    for key in COUNTS:
        value = ws.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.add(f"{label}: `{key}` must be a non-negative integer")
    for key in ("touch_leaf", "touch_core"):
        value = ws.get(key, "")
        if not isinstance(value, str) or value.startswith("/") or not value.endswith(".rs"):
            problems.add(f"{label}: `{key}` must be a repository-relative path to a .rs file")
    libs = ws.get("system_libs")
    if not isinstance(libs, list) or not all(isinstance(x, str) and x for x in libs):
        problems.add(f"{label}: `system_libs` must be a list of package names (may be empty)")
    if "notes" in ws and not isinstance(ws["notes"], str):
        problems.add(f"{label}: `notes` must be a string")


def verify_pin(ws: dict, problems: Problems) -> None:
    """The ref at the remote must point at the recorded commit.

    An annotated tag lists twice in ls-remote: the tag object and, with `^{}`,
    the commit it peels to. Either may equal the pin.
    """
    label = ws["name"]
    ref = ws["ref"]
    try:
        out = subprocess.run(
            ["git", "ls-remote", "--tags", "--heads", ws["repo"], ref, f"{ref}^{{}}"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        problems.add(f"{label}: git ls-remote {ws['repo']} {ref} failed: {e}")
        return
    shas = {line.split("\t")[0] for line in out.splitlines() if line.strip()}
    if not shas:
        problems.add(f"{label}: `{ref}` does not exist at {ws['repo']}")
    elif ws["commit"] not in shas:
        problems.add(
            f"{label}: `{ref}` resolves to {', '.join(sorted(shas))}, not the pinned {ws['commit']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", nargs="?", default="bench/corpus.toml")
    parser.add_argument(
        "--verify-pins",
        action="store_true",
        help="resolve every ref at its remote and compare it with the pinned commit",
    )
    args = parser.parse_args()
    problems = Problems(args.path)

    try:
        with open(args.path, "rb") as f:
            corpus = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        problems.add(f"cannot read: {e}")
        return 1

    if corpus.get("schema") != SCHEMA:
        problems.add(f"`schema` must be {SCHEMA}")
    if not isinstance(corpus.get("checked"), dt.date):
        problems.add("`checked` must be a TOML date: when the facts were read")
    nightly = corpus.get("nightly", {})
    if not isinstance(nightly, dict) or not NIGHTLY.match(str(nightly.get("channel", ""))):
        problems.add("`[nightly].channel` must be a dated channel such as nightly-2026-10-15")
    elif not isinstance(nightly.get("rustc"), str) or not nightly["rustc"].startswith("rustc "):
        problems.add("`[nightly].rustc` must be the first line of `rustc -vV` for that channel")

    workspaces = corpus.get("workspace", [])
    if not isinstance(workspaces, list) or not workspaces:
        problems.add("at least one [[workspace]] is required")
        workspaces = []
    for index, ws in enumerate(workspaces, start=1):
        if not isinstance(ws, dict):
            problems.add(f"workspace #{index} is not a table")
            continue
        check_workspace(ws, index, problems)
    names = [ws.get("name") for ws in workspaces if isinstance(ws, dict)]
    for name in sorted({n for n in names if names.count(n) > 1}):
        problems.add(f"duplicate workspace name `{name}`")

    if args.verify_pins and problems.count == 0:
        for ws in workspaces:
            verify_pin(ws, problems)

    if problems.count:
        print(f"{problems.count} problem(s) in {args.path}", file=sys.stderr)
        return 1
    print(f"ok: {len(workspaces)} workspaces in {args.path}" + (" (pins verified)" if args.verify_pins else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
