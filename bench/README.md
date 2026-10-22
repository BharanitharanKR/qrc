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
| `cache`, `cache_backend`, `cache_version` | the build cache the run went through (`none`, `sccache` or `kache`), where it keeps entries (`local`, or a remote type such as `s3`; `none` without a cache), and the tool's `--version` (null without one); see [Phase 2](#phase-2-cache-scenarios) |
| `cache_stats` | cache scenarios only, for the timed build: `hits`, `misses`, `errors`, `hit_rate` (hits / (hits + misses)); `read_s` and `write_s`, the time the cache spent restoring hits and storing entries; `stop_s`, how long the server or daemon took to stop afterwards (kache's daemon finishes queued work such as uploads first; sccache has written each entry before the compile returns); and each tool's own extra counters |
| `error`, `log` | a failed run: what failed and where cargo's log is |

Raw traces (the timing report, self-profile summaries, cargo's log) go to `results/raw/`, which is
git-ignored; the binary self-profile traces are deleted once summarized unless `--keep-traces` is
given, since they run to gigabytes over a full set; only the JSONL files under `results/` and the §5 report are committed.
[`analyze.py`](analyze.py) reports medians and the run-to-run spread, flags scenarios whose
spread is above 5 percent (the plan then asks for 5 runs), and writes the time-share table,
a bar and the top three hypotheses per workspace. `python3 bench/analyze.py --self-test`
checks it against [`tests/fixture.jsonl`](tests/fixture.jsonl), and `python3 bench/run.py --self-test` runs
the measurement path on real subprocesses and checks the size facts and share arithmetic; CI runs both.

## Phase 2: cache scenarios

Design §5 benchmarks kache against sccache, and the [shared-cache plan](../docs/tailscale-shared-cache.md)
§5 lists the runs. `--cache sccache` or `--cache kache` builds through that cache: `RUSTC_WRAPPER`
is the tool found on `PATH`, and `CARGO_INCREMENTAL=0`, since neither tool caches incremental units.

```sh
python3 bench/run.py ripgrep --cache sccache                   # the four cache scenarios, 3 runs each
python3 bench/run.py loams --cache kache --scenarios cache-hit,cache-partial --jobs 4
```

| Scenario | Before the timed `cargo build` | Plan row |
|---|---|---|
| `cache-cold` | cache directory emptied, target cleaned; the build fills the cache | design §5 "cold": filling an empty cache |
| `cache-hit` | cache filled (one untimed build, unless this invocation filled it already), target cleaned | cold build, full cache hit |
| `cache-partial` | as `cache-hit`, then a comment appended to `touch_core` (reverted after) | partial hit after a typical change |
| `cache-warm-local` | cache filled, target warm, a comment appended to `touch_leaf` | warm local rebuild |

"Cold build, no cache" is `cold-build` without `--cache`. It keeps the workspace's own incremental
setting (on in the dev profile); for a like-for-like row, export `CARGO_INCREMENTAL=0` for that run
and say so with the results. The cache scenarios need `--cache`, and `--cache` runs only them.
`analyze.py` reports each cache and backend as a setting of its own, with a hit-rate column.

- **Isolation.** Each invocation gets an empty cache directory under the work directory, removed
  when it ends, with a 200 GB limit so nothing is evicted mid-run. sccache gets its own server
  socket (`SCCACHE_SERVER_UDS`), so a server you already run is never used, and `SCCACHE_CONF` points
  at an empty file. kache gets `KACHE_CACHE_DIR`, an empty `KACHE_CONFIG` and no host config, plus
  `KACHE_SEED_NEW_TARGETS=0` (as in kache's own benchmark) and `KACHE_AUTO_RECOVER_MIN_FREE_BYTES=0`
  (kache's CI default). A config file you export yourself is kept.
- **Server state.** The sccache server or kache daemon is stopped at the start of every run and
  after the untimed fill, so no timed run inherits one from another run. Right before the timer,
  sccache's counters are zeroed (which starts its server) and kache's daemon is started. In
  `cache-warm-local` the one the untimed warm-up build started stays up, as in an edit loop.
- **Counters.** `sccache --show-stats --stats-format json` after the build (checked against sccache
  0.18.0), or the difference of kache's `report --format json` totals before and after it (its
  `docs/commands/report.schema.json`, checked against kache 1.2.2). kache calls a compile that joined
  another compile of the same key a duplicate; it counts as a miss here, as in kache's own hit rate.
  Then the server or daemon is stopped; `stop_s` is how long that took, which for kache includes
  work its daemon finishes after the build, such as uploads.
- **Remote backends.** `SCCACHE_BUCKET`, `KACHE_S3_*` and the rest of your environment pass through
  untouched, and the record says `cache_backend: "s3"`. kache's daemon ignores `KACHE_S3_*` from its
  environment, so put a kache remote in a file and export `KACHE_CONFIG`. The harness never empties a
  remote: for a cold remote, use a fresh key prefix. With kache and a remote, `cache-hit` and
  `cache-partial` also empty kache's local store first, so hits come from the remote, as on a fresh
  CI runner. A run whose sccache server stored entries anywhere else is recorded as failed.
- **CPU and memory under sccache.** rustc runs inside the sccache server (its default mode), outside
  cargo's process tree, so `user_s`, `sys_s` and `peak_rss_mib` leave those compiles out. Compare
  wall time.
