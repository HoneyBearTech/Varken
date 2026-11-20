# Plan: fuzz-python-rule

## What Sean asked for

Look at PR #64 (Renovate's minor and patch group).

## What we found

- Every fuzz check on #64 fails: the group moves the fuzz workflow's Python
  from 3.14 to 3.15, and the fuzzing library has no build for 3.15 yet.
- `renovate.json` already has a rule to keep that workflow on 3.14, but it
  never applies. It matches `matchPackageNames: ["python"]`, while Renovate
  calls this dependency `python` only as its *name*; its package is
  `actions/python-versions`. A rule on the name (`matchDepNames`) matches.
- The other updates in #64 pass every other check.

## What we'll change

1. `renovate.json`: in the fuzz rule, match on the dependency's name
   (`matchDepNames`) instead of its package. Check: Renovate's config
   validator passes, and after the merge Renovate rebuilds #64 without the
   Python change, so its fuzz checks pass.
2. `docs/dependencies.md`: no wording change needed (it already says the fuzz
   runtime stays on 3.14); confirm it still matches.
3. Record the job in `docs/` (pass map, decisions log; created if missing).

## Who's on it

Engineer, Security Officer, Auditor. No Researcher (the cause is found).

## Risks

- None to the running app: this only changes which updates Renovate offers.
- Until this merges, merging #64 as it stands would break the fuzz checks on
  `main`.

## Out of scope

The other updates in #64 (they merge once Renovate rebuilds it), and moving
the fuzz runtime to 3.15 (waits for the fuzzing library).
