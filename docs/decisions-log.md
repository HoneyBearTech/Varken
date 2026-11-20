# Decisions log

Why things are the way they are: each entry gives the decision, the reason and
what was turned down. Newest first. What shipped is in the
[pass map](pass-map.md).

## 2026-11-20: Renovate merges its own pull requests

Job `renovate-automerge` (#66).

**Decision.** Renovate merges its pull requests itself once every check passes,
majors included; new versions wait 3 days, security fixes and image rebuilds
don't, on the model homelab-atlas already uses. Kept manual: the fuzz workflow's
Python hold stays (#65). `platformAutomerge` is false ("Allow auto-merge" is
off).

**Why.** The owner asked for every repo with Renovate to merge its updates
automatically (2026-11-20) and chose this model, majors included, over keeping
majors manual.

**Not done.** Repository settings and branch rules (owner only) and workflows
are unchanged. A group merges automatically only when every update in it may, so
each manual exception gets its own pull request.

**Review findings.** Fixed: stale docs that still promised a manual review or
named Dependabot, and (where it applied) exceptions that sat inside the update
group. None declined. Nothing merges until the review rule on `main` no longer
needs an approving or code-owner review (an owner setting).

## 2026-11-20: match the fuzz Python rule on the dependency's name

Job `fuzz-python-rule`.

**Decision.** The rule in `renovate.json` that holds `.github/workflows/fuzz.yml`
on Python 3.14 matches with `matchDepNames: ["python"]`.

**Why.** Renovate records `actions/setup-python`'s version with the dependency
name `python` but the package name `actions/python-versions`;
`matchPackageNames` compares the package name, so the old rule never applied
and #64 moved the fuzz workflow to 3.15.

**Not done.** Moving the fuzz runtime to 3.15 (waits for the fuzzing library).

**Review findings.** None declined.
