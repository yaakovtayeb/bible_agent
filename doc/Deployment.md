# CI/CD Deployment Guide — Biblical News Agent

Step-by-step guide to implement a CI/CD framework for this project.

---

## Prerequisites

- GitHub account with a repository for this project
- AWS CLI configured (`aws configure`)
- Python 3.10+
- `git` installed

---

## Step 0 — Set Up GitHub Repository

1. Create a new repository on GitHub (e.g., `biblical-news-agent`)
2. Initialize git locally and push:

```bash
git init
git remote add origin https://github.com/<your-username>/biblical-news-agent.git
git add .
git commit -m "chore: initial commit"
git push -u origin main
```

3. In GitHub, go to Settings > Branches and add a branch protection rule for `main`:
   - Require pull request before merging
   - Require status checks to pass (add after CI is set up)

---

## Step 1 — Restructure the Project

Move from a flat layout to a structured one.

Target layout:

```
agent1_project/
├── agent/
│   ├── __init__.py
│   ├── agent.py
│   ├── tools/
│   │   ├── __init__.py
│   │   └── bible.py
│   └── prompts/
│       └── system_prompt.txt
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   └── test_tools.py
│   └── integration/
│       └── test_agent.py
├── doc/
│   └── Deployment.md
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
└── README.md
```

Actions:
- Move `agent1.py` to `agent/agent.py`
- Extract `fetch_bible_text` to `agent/tools/bible.py`
- Extract `SYSTEM_PROMPT` to `agent/prompts/system_prompt.txt`
- Update `.bedrock_agentcore.yaml` entrypoint to `agent/agent.py`

---

## Step 2 — Extract Secrets from Code

Currently hardcoded values that must move to environment variables:

| Hardcoded value | Environment variable |
|---|---|
| Model ARN | `MODEL_ID` |
| `BiblicalNewsAgent_CloudWatch_mem-dPJBb549Dg` | `MEMORY_ID` |
| `us-east-1` | `AWS_REGION` |

In `agent/agent.py`, replace hardcoded values with:

```python
MODEL_ID = os.environ["MODEL_ID"]
MEMORY_ID = os.environ["MEMORY_ID"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
```

Create a `.env.example` file (never commit `.env`):

```
MODEL_ID=arn:aws:bedrock:us-east-1:...
MEMORY_ID=...
AWS_REGION=us-east-1
```

Add `.env` to `.gitignore`.

---

## Step 3 — Add `pyproject.toml` and `requirements-dev.txt`

`pyproject.toml` centralizes linting and test configuration.

`requirements-dev.txt` adds test and quality tools:

```
pytest>=8.0
pytest-cov>=4.0
pytest-mock>=3.12
moto[s3]>=5.0
ruff>=0.3.0
mypy>=1.9.0
pre-commit>=3.6.0
bandit[toml]>=1.7.0
python-dotenv>=1.0.0
```

---

## Step 4 — Write Unit Tests for the Tool

Test `fetch_bible_text` with mocked HTTP — no real network calls, no cost.

File: `tests/unit/test_tools.py`

Tests to cover:
- Returns text on successful HTTP response
- Returns error string on network failure
- Truncates output to 3000 characters

Run with:

```bash
pytest tests/unit -v
```

---

## Step 5 — Add `pre-commit` Hooks

Install and configure hooks that run on every `git commit`:

```bash
pip install pre-commit
pre-commit install
```

Hooks to configure in `.pre-commit-config.yaml`:
- `ruff` — lint and format
- `detect-private-key` — catch accidentally committed keys
- `check-added-large-files` — prevent committing model files
- `bandit` — security scan on `agent/`
- `detect-secrets` — scan for hardcoded credentials

---

## Step 6 — GitHub Actions CI Pipeline

File: `.github/workflows/ci.yml`

Triggers on every pull request to `main`.

Jobs (run in parallel):
1. `lint` — ruff, mypy, bandit
2. `test` — pytest unit + integration tests with mocked AWS

To authenticate CI with AWS, use OIDC (no stored long-lived keys):

1. In AWS, create an IAM OIDC provider for GitHub Actions
2. Create an IAM role with trust policy for your repo
3. Add the role ARN as a GitHub secret: `AWS_CI_ROLE_ARN`

---

## Step 7 — GitHub Actions Deploy Pipeline

File: `.github/workflows/deploy.yml`

Triggers on push to `main` (after CI passes).

Steps:
1. Configure AWS credentials via OIDC
2. Install `bedrock-agentcore-starter-toolkit`
3. Run `agentcore configure` with environment variables (not secrets)
4. Run `agentcore deploy --auto-update-on-conflict`
5. Run smoke test: `agentcore invoke '{"news": "test"}'`
6. Tag the commit with the deploy timestamp

Add the deploy role ARN as a GitHub secret: `AWS_DEPLOY_ROLE_ARN`

---

## Step 8 — Cost Guards (Optional but Recommended)

Add a `CostGuard` class to `agent/agent.py` that caps per-invocation:
- Max tokens: configurable via `MAX_TOKENS_PER_INVOCATION` env var
- Max tool calls: configurable via `MAX_TOOL_CALLS` env var
- Max wall-clock seconds: configurable via `MAX_SECONDS` env var

---

## Implementation Order

| Step | Effort | Value |
|---|---|---|
| 0 — GitHub setup | Low | Required |
| 1 — Restructure | Low | Unlocks everything |
| 2 — Extract secrets | Low | Security critical |
| 3 — Dev tooling | Low | Quality foundation |
| 4 — Unit tests | Medium | Fast feedback |
| 5 — pre-commit | Low | Prevents bad commits |
| 6 — CI pipeline | Medium | Automated validation |
| 7 — Deploy pipeline | Medium | Automated deployment |
| 8 — Cost guards | Low | Production safety |
