# Decisions log

Why things are the way they are: each entry gives the decision, the reason and
what was turned down. Newest first. What shipped is in the
[pass map](pass-map.md).

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
