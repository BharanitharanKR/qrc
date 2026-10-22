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

## Harness and results

The driver scripts that run each scenario, and the committed result summaries under `results/`,
come next. Raw traces go to `results/raw/`, which is git-ignored.
