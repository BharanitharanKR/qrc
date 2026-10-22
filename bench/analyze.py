#!/usr/bin/env python3
"""Summarize Phase 0 results (docs/phase-0.md §5): medians and spread per scenario, the
time-share breakdown per workspace as a table and a bar, and the top hypotheses.

    python3 bench/analyze.py bench/results/*.jsonl            # markdown on stdout
    python3 bench/analyze.py --out docs/benchmarks/phase-0.md bench/results/*.jsonl
    python3 bench/analyze.py --self-test                       # the fixture under bench/tests

Standard library only. Reads the JSON objects bench/run.py writes, one per line.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHARE_KEYS = ("deps", "proc_macro_build_rs", "front_end", "codegen", "debuginfo", "link", "idle")
HYPOTHESIS = {
    "deps": "1. cold dependency compilation",
    "proc_macro_build_rs": "2. proc macros and build.rs",
    "front_end": "3. front end",
    "codegen": "4. monomorphization and codegen",
    "debuginfo": "5. debug info",
    "link": "6. linking",
    "idle": "7. scheduling gaps (idle slots)",
}
SCENARIO_ORDER = ("cold-build", "cold-test", "check", "noop", "touch-leaf", "touch-core", "deps-only")
BAR = "█"


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        for n, line in enumerate(p.read_text().splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{p}:{n}: {e}")
    return rows


def median(values: list[float]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def spread(values: list[float]) -> float | None:
    """(max - min) / median, the run-to-run variance the plan asks to report."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    med = statistics.median(vals)
    return (max(vals) - min(vals)) / med if med else None


def fmt(v: float | None, digits: int = 1, unit: str = "") -> str:
    return "n/a" if v is None else f"{v:.{digits}f}{unit}"


def pct(v: float | None) -> str:
    return "n/a" if v is None else f"{100 * v:.0f}%"


def setting(r: dict) -> str:
    """The configuration a run belongs to, including the machine and -j: runs from different
    computers or job counts are separate baselines, never one median."""
    m = r.get("machine") or {}
    return f"{r['config']} on {m.get('label', 'unknown machine')} (-j {m.get('jobs', '?')})"


def group(rows: list[dict]) -> dict:
    """{workspace: {setting: {scenario: [runs]}}}; failed runs stay in their scenario."""
    g: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        g[r["workspace"]][setting(r)][r["scenario"]].append(r)
    return g


