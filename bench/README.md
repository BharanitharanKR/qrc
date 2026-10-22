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

The harness measures the same facts from the checkout, with the definitions in the file's header,
records them in every result as `size_facts`, and warns when they differ from `corpus.toml`. The
checkout is always at the pinned commit, so a difference means the recorded value is wrong.

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
| `size_facts` | the corpus's size facts measured from the checkout (see [Corpus](#corpus)) |
| `test_run` | `cold-test` only: the test run itself, timed after the build (`cargo nextest run` when installed, else `cargo test`) |
| `derived_from`, `dep_slot_seconds` | `deps-only` only: the cold build it was read from, and the dependency units' slot-seconds |
| `error`, `log` | a failed run: what failed and where cargo's log is |

Raw traces (the timing report, self-profile summaries, cargo's log) go to `results/raw/`, which is
git-ignored; the binary self-profile traces are deleted once summarized unless `--keep-traces` is
given, since they run to gigabytes over a full set; only the JSONL files under `results/` and the §5 report (with its charts) are committed.
[`analyze.py`](analyze.py) reports medians and the run-to-run spread, flags scenarios whose
spread is above 5 percent (the plan then asks for 5 runs), and writes the time-share table,
a stacked bar and the top three hypotheses per workspace. The bar is text by default;
`--svg-dir DIR` also draws each cold scenario's bar as an SVG file in `DIR`, and with `--out`
the report embeds those charts by links relative to the report file (for instance
`--out docs/benchmarks/phase-0.md --svg-dir docs/benchmarks/phase-0`). `python3 bench/analyze.py --self-test`
checks it against [`tests/fixture.jsonl`](tests/fixture.jsonl), and `python3 bench/run.py --self-test` runs
the measurement path on real subprocesses and checks the size facts and share arithmetic; CI runs both.

## Running the harness in CI

The large workspaces do not fit on a laptop, so
[`.github/workflows/bench.yml`](../.github/workflows/bench.yml) runs the harness on a GitHub-hosted
Linux runner. It runs only when someone starts it, which needs write access to the repository.
Each run measures one workspace under one configuration:

```sh
gh workflow run bench.yml -R ostrium-labs/qrc -f workspace=nushell -f config=baseline-stable
gh workflow run bench.yml -R ostrium-labs/qrc -f workspace=ripgrep -f config=baseline-nightly -f scenarios=cold-build,noop -f runs=3
gh run list -R ostrium-labs/qrc -w bench.yml     # the run id
```

| Input | Default | Meaning |
|---|---|---|
| `workspace` | required | `loams`, `ripgrep`, `nushell` or `zed` |
| `config` | `baseline-stable` | or `baseline-nightly` |
| `runs` | `5` | runs per scenario |
| `jobs` | `4` | cargo `-j` |
| `scenarios` | `all` | comma-separated, as for `run.py --scenarios` |
| `runner` | `ubuntu-24.04` | the runner label; give a larger runner's label for zed or loams |
| `label` | `gha-<runner>` | the machine label recorded in the results and used in the file name |

A standard runner has 4 vCPUs, 16 GB of RAM and 14 GB of SSD storage
([GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)),
hence `-j 4`. Before building, the workflow deletes preinstalled toolchains the harness does not
use (.NET, Android, GHC, CodeQL, Docker images) and prints `df -h` before and after. The corpus
notes budget 30 GB of disk for loams and 40 GB for zed, so those two may need a larger runner.
The workflow also installs the workspace's `system_libs` with apt, and for `baseline-nightly`
measureme's `summarize`.

The harness step stops after 300 minutes and the job after 330, inside GitHub's
[6-hour job limit](https://docs.github.com/en/actions/reference/limits), so the report and the
upload still run. The harness writes each run to the results file as it finishes, so a step cut
short keeps the runs before it. Split a long set across dispatches with `scenarios`.

GitHub-hosted runners are shared virtual machines, and the CPU model behind a label can change
from one run to the next. Every record carries the CPU model under `machine.cpu`, and
`analyze.py` flags scenarios whose spread is above 5 percent; check the spread before reading
the medians.

When the run ends, its summary page shows the report. An artifact named
`bench-<workspace>-<config>-<run id>-<attempt>` is kept for 30 days and holds:

- `<date>-<label>.jsonl`, the results;
- `report.md`, the report for this run alone;
- `raw/<workspace>/<config>/<scenario>/run-<n>/`, cargo's `cargo-timing.html` and logs. A failed
  run's `log` field names a path on the runner; the same log is here.

To commit the results, append the JSONL to the file of the same name under `bench/results/`. The
plan keeps one file per date and machine ([docs/phase-0.md](../docs/phase-0.md), §4), so two
workspaces measured on the same day under the same label share a file. From the repository root:

```sh
run=1234567890                                   # the run id from `gh run list`
gh run download "$run" -R ostrium-labs/qrc -D ~/qrc-bench-download/"$run"
f=$(find ~/qrc-bench-download/"$run" -name '*.jsonl')
mkdir -p bench/results
cat "$f" >> "bench/results/$(basename "$f")"
python3 bench/analyze.py bench/results/*.jsonl   # the report over every committed file
git add bench/results/*.jsonl
git commit -s -m "bench: nushell baseline-stable on gha-ubuntu-24.04"
```

Commit only the JSONL. The `raw/` files stay out of git, as for a local run, and the report is
regenerated from the committed results.
