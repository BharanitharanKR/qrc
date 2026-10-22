# Phase 0: benchmark corpus and profiling harness

**Status:** Plan only. Nothing here has been run yet.

Phase 0 gates everything else in the [design](design.md): no layer gets built until we know where
debug-build time actually goes for real workloads (design §2). The exit criterion is a
**time-share breakdown per workload**: for each corpus workspace, what fraction of wall time and
CPU time goes to each of the seven hypotheses in design §2.

## 1. Benchmark corpus

Three to five real workspaces of varied size. Each one is pinned to an exact commit and toolchain,
recorded in [`bench/corpus.toml`](../bench/corpus.toml), so runs are repeatable.

| Workspace | Why it is in the corpus | Rough shape |
|---|---|---|
| [`ostrium-labs/loams`](https://github.com/ostrium-labs/loams) | Large Rust workspace with heavy CI (about 100 workspace manifests, about 1,400 packages in `Cargo.lock`, a pinned stable toolchain, around 30 GitHub Actions workflows). It is our own, so we can also try CI changes on it | Large, dependency-heavy services, many test binaries |
| [`BurntSushi/ripgrep`](https://github.com/BurntSushi/ripgrep) | Small, well-known workspace; a floor for "how much can overhead matter" | Small, few dependencies |
| [`nushell/nushell`](https://github.com/nushell/nushell) | Mid-to-large workspace with many crates and plugins | Medium to large, many crates |
| [`zed-industries/zed`](https://github.com/zed-industries/zed) | Very large application workspace; the Rust project's cg_clif goal benchmarks on it, so our numbers can be compared with theirs | Very large application, many crates |
| *(optional)* one proc-macro-heavy service, for example a workspace built on `axum` + `sqlx` + `serde` | Stresses hypothesis 2 (proc macros and `build.rs`) | Medium |

Rules for the corpus:
- Do not clone anything as part of writing this plan. When Phase 0 starts, the harness fetches
  each workspace at its pinned commit into a working directory outside `/tmp`, and the repos are
  never committed here.
- Record each workspace's crate count, `Cargo.lock` package count, lines of Rust, and number of
  test binaries, so results can be read against size.
- If a workspace needs system libraries (zed does), list them in `bench/corpus.toml` so runs are
  reproducible on a fresh machine.

## 2. Scenarios

Each workspace runs each scenario at least 3 times (5 when variance is above 5 percent); report
the median and the spread.

| Scenario | Command shape | What it models |
|---|---|---|
| `cold-build` | clean target dir, `cargo build` | Cold CI debug build |
| `cold-test` | clean target dir, `cargo test --no-run`, then the test run timed separately (`cargo nextest run` where the workspace supports it) | Cold CI build + tests |
| `check` | clean target dir, `cargo check` | Cost of the verify lane |
| `noop` | second `cargo build` with no changes | Fixed overhead (fingerprinting, scheduling) |
| `touch-leaf` | edit a leaf crate (a binary's `main.rs`), rebuild | Typical local edit loop |
| `touch-core` | edit a widely depended-on workspace crate, rebuild | Worst-case local edit |
| `deps-only` | build dependencies only (for example via `cargo chef cook` or a dependency-only manifest) | The share that a dependency cache layer could remove |

## 3. Configurations

Phase 0 measures the **baseline** only; Phase 1 reruns the same harness with the Layer 1 bundle.
The harness should still accept a named configuration so the Phase 1 runs are a flag away.

- `baseline-stable`: the workspace's own toolchain and profile, unchanged.
- `baseline-nightly`: the same on a pinned nightly (needed for `-Zself-profile` and
  `--unit-graph`). Report the stable-to-nightly difference so it is not mistaken for a gain later.
- Phase 1 configurations (named now, not run in Phase 0): `cranelift`, `line-tables-only`,
  `debug-0`, `mold`, `wild`, `lld`, `threads-N`, `share-generics`, and combinations.

## 4. Profiling harness

All tools below are standard; nothing new is built in Phase 0 except a thin driver script in
`bench/`.

| Tool | What it gives | Notes |
|---|---|---|
| `cargo build --timings` | Per-unit start/end times, codegen vs. front-end split per crate, CPU concurrency over time | Writes an HTML report under `target/cargo-timings/`. On nightly, `-Zunstable-options --timings=json` also gives machine-readable output; prefer it for analysis |
| `RUSTFLAGS="-Zself-profile=<dir>"` (nightly) | Per-query time inside rustc: parse, expansion, resolution, typeck, borrowck, MIR, monomorphization, LLVM, linking | Summarize with `summarize` and `crox` from [measureme](https://github.com/rust-lang/measureme). Add `-Zself-profile-events=default,args` only for spot runs, it is heavy |
| `cargo build --unit-graph -Zunstable-options` (nightly) | The unit graph: the critical path and the theoretical parallelism | Input for Layer 3 (`qrcd`) design |
| `/usr/bin/time -v` (Linux) or `/usr/bin/time -l` (macOS) | Wall time, user + system CPU time, peak RSS | Wrap the whole cargo invocation |
| Link timing | Time spent in the linker per binary | From `-Zself-profile` `link_*` events, or by wrapping the linker with a timing shim |
| `cargo metadata` | Crate count, dependency count, proc-macro and `build.rs` count | Static facts about each workspace |

### What to record for every run

Always (design §11): wall time, CPU time, peak RSS, and the per-phase breakdown. In full:

- workspace, pinned commit, scenario, configuration, run index;
- toolchain (`rustc -vV`, `cargo -V`), linker and version;
- machine: CPU model, core count, `-j` used, RAM, disk type, OS and kernel;
- wall time, user CPU time, system CPU time, CPU utilization (CPU time / (wall time x cores));
- peak RSS of the whole build;
- time share per hypothesis from design §2: dependency compilation, proc macros + `build.rs`
  (compile and run), front end, monomorphization + codegen, debug info, linking, scheduling idle
  time (cores idle while work was waiting);
- number of units built, number of test binaries linked, target dir size after the build.

### Output format

One JSON object per run, appended to `bench/results/<date>-<machine>.jsonl`. Raw traces
(self-profile data, timings HTML) go to `bench/results/raw/`, which is git-ignored; only the
JSONL and the summaries are committed.

```json
{
  "schema": 1,
  "workspace": "ostrium-labs/loams",
  "commit": "<sha>",
  "scenario": "cold-build",
  "config": "baseline-nightly",
  "run": 1,
  "toolchain": { "rustc": "<rustc -vV first line>", "linker": "<name version>" },
  "machine": { "cpu": "<model>", "cores": 16, "jobs": 8, "ram_gib": 64, "os": "<os kernel>" },
  "wall_s": 0.0,
  "user_s": 0.0,
  "sys_s": 0.0,
  "peak_rss_mib": 0,
  "units": 0,
  "test_binaries": 0,
  "target_dir_mib": 0,
  "share": {
    "deps": 0.0,
    "proc_macro_build_rs": 0.0,
    "front_end": 0.0,
    "codegen": 0.0,
    "debuginfo": 0.0,
    "link": 0.0,
    "idle": 0.0
  }
}
```

The `share` fields are fractions of wall time and should sum to about 1.0; the analysis script
reports how far off they are, since the attribution from `--timings` and `-Zself-profile` overlaps.

## 5. Deliverable

A `docs/benchmarks/phase-0.md` report (written when Phase 0 runs) with, per workspace:
- the time-share breakdown as a table and a stacked bar;
- the top three hypotheses by share, which decides what Phase 1 to 4 work comes first;
- the run-to-run variance, and anything that could not be measured.

## 6. Practical rules

- Keep build parallelism bounded (`-j` set explicitly and recorded); some machines hang on fully
  parallel builds.
- Never build in `/tmp` (often a small RAM tmpfs); use a disk-backed working directory.
- Do not use any build cache in the baseline runs (`RUSTC_WRAPPER` unset). Cache comparisons are
  Phase 2.
- Treat every number as provisional until it reproduces on a second machine.
