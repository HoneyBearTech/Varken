# Pass map

A short record of each piece of work on Varken: what shipped, or what a review
found, and where to look. Newest first. The reasons behind the choices are in
the [decisions log](decisions-log.md); what is planned next is in the
[roadmap](roadmap.md).

## 2026-11-20: `fuzz-python-rule`

The Renovate rule that keeps the fuzz workflow on Python 3.14 now matches
(`matchDepNames` instead of `matchPackageNames`), so Renovate's group
(#64) stops moving it to 3.15, which the fuzzing library doesn't support yet.
Proved with a Renovate dry run (3.15 offered before, nothing after) and by
running Renovate's own rule matching against the config. Security review
clear; code audit approved.
