# CI Guide — What Runs, What Blocks, and How to Fix It

## What runs on every pull request to main

Two jobs run in parallel. Both must pass before a PR can be merged.

### 1. Lint

Runs: `ruff check .`, `ruff format --check .`, `bandit -c pyproject.toml -r agent/`

What it checks:
- `ruff check` — import order, unused variables, undefined names, and common Python errors
- `ruff format` — consistent code formatting (line length, spacing, quotes)
- `bandit` — security vulnerabilities in `agent/` (hardcoded secrets, unsafe calls, weak crypto)

### 2. Unit Tests

Runs: `pytest tests/unit -v`

What it checks:
- All tests under `tests/unit/`
- Runs with `LOCAL_MODE=true` and dummy env vars — no real AWS calls
- AWS credentials are still configured via OIDC in case a test needs them

---

## If a check fails — where to look

### Ruff lint failure
Run locally:
```bash
ruff check . --fix
```
Ruff will auto-fix most issues. Review the diff before committing.

### Ruff format failure
Run locally:
```bash
ruff format .
```

### Bandit failure
Read the output carefully. Each issue shows:
- Severity (Low / Medium / High)
- CWE reference
- File and line number

Fix the code if it's a real issue. If it's a false positive (e.g. `random.sample` for non-security use),
suppress it with a comment on the flagged line:
```python
result = random.sample(items, 3)  # nosec B311
```

### Unit test failure
Run locally:
```bash
pytest tests/unit -v
```
The output shows exactly which test failed and why. Fix the code or the test, then push again.

---

## How to add a new required check

### Option 1 — Add a new step to an existing job

Open `.github/workflows/ci.yml` and add a step under `lint` or `test`:

```yaml
- name: My new check
  run: my-tool --check .
```

The step name does not need to be added to branch protection — it blocks the job automatically if it fails.

### Option 2 — Add a new job

Add a new job block in `ci.yml`:

```yaml
  my-new-job:
    name: My New Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run check
        run: my-tool .
```

Then go to GitHub > Settings > Branches > Edit main rule > Require status checks > add "My New Check".
GitHub will show it as an option after the workflow runs once with the new job.

### Option 3 — Add a pre-commit hook

Add the tool to `.pre-commit-config.yaml`. It will run locally on every commit.
To also enforce it in CI, add it as a step in `ci.yml`.

---

## Current required status checks on main

| Check | Job | Tool |
|---|---|---|
| Lint | lint | ruff, bandit |
| Unit Tests | test | pytest |