def scenario_table(by_scenario: dict) -> list[str]:
    lines = ["| Scenario | Runs | Wall (median) | Spread | CPU time (user+sys) | CPU use | Peak RSS | Units | Test binaries |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(by_scenario, key=lambda x: SCENARIO_ORDER.index(x) if x in SCENARIO_ORDER else 99):
        runs = [r for r in by_scenario[s] if "error" not in r]
        errors = len(by_scenario[s]) - len(runs)
        if not runs:
            lines.append(f"| {s} | 0 ({errors} failed) | | | | | | | |")
            continue
        walls = [r["wall_s"] for r in runs]
        cpu = [None if r.get("user_s") is None else r["user_s"] + r["sys_s"] for r in runs]
        sp = spread(walls)
        # The plan's rule: above 5 percent, run 5. Not for sub-second scenarios, where the
        # spread is scheduler noise measured in tens of milliseconds.
        wide = sp is not None and sp > 0.05 and (max(walls) - min(walls)) > 0.2
        flag = " (above 5%: run 5)" if wide and len(runs) < 5 else ""
        lines.append(
            f"| {s} | {len(runs)}{' (+%d failed)' % errors if errors else ''} | {fmt(median(walls), 2, ' s')} | "
            f"{pct(sp)}{flag} | {fmt(median(cpu), 1, ' s')} | {pct(median([r.get('cpu_utilization') for r in runs]))} | "
            f"{fmt(median([r.get('peak_rss_mib') for r in runs]), 0, ' MiB')} | {fmt(median([r.get('units') for r in runs]), 0)} | "
            f"{fmt(median([r.get('test_binaries') for r in runs]), 0)} |"
        )
    return lines


def share_rows(runs: list[dict]) -> dict[str, float | None]:
    out = {}
    for k in SHARE_KEYS:
        out[k] = median([(r.get("share") or {}).get(k) for r in runs])
    return out


def bar(shares: dict[str, float | None], width: int = 60) -> str:
    parts, legend = [], []
    for k in SHARE_KEYS:
        v = shares.get(k)
        if v:
            n = max(1, round(v * width))
            parts.append(BAR * n)
            legend.append(f"{k} {pct(v)}")
    return "".join(parts) + "\n" + "  " + " · ".join(legend)


def report(rows: list[dict], preamble: str = "") -> str:
    g = group(rows)
    out = ["# Phase 0 baseline: where debug-build time goes", ""]
    if preamble.strip():
        out += [preamble.strip(), ""]
    machines = {(r["machine"].get("label"), r["machine"].get("cpu"), r["machine"].get("cores"), r["machine"].get("jobs"), r["machine"].get("ram_gib"), r["machine"].get("os"))
                for r in rows if "machine" in r}
    out.append("Machines: " + "; ".join(f"{h}: {c}, {n} cores, -j {j}, {ram} GiB, {o}" for h, c, n, j, ram, o in sorted(machines, key=str)))
    out.append("")
    out.append("Shares are fractions of the build's slot capacity (wall time x jobs), so they add up to about 1.0 together "
               "with idle; `front_end` and `codegen` are the workspace's own crates, split by cargo's unit sections; "
               "`link` and `debuginfo` need the nightly self-profile and are n/a on stable. The deviation of the sum "
               "from 1.0 is the time neither source attributes. Timed runs never carry `-Zself-profile`; on nightly, "
               "the phase data comes from one extra, untimed, profiled build per cold scenario.")
    out.append("")
    for ws in sorted(g):
        out.append(f"## {ws}")
        for config in sorted(g[ws]):
            by_scenario = g[ws][config]
            commits = {r.get("commit", "")[:8] for r in sum(by_scenario.values(), [])}
            tcs = {r["toolchain"]["rustc"] for r in sum(by_scenario.values(), []) if "toolchain" in r}
            out.append(f"### {config}")
            out.append(f"Commit {', '.join(sorted(commits))}; {'; '.join(sorted(tcs))}")
            out.append("")
            out.extend(scenario_table(by_scenario))
            out.append("")
            for scenario in ("cold-build", "cold-test"):
                runs = [r for r in by_scenario.get(scenario, []) if "error" not in r and r.get("share")]
                if not runs:
                    continue
                shares = share_rows(runs)
                sums = [r.get("share_sum") for r in runs if r.get("share_sum") is not None]
                out.append(f"Time share, {scenario} (median of {len(runs)} runs; shares sum to {fmt(median(sums), 2)}):")
                out.append("")
                out.append("| Hypothesis | Share |")
                out.append("|---|---|")
                for k in SHARE_KEYS:
                    out.append(f"| {HYPOTHESIS[k]} | {pct(shares[k])} |")
                out.append("")
                out.append("```")
                out.append(bar(shares))
                out.append("```")
                top = sorted(((v, k) for k, v in shares.items() if v is not None), reverse=True)[:3]
                out.append("Top hypotheses: " + ", ".join(f"{HYPOTHESIS[k]} ({pct(v)})" for v, k in top) + ".")
                all_crates = [r.get("sections_all_crates") for r in runs if r.get("sections_all_crates")]
                if all_crates:
                    fe = median([a["front_end"] for a in all_crates])
                    cg = median([a["codegen"] for a in all_crates])
                    out.append(f"Across every compiled crate, dependencies included: front end {pct(fe)}, codegen {pct(cg)} of compile time.")
                out.append("")
        out.append("")
    failed = [r for r in rows if "error" in r]
    if failed:
        out.append("## Failed runs")
        for r in failed:
            out.append(f"- {r['workspace']} {r['config']} {r['scenario']} run {r['run']}: {r['error']}")
        out.append("")
    return "\n".join(out)


def self_test() -> int:
    fixture = HERE / "tests" / "fixture.jsonl"
    rows = load([fixture])
    g = group(rows)
    runs = g["example/ws"]["baseline-stable on fixture (-j 8)"]["cold-build"]
    walls = [r["wall_s"] for r in runs]
    assert median(walls) == 10.0, median(walls)
    assert abs(spread(walls) - 0.2) < 1e-9, spread(walls)
    shares = share_rows(runs)
    assert shares["deps"] == 0.5 and shares["idle"] == 0.1, shares
    assert shares["link"] is None
    text = report(rows, "Status: fixture.")
    assert text.splitlines()[2] == "Status: fixture.", text.splitlines()[:4]
    assert "| cold-build | 3 | 10.00 s | 20% (above 5%: run 5) |" in text, text
    assert "1. cold dependency compilation | 50%" in text
    assert "Failed runs" in text and "run 1: cargo exited 101" in text
    # A failed run is counted in its own scenario row, under the same workspace and setting.
    assert "| check | 0 (1 failed) |" in text, text
    # A second machine is a second baseline: its 30 s run does not move the first one's median.
    assert "baseline-stable on fixture-2 (-j 8)" in g["example/ws"], list(g["example/ws"])
    assert median([r["wall_s"] for r in g["example/ws"]["baseline-stable on fixture-2 (-j 8)"]["cold-build"]]) == 30.0
    # Idle is hypothesis 7 and can rank: on the second machine it is the largest share.
    assert "Top hypotheses: 7. scheduling gaps (idle slots) (70%)" in text, text
    print("analyze.py self-test: ok")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, help="write the markdown here instead of stdout")
    ap.add_argument("--preamble", type=Path, help="markdown placed under the title (status, caveats), kept across regenerations")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    paths = args.results or sorted((HERE / "results").glob("*.jsonl"))
    if not paths:
        sys.exit("no results files")
    text = report(load(paths), args.preamble.read_text() if args.preamble else "")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
