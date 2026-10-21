# qrcd

The orchestrator daemon (design §6): reads cargo's unit graph, schedules units with cache-aware
and critical-path scheduling, pipelines on `.rmeta`, and holds warm state between invocations.
Also the cache client. Zig or Rust; the choice is made after the Phase 2 cache benchmark
(design §9 and §16).

Planned crate name: `qrcd`. Empty for now.
