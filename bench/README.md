# bench

Benchmark corpus and profiling harness (Phase 0, [docs/phase-0.md](../docs/phase-0.md)).

## Corpus

[`corpus.toml`](corpus.toml) pins each workspace to an exact commit and toolchain and records
the size facts the plan asks for (manifests, `Cargo.lock` packages, Rust files and lines,
integration-test files, build scripts), the files the `touch-leaf` and `touch-core` scenarios
edit, and the system libraries a fresh machine needs. `[nightly]` is the pinned nightly for the
`baseline-nightly` configuration.

From the repository root:

```sh
python3 scripts/check-corpus.py bench/corpus.toml                 # shape of the file
python3 scripts/check-corpus.py --verify-pins bench/corpus.toml   # and each ref still names its pin (CI)
```

The harness re-measures the size facts at run time and reports them beside the recorded ones;
the recorded ones are there so results can be read without fetching anything.

## Harness

[`run.py`](run.py) runs the plan's scenarios (§2) for one workspace under one configuration
(§3) and appends one JSON object per run to a results file in the plan's schema (§4).
Standard library Python; cargo and rustup do the work.

```sh
python3 bench/run.py --list
python3 bench/run.py ripgrep                                   # every scenario, baseline-stable, 3 runs, -j = cores
python3 bench/run.py ripgrep --config baseline-nightly --runs 5 --jobs 8
python3 bench/run.py loams --scenarios cold-build,noop --work /data/qrc-bench
python3 bench/analyze.py bench/results/*.jsonl                 # the §5 report, as markdown
```

Prerequisites: [rustup](https://rustup.rs) (the pinned toolchains install on first use),
Python 3.11 or newer, git, and for `baseline-nightly` measureme's `summarize`
(`cargo install --git https://github.com/rust-lang/measureme --tag 12.0.3 summarize`). Each
workspace is fetched at its pin into the work directory (`--work`, default `~/qrc-bench`,
never `/tmp`), and the harness refuses a checkout at any other commit or with local edits.
Budget the disk the corpus notes give: zed and loams need tens of gigabytes each.

What each run does, in order: one untimed `cargo fetch --locked` per invocation, so no timed
run downloads anything; `cargo clean` for the cold scenarios or an untimed warm-up build for
the warm ones; the timed cargo command with an explicit `-j`, `--offline` and `--timings`;
for the `touch-*` scenarios a comment line appended to the corpus file and reverted after.
`deps-only` is not a separate build: it is read off the cold build's timings as the moment the
last dependency unit finished, which is what a dependency cache could remove.

What is recorded, per run (the machine appears under a label, the CPU model by default, never the hostname): wall time; the build's user and system CPU time (rusage of the
children); the peak resident memory of the whole process tree, sampled twice a second with
`ps`, and the largest single process; the unit count, test-binary count and target directory
size; toolchain, linker and machine facts; and the time share per hypothesis of design §2:

| Share | Source |
|---|---|
| `deps`, `proc_macro_build_rs` | cargo's unit data (the JSON its `--timings` report embeds): slot-seconds of dependency units, and of build scripts and proc-macro crates |
| `front_end`, `codegen` | the workspace's own units, split by the sections cargo records when rustc hands over metadata |
| `link`, `debuginfo` | rustc's `-Zself-profile` (nightly only), summed over the workspace's crates with measureme's `summarize`; taken out of `codegen`, which contains them in the sections view. The timed command never carries the flag, since writing the profile inflates wall time; for the cold scenarios the harness runs one extra, untimed, profiled build and reads these from it |
| `idle` | job slots with nothing to run, integrated over cargo's concurrency samples |

Shares are fractions of the build's slot capacity (wall time x jobs), so with idle they add
up to about 1.0; `share_sum` records how close. `sections_all_crates` gives the front end
versus codegen split over every compiled crate, dependencies included.

### Fields beyond the plan's schema

The record carries every field of the plan's example (§4) and these beside them:

| Field | Meaning |
|---|---|
| `commit`, `recorded_at` | the workspace commit measured, and when (UTC) |
| `toolchain.name`, `.cargo`, `.host` | the rustup toolchain, `cargo -V`, and the host triple |
| `machine.label`, `.arch`, `.disk` | a label for the machine (the CPU model unless `--label` is given; never the hostname), the architecture, SSD or HDD |
| `max_process_rss_mib`, `rss_samples` | the largest single process (rusage), and how many tree samples `peak_rss_mib` rests on |
| `cpu_utilization` | (user + sys) / (wall x jobs) |
| `workspace_share` | slot-seconds of the workspace's own units, before the front end / codegen split |
| `share_sum` | the sum of the non-null shares; how close the attribution comes to 1.0 |
| `sections_all_crates` | front end and codegen as fractions of compile time over every crate, dependencies included |
| `phase_all_crates`, `self_profile` | nightly only: the self-profile split over every crate, and the profiled build's crate count and wall time |
| `timings_summary` | cargo's own summary rows (total, fresh and dirty units, max concurrency, total time) |
| `test_run` | `cold-test` only: the test run itself, timed after the build (`cargo nextest run` when installed, else `cargo test`) |
| `derived_from`, `dep_slot_seconds` | `deps-only` only: the cold build it was read from, and the dependency units' slot-seconds |
| `error`, `log` | a failed run: what failed and where cargo's log is |

Raw traces (the timing report, self-profile summaries, cargo's log) go to `results/raw/`, which is
git-ignored; the binary self-profile traces are deleted once summarized unless `--keep-traces` is
given, since they run to gigabytes over a full set; only the JSONL files under `results/` and the §5 report are committed.
[`analyze.py`](analyze.py) reports medians and the run-to-run spread, flags scenarios whose
spread is above 5 percent (the plan then asks for 5 runs), and writes the time-share table,
a bar and the top three hypotheses per workspace. `python3 bench/analyze.py --self-test`
checks it against [`tests/fixture.jsonl`](tests/fixture.jsonl); CI runs that.
