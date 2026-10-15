## What and why

<!-- What does this change, and why? Link the issue it closes, if any. -->

## Checklist

- [ ] Every commit is signed off (`git commit -s`), certifying the [DCO](https://developercertificate.org/); see [CONTRIBUTING.md](../CONTRIBUTING.md).
- [ ] `ruff check .`, `yamllint --strict .` and the tests with coverage pass locally (CI runs the same, plus the workflow, Dockerfile, dependency and secret scanners).
- [ ] New behaviour has tests; a bug fix has a regression test (the test policy in [CONTRIBUTING.md](../CONTRIBUTING.md)).
- [ ] User-visible changes are in `CHANGELOG.md` under "Unreleased", and the README, `docs/` and `data/varken.example.ini` are updated.
- [ ] No secrets, hostnames or addresses are committed.
