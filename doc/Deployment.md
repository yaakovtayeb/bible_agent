# CI/CD Deployment Guide — Biblical News Agent

This guide walks through building a production-grade CI/CD pipeline for an AWS Bedrock AgentCore agent.
Each step is self-contained. A customer can follow this from zero to automated deployments.

---

## Prerequisites

- GitHub account with a repository for this project
- AWS CLI configured (`aws configure`)
- Python 3.10+
- `git` installed

---

## Step 0 — Set Up GitHub Repository

> Why: Every CI/CD pipeline needs a remote Git repository as its source of truth.
> GitHub will be the trigger point — every push or pull request kicks off automation.

1. Create a new repository on GitHub (e.g., `biblical-news-agent`)
2. Initialize git locally and push:

```bash
git init
git remote add origin git@github-personal:<your-username>/biblical-news-agent.git
git add .
git commit -m "chore: initial commit"
git push -u origin main
```

3. In GitHub, go to Settings > Branches and add a branch protection rule for `main`:
   - Require pull request before merging
   - Require status checks to pass (add after CI is set up)

> Branch protection ensures no one (including you) can push directly to `main` without passing CI.
> This is the foundation of a safe deployment pipeline.

---

## Step 1 — Restructure the Project

> Why: A flat single-file layout does not scale. CI/CD tools expect a structured project
> with clear separation between source code, tests, and configuration.

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

> Why: Hardcoded values in source code are a security risk. Anyone with repo access
> can see your model ARNs, memory IDs, and region. CI/CD pipelines inject these at
> runtime via environment variables, keeping secrets out of the codebase entirely.

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

> `.env.example` documents what variables are needed without exposing real values.
> New team members clone the repo, copy `.env.example` to `.env`, fill in their values, and run locally.

---

## Step 3 — Add `pyproject.toml` and `requirements-dev.txt`

> Why: CI needs to install the exact same tools locally and in the pipeline.
> `pyproject.toml` centralizes linting and test configuration so every developer
> and every CI run uses identical settings.

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

> Why: CI pipelines run tests automatically on every commit. Without tests, CI is just
> a deployment button with no safety net. Unit tests catch bugs before they reach AWS.
> They run in milliseconds with no real network calls and no cost.

Test `fetch_local_bible` with mocked HTTP.

File: `tests/unit/test_tools.py`

Tests to cover:
- Returns text on successful HTTP response
- Returns error string on network failure
- Truncates output to 10_000 characters

Run with:

```bash
pytest tests/unit -v
```

---

## Step 5 — Add `pre-commit` Hooks

> Why: Pre-commit hooks are your first line of defense. They run on your local machine
> before a commit is even created, catching issues before they ever reach GitHub.
> This is faster and cheaper than catching them in CI.

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

> Why: This is the core of CI. Every pull request to `main` automatically triggers
> lint, type checks, and tests. No human needs to remember to run them.
> A PR cannot be merged unless all checks pass — this is enforced by branch protection from Step 0.

File: `.github/workflows/ci.yml`

Triggers on every pull request to `main`.

Jobs (run in parallel):
1. `lint` — ruff, mypy, bandit
2. `test` — pytest unit + integration tests with mocked AWS

To authenticate CI with AWS, use OIDC (no stored long-lived keys):

> OIDC (OpenID Connect) lets GitHub Actions assume an AWS IAM role temporarily using
> a short-lived token. This is more secure than storing `AWS_ACCESS_KEY_ID` as a secret
> because there are no long-lived credentials that can be leaked or rotated.

1. In AWS, create an IAM OIDC provider for GitHub Actions
2. Create an IAM role with trust policy for your repo
3. Add the role ARN as a GitHub secret: `AWS_CI_ROLE_ARN`

---

## Step 7 — GitHub Actions Deploy Pipeline

> Why: This is CD — Continuous Deployment. Every merge to `main` automatically deploys
> the agent to AWS. No manual steps, no forgotten deployments, no "works on my machine".
> The pipeline is the single path to production.

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

> The smoke test in step 5 is critical. It invokes the live agent immediately after deploy
> and fails the pipeline if the agent does not respond correctly. This means a bad deploy
> is caught within seconds and can be rolled back automatically.

---

## Step 8 — Cost Guards (Optional but Recommended)

> Why: Agents can run indefinitely if not bounded. In a CI/CD context where deploys are
> automated and invocations can be triggered by pipelines, runaway costs are a real risk.
> These guards cap spending at the code level, independent of AWS service limits.

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
