**Status: partial and provisional.** One workspace of the four (ripgrep), on one machine (an Apple
M3 laptop, 8 cores, 16 GiB, macOS), so these numbers are a first look at the
harness's output, not the Phase 0 exit criterion. loams, nushell and zed need a Linux machine with
more memory and disk (see [the corpus notes](../../bench/corpus.toml)), and the plan treats every
number as provisional until it reproduces on a second machine (§6). Regenerate this file with:

```sh
python3 bench/analyze.py --preamble docs/benchmarks/phase-0-preamble.md \
  --out docs/benchmarks/phase-0.md bench/results/*.jsonl
```

The runs: `python3 bench/run.py ripgrep --config <config> --runs 5 --jobs 8`, stable first, then
nightly, back to back on 2026-10-22.

**Run conditions.** The machine ran on battery, and other work (git checkouts, code searches) ran
on it at the same time, so the absolute times are noisier than a quiet machine would give: the
same stable cold build measured 7.4 s (median of 5) an hour earlier with less going on, and 9.0 s
here. Several scenarios have a spread above 5 percent even with 5 runs. The shares and the
ranking of hypotheses were the same in both sets; the wall times should be re-measured on a quiet
machine before anything is compared against them.

**Stable against nightly (§3).** The tables below put nightly's cold build at 11.7 s against
stable's 9.0 s. That gap is the order of the runs and the machine's load, not the toolchain: the
nightly set ran after the stable one, and its CPU time for the same work was higher run after
run. A check with the two interleaved (4 pairs, `cargo +<toolchain> clean` then
`cargo +<toolchain> --offline build --workspace -j 8`, a 45-second pause before each build) gave a
median wall time of 7.77 s for stable 1.99.1 and 7.06 s for nightly-2026-10-15, with the same CPU
time (21.9 s and 22.0 s user). Read the stable-to-nightly difference on this machine as zero.

ripgrep is the corpus's floor (§1): 59 packages in `Cargo.lock`, a cold build of 7 to 9 seconds here. What
it shows is how much of even a small build is spent outside the workspace's own code; it says
little about where a large workspace's time goes, which is what the other three are for.
