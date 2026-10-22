# Contributing to qrc

Thanks for your interest. qrc is at the design stage (see the [README](README.md)), so the most
useful contributions right now are review of the [design](docs/design.md), corrections with
sources, and help with the [Phase 0 benchmarks](docs/phase-0.md).

## Discuss before large pull requests

Open an issue before starting anything larger than a small fix (a new layer, a new tool, a change
to the design's direction, or more than a few hundred lines). Agreeing on the approach first saves
everyone time. Small fixes such as typos, broken links or a corrected source can go straight to a
pull request.

## Upstream first

qrc builds on existing work (rustc, cargo, `rustc_codegen_cranelift`, TPDE, sccache, kache,
mold, wild). If a problem belongs in one of those projects, report or fix it there and link it
from the qrc issue. We would rather contribute upstream than fork.

## Developer Certificate of Origin (DCO)

Every commit must be signed off under the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
Signing off means you certify that you wrote the change, or otherwise have the right to submit it
under this project's licences. Add the sign-off with `git commit -s`, which appends a line like:

```
Signed-off-by: Your Name <you@example.com>
```

The name and email must match the commit author. A CI check (`DCO sign-off`) rejects pull
requests with unsigned commits. To fix an unsigned commit, amend it with `git commit --amend -s`
(or `git rebase --signoff` for several commits) and force-push your branch.

## Code review

Every pull request gets one AI reviewer, never two. In this repository it is
[Greptile](https://www.greptile.com), configured in [`.greptile/`](.greptile/config.json); it
reviews pull requests into `main` when they are opened (comment `@greptileai` to re-run it).
CodeRabbit's automatic review is off ([`.coderabbit.yaml`](.coderabbit.yaml)); it runs only if
someone comments `@coderabbitai review`. A maintainer reviews after the bot. Answer each bot
comment; it is fine to disagree and say why.

## Licence of contributions

qrc is dual-licensed under [MIT](LICENSE-MIT) OR [Apache-2.0](LICENSE-APACHE). Unless you
explicitly state otherwise, any contribution intentionally submitted for inclusion in qrc by you,
as defined in the Apache-2.0 licence, shall be dual licensed as above, without any additional
terms or conditions.

Do not add code or dependencies under licences that are incompatible with MIT OR Apache-2.0.

## Writing style

Plain, clear English. When the design states a fact about another project, cite the source. When
something is a goal rather than a measurement, say so.
