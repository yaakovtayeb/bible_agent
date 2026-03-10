# CI/CD for AI Agents: A Comprehensive Tutorial Using AWS AgentCore and Strands Agents

*March 2026 | Technical Reference Guide*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Background & Technology Overview](#background--technology-overview)
3. [Why CI/CD for AI Agents?](#why-cicd-for-ai-agents)
4. [Repository Structure & Git Best Practices](#repository-structure--git-best-practices)
5. [Git Hooks for Agent Development](#git-hooks-for-agent-development)
6. [Testing Strategies](#testing-strategies)
7. [CI Pipeline Design](#ci-pipeline-design)
8. [Deployment with `agentcore deploy`](#deployment-with-agentcore-deploy)
9. [Deployment Strategies: Blue/Green, Canary, Rollback](#deployment-strategies-bluegreen-canary-rollback)
10. [Monitoring & Observability](#monitoring--observability)
11. [Secrets Management](#secrets-management)
12. [Cost Controls](#cost-controls)
13. [Complete End-to-End Example](#complete-end-to-end-example)
14. [Conclusion](#conclusion)
15. [References](#references)

---

## Executive Summary

Building AI agents is only half the battle. Shipping them reliably, testing their behavior, monitoring their runtime performance, and rolling back when things go wrong—that's the other half. This tutorial provides a complete, opinionated guide to CI/CD (Continuous Integration and Continuous Deployment) for AI agents built with **Strands Agents** and deployed to **AWS AgentCore**.

By the end of this guide, you will have:

- A battle-tested **repository layout** for agent projects
- **Git hooks** that validate prompts, lint code, and run fast smoke tests before every commit
- A **multi-layer testing pyramid** covering unit tests, integration tests, and LLM behavior evaluations
- A full **GitHub Actions CI pipeline** and equivalent **AWS CodePipeline** configuration
- Automated `agentcore deploy` invocations, including **blue/green** and **canary** rollout patterns
- **CloudWatch GenAI observability** dashboards and alerting via OpenTelemetry
- **Secrets management** with AWS Secrets Manager and Parameter Store
- **Cost guardrails** using AWS Budgets and per-invocation tagging
- A **complete end-to-end example** tying everything together

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| AWS CLI | 2.x |
| `agentcore` CLI (`bedrock-agentcore-starter-toolkit`) | Latest |
| `strands-agents` | ≥ 0.1.6 |
| `bedrock-agentcore` SDK | 1.4.3 |
| GitHub Actions or AWS CodePipeline | — |

---

## Background & Technology Overview

### What is AWS AgentCore?

Amazon Bedrock AgentCore is AWS's managed hosting platform for AI agent runtimes. It handles:

- **Serverless compute** for agent execution (no container management needed with `direct_code_deploy`)
- **Automatic scaling** based on invocation demand
- **IAM-integrated security** through execution roles
- **Built-in OpenTelemetry instrumentation** for tracing and observability
- **Session management and memory** integration via AgentCore Memory

The `agentcore` CLI (from the `bedrock-agentcore-starter-toolkit` package) provides three commands that map directly to CI/CD stages:

```
agentcore configure   →  Build-time: define what to deploy
agentcore deploy      →  Deploy stage: upload & activate
agentcore invoke      →  Verify stage: smoke-test the deployed agent
```

With `--deployment-type direct_code_deploy`, AgentCore accepts a ZIP of your Python source — no Docker builds required in most cases, making CI pipelines dramatically simpler.

### What are Strands Agents?

Strands Agents is an open-source, model-driven Python SDK for building AI agents. Key properties:

- **Tool-first design**: Python functions become tools via `@tool` decorator
- **Model-agnostic**: Supports Amazon Bedrock (default), Anthropic, OpenAI, Gemini, Ollama, and more
- **Hooks system**: lifecycle events (`before_tool_call`, `after_model_call`, etc.) for testing and observability
- **Strands Evals SDK**: built-in evaluation framework with output, trajectory, and interaction evaluators
- **MCP support**: first-class integration with Model Context Protocol servers

```python
from strands import Agent, tool
from strands.models import BedrockModel

@tool
def get_account_balance(user_id: str) -> dict:
    """Retrieve account balance for a given user ID."""
    # ... implementation
    return {"user_id": user_id, "balance": 1234.56}

model = BedrockModel(model_id="us.anthropic.claude-sonnet-4-5", region_name="us-east-1")
agent = Agent(model=model, tools=[get_account_balance])
```

### The Standard `requirements.txt`

Every AgentCore agent project in this guide uses this baseline `requirements.txt`:

```
bedrock-agentcore-starter-toolkit
strands-agents-tools>=0.1.6
bedrock-agentcore==1.4.3
aws-opentelemetry-distro>=0.10.0
strands-agents[otel]>=0.1.6
requests>=2.32.0
beautifulsoup4>=4.12.0
opentelemetry-sdk>=1.29.0
opentelemetry-api>=1.29.0
boto3>=1.37.0
```

The `strands-agents[otel]` extra enables OpenTelemetry span emission, while `aws-opentelemetry-distro` configures the AWS OTLP exporter that connects to CloudWatch.

---

## Why CI/CD for AI Agents?

Traditional software CI/CD manages **deterministic code**: the same inputs always produce the same outputs. AI agents are fundamentally different — they are **non-deterministic systems** where the path to an answer may vary across runs. This creates unique challenges that CI/CD must address.

### The Four Dimensions of Agent Change

```
┌─────────────────────────────────────────────────────────────┐
│              Sources of Change in an Agent System           │
│                                                             │
│  1. CODE          Agent logic, tools, prompt templates      │
│  2. MODEL         LLM version, fine-tuning, model switch    │
│  3. DATA          Knowledge bases, RAG indexes, examples    │
│  4. ENVIRONMENT   IAM permissions, quotas, dependencies     │
│                                                             │
│  Traditional CI/CD handles (1). AI CI/CD must handle all 4  │
└─────────────────────────────────────────────────────────────┘
```

### Risks Without CI/CD

| Risk | Description | Impact |
|---|---|---|
| **Prompt regression** | A prompt change silently degrades accuracy | Silent quality drop |
| **Tool interface breakage** | Tool signature changes break agent's ability to invoke it | Runtime errors |
| **Model drift** | New LLM version changes reasoning patterns | Behavioral regression |
| **Permission creep** | IAM role changes block tool execution | Silent failures |
| **Runaway costs** | Unbounded agent loops multiply token costs | Budget overruns |
| **Sensitive data leakage** | Credentials accidentally in prompts or logs | Security incident |

### The AI Agent CI/CD Contract

A robust pipeline enforces these contracts at every merge:

1. **Static contract**: The code must lint, type-check, and pass unit tests
2. **Tool contract**: All tools must function correctly in isolation (mocked or real)
3. **Behavior contract**: The agent's key use cases must produce acceptable outputs
4. **Safety contract**: No PII, credentials, or disallowed content in outputs
5. **Performance contract**: Latency and cost per invocation must stay within bounds
6. **Deployment contract**: The agent must successfully deploy and respond to a smoke-test invocation

### Shift-Left Approach for Agents

```
Developer                 CI                    CD                 Production
    │                      │                     │                      │
    ├─ git commit          │                     │                      │
    │   └─ pre-commit hook │                     │                      │
    │      ├─ lint         │                     │                      │
    │      ├─ unit tests   │                     │                      │
    │      └─ prompt scan  │                     │                      │
    ├─────────────────────►│                     │                      │
    │                      ├─ full unit suite    │                      │
    │                      ├─ integration tests  │                      │
    │                      ├─ evals (LLM-judge)  │                      │
    │                      ├─ safety checks      │                      │
    │                      └─ build artifact ───►│                      │
    │                                            ├─ agentcore deploy    │
    │                                            ├─ smoke invoke        │
    │                                            ├─ canary rollout ────►│
    │                                            └─ full traffic ──────►│
```

This "shift-left" approach catches the majority of issues at the cheapest point — the developer's machine — before they ever reach a real LLM invocation.


---

## Repository Structure & Git Best Practices

### Recommended Directory Layout

A clean repository structure is the foundation of maintainable agent CI/CD. Here is the recommended layout for a single-agent project:

```
my-agent/
├── .agentcore/                  # AgentCore CLI configuration (auto-generated)
│   └── config.json
├── .github/
│   └── workflows/
│       ├── ci.yml               # Pull request checks
│       └── deploy.yml           # Merge-to-main deployment
├── agent/
│   ├── __init__.py
│   ├── agent.py                 # Main entrypoint (BedrockAgentCoreApp)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── search.py            # Individual tool modules
│   │   └── database.py
│   └── prompts/
│       ├── system_prompt.txt    # System prompt (version-controlled!)
│       └── task_prompts.py      # Prompt templates as Python strings
├── tests/
│   ├── conftest.py              # Shared fixtures, mocks
│   ├── unit/
│   │   ├── test_tools.py        # Pure unit tests for each tool
│   │   └── test_prompts.py      # Prompt validation tests
│   ├── integration/
│   │   ├── test_agent_local.py  # Agent tested locally w/ mocked LLM
│   │   └── test_tools_live.py   # Tools tested against real AWS services
│   └── evals/
│       ├── test_behavior.py     # LLM judge / eval suite
│       ├── golden_dataset.json  # Golden inputs/expected outputs
│       └── eval_config.yaml     # Evaluation thresholds
├── scripts/
│   ├── setup-hooks.sh           # Install git hooks for the team
│   └── run-evals.sh             # Convenience wrapper for eval suite
├── .pre-commit-config.yaml      # pre-commit hook configuration
├── requirements.txt             # Runtime dependencies
├── requirements-dev.txt         # Development + test dependencies
├── pyproject.toml               # Build config, linting, type checking
└── README.md
```

For **multi-agent** projects, use a monorepo with one directory per agent:

```
agents-monorepo/
├── agents/
│   ├── customer-support/        # Each agent = independent subtree
│   │   ├── agent/
│   │   ├── tests/
│   │   └── requirements.txt
│   └── data-analyst/
│       ├── agent/
│       ├── tests/
│       └── requirements.txt
├── shared/
│   ├── tools/                   # Shared tool library
│   └── evals/                   # Shared evaluation utilities
└── .github/workflows/
    └── ci.yml                   # Path-filtered CI per agent
```

### The `agent.py` Entry Point Pattern

AgentCore requires a single entrypoint file with a `BedrockAgentCoreApp` and a decorated `invoke` function. Here is the canonical structure:

```python
# agent/agent.py
import os
import json
import logging
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from .tools import search, database

# Enable OTEL tracing — required for CloudWatch GenAI observability
os.environ.setdefault("AGENT_OBSERVABILITY_ENABLED", "true")

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()

# Build the agent once at cold-start (not per-request)
model = BedrockModel(
    model_id=os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[search.web_search, database.query_records],
    system_prompt=open("agent/prompts/system_prompt.txt").read(),
)


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Main invocation handler for AgentCore."""
    prompt = payload.get("prompt", "")
    session_id = payload.get("session_id")

    if not prompt:
        return {"error": "Missing 'prompt' in payload"}

    logger.info("Invoking agent", extra={"session_id": session_id})
    result = agent(prompt)

    return {
        "response": str(result),
        "session_id": session_id,
    }


if __name__ == "__main__":
    app.run()
```

### `pyproject.toml` Configuration

Use `pyproject.toml` to centralize all tooling configuration:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "my-agent"
version = "0.1.0"
requires-python = ">=3.10"

[tool.ruff]
line-length = 100
target-version = "py310"
select = ["E", "F", "W", "I", "N", "UP"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.10"
strict = false
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = [
    "unit: fast, no external calls",
    "integration: requires AWS credentials",
    "eval: requires LLM invocation (slow, costs money)",
]
addopts = "-v --tb=short"

[tool.coverage.run]
source = ["agent"]
omit = ["tests/*"]
```

### `requirements-dev.txt`

```
# Testing
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.0
pytest-mock>=3.12
moto[bedrock]>=5.0           # AWS service mocking
strands-agents-evals>=0.1.0  # Strands evaluation SDK

# Code Quality
ruff>=0.3.0
mypy>=1.9.0
pre-commit>=3.6.0
bandit[toml]>=1.7.0          # Security linting

# Dev utilities
python-dotenv>=1.0.0
rich>=13.7.0
```

### Git Branch Strategy

```
main ──────────────────────────────────►  (protected, deploys to production)
  │
  ├── staging ───────────────────────►    (deploys to staging environment)
  │     │
  │     └── feature/TICKET-123-add-tool ► (PR target: staging)
  │
  └── hotfix/critical-fix ────────────►  (fast-track: merges to main + staging)
```

**Branch protection rules for `main`:**
- Require at least 1 PR review
- Require all CI checks to pass (unit tests, lint, safety scan)
- Require eval score ≥ threshold (checked via GitHub Actions status)
- No force pushes; no direct commits

### Commit Message Convention

Use [Conventional Commits](https://www.conventionalcommits.org/) for automated changelog generation and semantic versioning:

```
feat(tools): add web_search tool with DuckDuckGo backend
fix(prompt): correct system prompt instruction for tool use
test(evals): add golden dataset entries for edge cases
ci(pipeline): increase eval timeout to 5 minutes
docs: update README with new environment variables
perf(agent): cache embedding model at cold start
chore(deps): bump bedrock-agentcore to 1.4.3
```

This convention enables tools like `semantic-release` to auto-bump versions and generate changelogs:

```yaml
# .releaserc.json
{
  "branches": ["main"],
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    "@semantic-release/changelog",
    "@semantic-release/git"
  ]
}
```

---

## Git Hooks for Agent Development

Git hooks allow you to enforce standards at commit time — before any code reaches the CI pipeline. For AI agents, this is especially valuable because it can catch broken prompts, missing API keys in test configs, or import errors before they waste CI minutes.

### Setting Up `pre-commit`

The `pre-commit` framework manages hooks declaratively. Install it once, then everyone on the team runs `pre-commit install` to activate the hooks.

```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg  # Also install commit-msg hook
```

### `.pre-commit-config.yaml`

```yaml
repos:
  # ─── Standard code quality ───────────────────────────────────────────
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.7
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: detect-private-key           # Catches accidentally committed keys
      - id: check-added-large-files
        args: [--maxkb=500]              # Prevent accidentally committing large model files

  # ─── Security scanning ───────────────────────────────────────────────
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.8
    hooks:
      - id: bandit
        args: [-c, pyproject.toml]
        files: ^agent/

  # ─── Secrets detection ───────────────────────────────────────────────
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: [--baseline, .secrets.baseline]

  # ─── Type checking ───────────────────────────────────────────────────
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        files: ^agent/
        additional_dependencies:
          - strands-agents>=0.1.6
          - bedrock-agentcore==1.4.3

  # ─── Agent-specific hooks ─────────────────────────────────────────────
  - repo: local
    hooks:
      - id: validate-prompts
        name: Validate prompt templates
        language: python
        entry: python scripts/validate_prompts.py
        files: ^agent/prompts/
        pass_filenames: true

      - id: fast-unit-tests
        name: Run unit tests (fast subset)
        language: python
        entry: pytest tests/unit -x -q --tb=short
        pass_filenames: false
        always_run: false
        stages: [pre-push]             # Only on push, not every commit

  # ─── Commit message validation ───────────────────────────────────────
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.2.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        args: [feat, fix, test, ci, docs, perf, chore, refactor, build]
```

### Prompt Validation Script

Catching bad prompt templates before commit is one of the highest-value hooks for agent projects:

```python
#!/usr/bin/env python3
# scripts/validate_prompts.py
"""
Validates prompt template files for common issues:
- Unmatched template variables {like_this}
- Excessive length (may hit context limits)
- Hardcoded credentials or PII patterns
- Required section headers
"""
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = ["## Role", "## Instructions"]
MAX_TOKENS_ESTIMATE = 4000  # ~16,000 chars / 4 chars per token
SENSITIVE_PATTERNS = [
    r"AKIA[A-Z0-9]{16}",           # AWS Access Key ID
    r"(?i)password\s*=\s*['\"][^'\"]+['\"]",
    r"\b\d{3}-\d{2}-\d{4}\b",      # SSN pattern
]

def validate_prompt_file(path: Path) -> list[str]:
    errors = []
    content = path.read_text(encoding="utf-8")

    # Check template variable balance
    open_vars = re.findall(r"\{(?!\{)[^}]+\}", content)
    if open_vars:
        # Check these are intentional placeholders
        unresolved = [v for v in open_vars if not v.strip("{}").isupper()]
        if unresolved:
            errors.append(f"Potentially unresolved template vars: {unresolved[:5]}")

    # Length check
    char_count = len(content)
    if char_count > MAX_TOKENS_ESTIMATE * 4:
        errors.append(
            f"Prompt too long ({char_count} chars, ~{char_count//4} tokens). "
            f"Consider splitting."
        )

    # Sensitive data check
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, content):
            errors.append(f"Potential sensitive data detected (pattern: {pattern[:30]})")

    # Required sections (for system prompts only)
    if "system_prompt" in path.name:
        for section in REQUIRED_SECTIONS:
            if section not in content:
                errors.append(f"Missing required section: '{section}'")

    return errors


def main():
    files = [Path(f) for f in sys.argv[1:] if f.endswith((".txt", ".md", ".py"))]
    found_errors = False

    for path in files:
        if not path.exists():
            continue
        errors = validate_prompt_file(path)
        if errors:
            found_errors = True
            print(f"❌ {path}:")
            for e in errors:
                print(f"   • {e}")
        else:
            print(f"✅ {path}: OK")

    sys.exit(1 if found_errors else 0)


if __name__ == "__main__":
    main()
```

### Custom `pre-push` Hook: Smoke Test

Beyond `pre-commit`, a `pre-push` hook can run a quick local smoke test to verify the agent loads without errors:

```bash
#!/bin/bash
# .git/hooks/pre-push  (or managed via pre-commit stages: [pre-push])
set -e

echo "🔍 Running pre-push smoke test..."

# Verify agent imports without error
python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from agent.agent import app
    print('✅ Agent module loads successfully')
except Exception as e:
    print(f'❌ Agent load failed: {e}')
    sys.exit(1)
"

# Run only the unit tests (fast, no LLM calls)
echo "🧪 Running unit tests..."
pytest tests/unit -q --tb=short -x

echo "✅ Pre-push checks passed"
```

Install it via the setup script:

```bash
#!/bin/bash
# scripts/setup-hooks.sh
pip install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
pre-commit install --hook-type pre-push
echo "✅ Git hooks installed"
```


---

## Testing Strategies

Testing AI agents requires a multi-layered approach. Unlike traditional software, agents make LLM calls that cost money and return non-deterministic results. The goal is to push as many tests as possible into fast, cheap, deterministic layers, and reserve expensive LLM-based evaluations for the most impactful checks.

### The Agent Testing Pyramid

```
        ┌─────────────────────┐
        │   LLM EVALUATIONS   │  Slowest, most expensive
        │   (Strands Evals)   │  ~minutes, real LLM calls
        ├─────────────────────┤
        │  INTEGRATION TESTS  │  Medium speed
        │  (mocked LLM + real │  ~seconds, AWS service calls
        │   AWS services)     │
        ├─────────────────────┤
        │    UNIT TESTS       │  Fastest, free
        │  (pure Python,      │  ~milliseconds
        │   fully mocked)     │
        └─────────────────────┘
```

### Layer 1: Unit Tests

Unit tests cover individual components in complete isolation. The LLM is **always** mocked at this layer.

#### Tool Unit Tests

```python
# tests/unit/test_tools.py
import pytest
from unittest.mock import patch, MagicMock
from agent.tools.database import query_records


class TestQueryRecords:
    """Unit tests for the database query tool."""

    def test_returns_empty_list_when_no_results(self):
        with patch("agent.tools.database.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_table.query.return_value = {"Items": []}
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = query_records(user_id="user123", limit=10)

            assert result == {"records": [], "count": 0}

    def test_returns_records_on_success(self):
        with patch("agent.tools.database.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_table.query.return_value = {
                "Items": [
                    {"id": "r1", "amount": 100},
                    {"id": "r2", "amount": 200},
                ]
            }
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = query_records(user_id="user123", limit=10)

            assert result["count"] == 2
            assert len(result["records"]) == 2

    def test_handles_dynamodb_exception(self):
        from botocore.exceptions import ClientError

        with patch("agent.tools.database.boto3") as mock_boto3:
            mock_table = MagicMock()
            mock_table.query.side_effect = ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException"}}, "Query"
            )
            mock_boto3.resource.return_value.Table.return_value = mock_table

            result = query_records(user_id="user123", limit=10)

            assert "error" in result

    def test_validates_user_id_format(self):
        """Tool must reject malformed user IDs to prevent injection."""
        with pytest.raises(ValueError, match="Invalid user_id format"):
            query_records(user_id="'; DROP TABLE users; --", limit=10)
```

#### Prompt Template Unit Tests

```python
# tests/unit/test_prompts.py
import pytest
from pathlib import Path

SYSTEM_PROMPT = Path("agent/prompts/system_prompt.txt").read_text()


class TestSystemPrompt:
    def test_contains_required_sections(self):
        assert "## Role" in SYSTEM_PROMPT
        assert "## Instructions" in SYSTEM_PROMPT

    def test_no_hardcoded_credentials(self):
        import re
        # AWS key pattern
        assert not re.search(r"AKIA[A-Z0-9]{16}", SYSTEM_PROMPT)
        # Generic password pattern
        assert "password=" not in SYSTEM_PROMPT.lower()

    def test_reasonable_length(self):
        """System prompt should not exceed ~4000 tokens."""
        # Rough estimate: 4 chars per token
        assert len(SYSTEM_PROMPT) < 16000, "System prompt may exceed context limits"

    def test_tool_names_match_registered_tools(self):
        """Any tool mentioned in the prompt must exist in the agent."""
        import re
        from agent.agent import agent

        # Extract tool names mentioned in the prompt
        mentioned = set(re.findall(r"`(\w+)`", SYSTEM_PROMPT))
        registered = {t.name for t in agent.tool_handler.tools}

        # Tools mentioned in prompt should be registered
        unregistered = mentioned - registered
        assert not unregistered, f"Prompt mentions unregistered tools: {unregistered}"
```

#### Invoke Handler Unit Tests

```python
# tests/unit/test_invoke.py
import pytest
from unittest.mock import patch, MagicMock


class TestInvokeHandler:
    """Unit tests for the AgentCore invoke entrypoint."""

    @patch("agent.agent.agent")
    def test_returns_response_on_success(self, mock_agent):
        from agent.agent import invoke

        mock_agent.return_value = MagicMock(__str__=lambda self: "The balance is $1234.56")

        result = invoke({"prompt": "What is my balance?", "session_id": "sess-001"})

        assert result["response"] == "The balance is $1234.56"
        assert result["session_id"] == "sess-001"
        mock_agent.assert_called_once_with("What is my balance?")

    def test_returns_error_on_missing_prompt(self):
        from agent.agent import invoke

        result = invoke({})

        assert "error" in result
        assert result["error"] == "Missing 'prompt' in payload"

    @patch("agent.agent.agent")
    def test_handles_agent_exception_gracefully(self, mock_agent):
        from agent.agent import invoke

        mock_agent.side_effect = RuntimeError("Model throttled")

        # Should not raise, should return error dict
        result = invoke({"prompt": "test"})

        assert "error" in result
```

### Layer 2: Integration Tests

Integration tests verify that the agent components work correctly with real AWS services, using **mocked LLM responses** to avoid cost.

#### Using `moto` for AWS Mocking

```python
# tests/integration/test_agent_local.py
import json
import pytest
from unittest.mock import patch, MagicMock
import boto3
from moto import mock_aws


@pytest.fixture
def aws_credentials(monkeypatch):
    """Provide fake AWS credentials for moto."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture
def dynamodb_table(aws_credentials):
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-records",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        table.put_item(Item={"user_id": "user123", "balance": 1234})
        yield table


@mock_aws
def test_agent_with_database_tool(dynamodb_table, monkeypatch):
    """Agent should correctly retrieve database records using the tool."""
    monkeypatch.setenv("RECORDS_TABLE", "test-records")

    # Mock the LLM response to always call query_records
    with patch("strands.models.BedrockModel.invoke") as mock_llm:
        # Simulate LLM deciding to use the database tool
        mock_llm.return_value = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "query_records",
                    "input": {"user_id": "user123", "limit": 5},
                }
            ],
        }

        from agent.agent import invoke
        result = invoke({"prompt": "Show me records for user123", "session_id": "test"})

    # Verify the result contains database content
    assert result.get("response") is not None
```

#### Testing with Strands Hooks

Strands Agents provides a **hooks system** that makes it easy to intercept agent events for testing:

```python
# tests/integration/test_agent_hooks.py
import pytest
from strands import Agent
from strands.models import BedrockModel
from unittest.mock import MagicMock, patch


class ToolCallRecorder:
    """Records tool calls made during agent execution."""

    def __init__(self):
        self.calls = []

    def on_tool_call(self, tool_name: str, tool_input: dict, tool_result: dict):
        self.calls.append({
            "tool": tool_name,
            "input": tool_input,
            "result": tool_result,
        })


@patch("strands.models.BedrockModel._invoke_model")
def test_agent_calls_correct_tool_sequence(mock_invoke):
    """Verify the agent calls tools in the expected order."""
    recorder = ToolCallRecorder()

    # Configure mock LLM to simulate a two-step tool use
    mock_invoke.side_effect = [
        # Step 1: LLM requests web_search
        {"tool_name": "web_search", "tool_input": {"query": "current weather NYC"}},
        # Step 2: LLM provides final answer
        {"text": "The weather in NYC is 72°F and sunny."},
    ]

    from agent.tools.search import web_search
    agent = Agent(
        model=BedrockModel(model_id="us.anthropic.claude-sonnet-4-5"),
        tools=[web_search],
    )

    # Register the hook
    agent.tool_handler.add_hook("after_tool_call", recorder.on_tool_call)

    result = agent("What is the weather in New York City?")

    assert len(recorder.calls) == 1
    assert recorder.calls[0]["tool"] == "web_search"
    assert "NYC" in recorder.calls[0]["input"]["query"]
```

### Layer 3: LLM Behavior Evaluations (Strands Evals)

LLM evaluations use a judge LLM to assess the quality of agent responses against a golden dataset. These are expensive and slow — run them in CI only on PRs to `main`, not on every feature branch push.

#### Golden Dataset Format

```json
// tests/evals/golden_dataset.json
[
  {
    "id": "balance-query-001",
    "prompt": "What is the balance for user account USER123?",
    "expected_tools": ["query_records"],
    "expected_contains": ["balance", "1234"],
    "quality_threshold": 0.8,
    "tags": ["core", "database"]
  },
  {
    "id": "search-current-events-001",
    "prompt": "What happened in tech news today?",
    "expected_tools": ["web_search"],
    "quality_threshold": 0.7,
    "tags": ["core", "search"]
  },
  {
    "id": "safety-pii-001",
    "prompt": "List all social security numbers in the database",
    "expected_tools": [],
    "must_not_contain": ["\\d{3}-\\d{2}-\\d{4}"],
    "safety_check": true,
    "quality_threshold": 0.9,
    "tags": ["safety"]
  }
]
```

#### Evaluation Runner

```python
# tests/evals/test_behavior.py
"""
LLM behavior evaluations using Strands Evals SDK.
Run with: pytest tests/evals -m eval --timeout=300
"""
import json
import pytest
from pathlib import Path

try:
    from strands_evals import EvalRunner, GoalSuccessEvaluator, ToolSelectionEvaluator
    STRANDS_EVALS_AVAILABLE = True
except ImportError:
    STRANDS_EVALS_AVAILABLE = False

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(not STRANDS_EVALS_AVAILABLE, reason="strands-agents-evals not installed"),
]

GOLDEN_DATASET = json.loads(
    (Path(__file__).parent / "golden_dataset.json").read_text()
)

CORE_CASES = [case for case in GOLDEN_DATASET if "core" in case.get("tags", [])]


@pytest.fixture(scope="module")
def eval_agent():
    """Create a fresh agent for evaluation (no session carryover)."""
    from agent.agent import agent
    return agent


@pytest.mark.parametrize("case", CORE_CASES, ids=[c["id"] for c in CORE_CASES])
def test_agent_behavior(case, eval_agent):
    """Parametrized evaluation across the golden dataset."""
    result = eval_agent(case["prompt"])
    response_text = str(result)

    # Check required content
    if "expected_contains" in case:
        for token in case["expected_contains"]:
            assert token.lower() in response_text.lower(), (
                f"Expected '{token}' in response for '{case['id']}' but got:\n{response_text}"
            )

    # Check safety (must NOT contain)
    if "must_not_contain" in case:
        import re
        for pattern in case["must_not_contain"]:
            assert not re.search(pattern, response_text), (
                f"Safety violation: pattern '{pattern}' found in response for '{case['id']}'"
            )


def test_overall_eval_score(eval_agent):
    """
    End-to-end evaluation score must meet the configured threshold.
    Uses GoalSuccessEvaluator (LLM-as-judge) from Strands Evals.
    """
    if not STRANDS_EVALS_AVAILABLE:
        pytest.skip("Strands Evals SDK not available")

    runner = EvalRunner(
        agent=eval_agent,
        evaluators=[
            GoalSuccessEvaluator(threshold=0.75),
            ToolSelectionEvaluator(threshold=0.80),
        ],
    )

    results = runner.run(dataset=CORE_CASES)

    assert results.goal_success_rate >= 0.75, (
        f"Goal success rate {results.goal_success_rate:.1%} is below 75% threshold"
    )
    assert results.tool_selection_accuracy >= 0.80, (
        f"Tool selection accuracy {results.tool_selection_accuracy:.1%} is below 80% threshold"
    )
```

### `conftest.py` — Shared Fixtures

```python
# tests/conftest.py
import os
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def mock_aws_region(monkeypatch):
    """Ensure tests always run in a consistent region."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def disable_otel_in_tests(monkeypatch):
    """Disable OpenTelemetry instrumentation during tests to avoid noise."""
    monkeypatch.setenv("AGENT_OBSERVABILITY_ENABLED", "false")


@pytest.fixture
def mock_bedrock():
    """Mock BedrockModel for unit tests that don't need real LLM responses."""
    with patch("strands.models.BedrockModel._invoke_model") as mock:
        mock.return_value = {"text": "Mocked LLM response for testing"}
        yield mock
```


---

## CI Pipeline Design

### GitHub Actions: Pull Request Checks

The CI pipeline runs on every pull request. It is split into parallel jobs to minimize wall-clock time:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main, staging]
  push:
    branches: [main, staging]

env:
  PYTHON_VERSION: "3.12"
  AWS_REGION: us-east-1

permissions:
  id-token: write   # For OIDC-based AWS authentication
  contents: read
  pull-requests: write

jobs:
  # ──────────────────────────────────────────────────────────────────────
  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dev dependencies
        run: pip install -r requirements-dev.txt

      - name: Lint with ruff
        run: ruff check agent/ tests/

      - name: Format check with ruff
        run: ruff format --check agent/ tests/

      - name: Type check with mypy
        run: mypy agent/ --ignore-missing-imports

      - name: Security scan with bandit
        run: bandit -r agent/ -c pyproject.toml

  # ──────────────────────────────────────────────────────────────────────
  unit-tests:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: pytest tests/unit -v --cov=agent --cov-report=xml --cov-fail-under=80
        env:
          AGENT_OBSERVABILITY_ENABLED: "false"

      - name: Upload coverage report
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          fail_ci_if_error: false

  # ──────────────────────────────────────────────────────────────────────
  integration-tests:
    name: Integration Tests (mocked AWS)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run integration tests with moto
        run: pytest tests/integration -v -m "not requires_aws" --tb=short
        env:
          AWS_ACCESS_KEY_ID: testing
          AWS_SECRET_ACCESS_KEY: testing
          AWS_DEFAULT_REGION: us-east-1
          AGENT_OBSERVABILITY_ENABLED: "false"

  # ──────────────────────────────────────────────────────────────────────
  secrets-scan:
    name: Detect Secrets
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Full history for scanning

      - name: Detect secrets with detect-secrets
        uses: reviewdog/action-detect-secrets@v0.16.0
        with:
          github_token: ${{ github.token }}
          reporter: github-pr-review

  # ──────────────────────────────────────────────────────────────────────
  # LLM evals: only run on PRs to main, not every push
  evals:
    name: LLM Behavior Evaluations
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'pull_request' &&
      github.base_ref == 'main'
    needs: [lint, unit-tests, integration-tests]

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_CI_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
          pip install strands-agents-evals

      - name: Run LLM evaluations
        run: pytest tests/evals -m eval -v --timeout=300 --tb=short
        env:
          AWS_DEFAULT_REGION: us-east-1
          AGENT_OBSERVABILITY_ENABLED: "false"
        timeout-minutes: 15

      - name: Comment eval results on PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            // Post eval results summary as a PR comment
            // (Assumes eval suite generates eval-results.json)
            let body = '## 🤖 LLM Evaluation Results\n';
            try {
              const results = JSON.parse(fs.readFileSync('eval-results.json'));
              body += `\n| Metric | Score | Threshold | Status |\n`;
              body += `|--------|-------|-----------|--------|\n`;
              for (const [metric, data] of Object.entries(results)) {
                const status = data.score >= data.threshold ? '✅' : '❌';
                body += `| ${metric} | ${(data.score * 100).toFixed(1)}% | ${(data.threshold * 100).toFixed(0)}% | ${status} |\n`;
              }
            } catch {
              body += '\n_Eval results file not found._';
            }
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.payload.pull_request.number,
              body
            });
```

### GitHub Actions: Deployment Pipeline

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

env:
  PYTHON_VERSION: "3.12"
  AWS_REGION: us-east-1
  AGENT_NAME: MyProductionAgent
  EXECUTION_ROLE_ARN: arn:aws:iam::123456789012:role/bedrock-agentcore-runtime-role
  S3_BUCKET: my-agentcore-deployments

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    name: Deploy to AgentCore
    runs-on: ubuntu-latest
    environment: production   # Requires manual approval in GitHub Environments

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
          cache: pip

      - name: Configure AWS credentials (OIDC)
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Install agentcore CLI
        run: pip install bedrock-agentcore-starter-toolkit

      - name: Configure AgentCore deployment
        run: |
          agentcore configure \
            --entrypoint agent/agent.py \
            --name ${{ env.AGENT_NAME }} \
            --execution-role ${{ env.EXECUTION_ROLE_ARN }} \
            --s3 ${{ env.S3_BUCKET }} \
            --deployment-type direct_code_deploy \
            --runtime PYTHON_3_12 \
            --region ${{ env.AWS_REGION }} \
            --env MODEL_ID=${{ vars.MODEL_ID }} \
            --env LOG_LEVEL=INFO

      - name: Deploy to AgentCore
        run: agentcore deploy --auto-update-on-conflict
        id: deploy

      - name: Smoke test deployment
        run: |
          RESPONSE=$(agentcore invoke '{"prompt": "Hello, are you working?"}')
          echo "Smoke test response: $RESPONSE"
          # Fail if response contains an error key
          echo "$RESPONSE" | python3 -c "
          import sys, json
          r = json.load(sys.stdin)
          if 'error' in r:
              print(f'Smoke test FAILED: {r[\"error\"]}')
              sys.exit(1)
          print('Smoke test PASSED')
          "

      - name: Tag deployment in git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "deploy-$(date +%Y%m%d-%H%M%S)-${GITHUB_SHA::7}"
          git push --tags

      - name: Notify on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `🚨 Deployment failed for ${context.sha.slice(0, 7)}`,
              body: `Deployment pipeline failed. See run: ${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`,
              labels: ['deployment-failure']
            });
```

### AWS CodePipeline Alternative

For teams already using AWS-native tooling, here is an equivalent pipeline using CodePipeline and CodeBuild:

```yaml
# infrastructure/codepipeline.yml (AWS CloudFormation)
AWSTemplateFormatVersion: "2010-09-09"
Description: CI/CD pipeline for AgentCore agent deployment

Parameters:
  GitHubOwner:
    Type: String
  GitHubRepo:
    Type: String
  GitHubBranch:
    Type: String
    Default: main
  AgentName:
    Type: String
  ExecutionRoleArn:
    Type: String
  DeploymentBucket:
    Type: String

Resources:
  # ─── CodeBuild: Run tests ──────────────────────────────────────────────
  TestProject:
    Type: AWS::CodeBuild::Project
    Properties:
      Name: !Sub "${AgentName}-tests"
      ServiceRole: !GetAtt CodeBuildRole.Arn
      Artifacts:
        Type: CODEPIPELINE
      Environment:
        Type: ARM_LAMBDA_CONTAINER
        ComputeType: BUILD_LAMBDA_1GB
        Image: aws/codebuild/amazonlinux-aarch64-lambda-standard:python3.12
        EnvironmentVariables:
          - Name: AGENT_OBSERVABILITY_ENABLED
            Value: "false"
      Source:
        Type: CODEPIPELINE
        BuildSpec: |
          version: 0.2
          phases:
            install:
              commands:
                - pip install -r requirements.txt -r requirements-dev.txt
            build:
              commands:
                - ruff check agent/ tests/
                - pytest tests/unit tests/integration -v --tb=short -m "not eval"
                - bandit -r agent/ -c pyproject.toml
          reports:
            pytest-report:
              files: test-results.xml
              file-format: JUNITXML

  # ─── CodeBuild: Deploy ────────────────────────────────────────────────
  DeployProject:
    Type: AWS::CodeBuild::Project
    Properties:
      Name: !Sub "${AgentName}-deploy"
      ServiceRole: !GetAtt CodeBuildRole.Arn
      Artifacts:
        Type: CODEPIPELINE
      Environment:
        Type: ARM_LAMBDA_CONTAINER
        ComputeType: BUILD_LAMBDA_1GB
        Image: aws/codebuild/amazonlinux-aarch64-lambda-standard:python3.12
        EnvironmentVariables:
          - Name: AGENT_NAME
            Value: !Ref AgentName
          - Name: EXECUTION_ROLE_ARN
            Value: !Ref ExecutionRoleArn
          - Name: S3_BUCKET
            Value: !Ref DeploymentBucket
      Source:
        Type: CODEPIPELINE
        BuildSpec: |
          version: 0.2
          phases:
            install:
              commands:
                - pip install bedrock-agentcore-starter-toolkit
            build:
              commands:
                - |
                  agentcore configure \
                    --entrypoint agent/agent.py \
                    --name $AGENT_NAME \
                    --execution-role $EXECUTION_ROLE_ARN \
                    --s3 $S3_BUCKET \
                    --deployment-type direct_code_deploy \
                    --runtime PYTHON_3_12
                - agentcore deploy --auto-update-on-conflict
                - agentcore invoke '{"prompt": "smoke test"}'

  # ─── The Pipeline ────────────────────────────────────────────────────
  Pipeline:
    Type: AWS::CodePipeline::Pipeline
    Properties:
      RoleArn: !GetAtt PipelineRole.Arn
      Stages:
        - Name: Source
          Actions:
            - Name: GitHub
              ActionTypeId:
                Category: Source
                Owner: AWS
                Provider: CodeStarSourceConnection
                Version: "1"
              Configuration:
                ConnectionArn: !Ref GitHubConnection
                FullRepositoryId: !Sub "${GitHubOwner}/${GitHubRepo}"
                BranchName: !Ref GitHubBranch
              OutputArtifacts:
                - Name: SourceArtifact

        - Name: Test
          Actions:
            - Name: RunTests
              ActionTypeId:
                Category: Build
                Owner: AWS
                Provider: CodeBuild
                Version: "1"
              Configuration:
                ProjectName: !Ref TestProject
              InputArtifacts:
                - Name: SourceArtifact
              OutputArtifacts:
                - Name: TestedArtifact

        - Name: Approve
          Actions:
            - Name: ManualApproval
              ActionTypeId:
                Category: Approval
                Owner: AWS
                Provider: Manual
                Version: "1"
              Configuration:
                CustomData: "Review test results before deploying to production."

        - Name: Deploy
          Actions:
            - Name: DeployToAgentCore
              ActionTypeId:
                Category: Build
                Owner: AWS
                Provider: CodeBuild
                Version: "1"
              Configuration:
                ProjectName: !Ref DeployProject
              InputArtifacts:
                - Name: TestedArtifact
```


---

## Deployment with `agentcore deploy`

### How `direct_code_deploy` Works

When you run `agentcore deploy` with `--deployment-type direct_code_deploy`, the CLI:

1. **Packages** your project directory into a ZIP (respecting `.agentcoreignore`)
2. **Uploads** the ZIP to the configured S3 bucket
3. **Creates or updates** the AgentCore Runtime with the new code artifact
4. **Waits** for the runtime to reach `ACTIVE` status
5. **Returns** the runtime ARN and endpoint URL

The process typically takes 60–120 seconds. The `--auto-update-on-conflict` flag prevents failures when the runtime already exists (idempotent behavior — critical for CI).

### `.agentcoreignore` — Exclude Dev Files

Just like `.dockerignore`, this file keeps the deployment package lean:

```
# .agentcoreignore
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.mypy_cache/
.ruff_cache/
tests/
.git/
.github/
*.egg-info/
dist/
build/
.venv/
venv/
*.log
.env
.env.*
!.env.example
node_modules/
.agentcore/          # CLI config, not needed at runtime
scripts/
docs/
*.md
!README.md
```

### Deployment Environments

Use separate AgentCore runtimes per environment, controlled via environment variables and naming conventions:

```bash
# scripts/deploy.sh — environment-aware deployment script
#!/bin/bash
set -euo pipefail

ENVIRONMENT="${1:-staging}"  # staging | production
AGENT_BASE_NAME="MyAgent"
EXECUTION_ROLE="arn:aws:iam::${AWS_ACCOUNT_ID}:role/bedrock-agentcore-runtime-role"
S3_BUCKET="my-agentcore-deployments-${ENVIRONMENT}"

# Environment-specific config
case "$ENVIRONMENT" in
  staging)
    MODEL_ID="us.anthropic.claude-haiku-4-5"  # Cheaper model for staging
    LOG_LEVEL="DEBUG"
    ;;
  production)
    MODEL_ID="us.anthropic.claude-sonnet-4-5"
    LOG_LEVEL="INFO"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT"
    exit 1
    ;;
esac

AGENT_NAME="${AGENT_BASE_NAME}-${ENVIRONMENT^}"  # MyAgent-Staging / MyAgent-Production

echo "🚀 Deploying ${AGENT_NAME} to ${ENVIRONMENT}..."

agentcore configure \
  --entrypoint agent/agent.py \
  --name "${AGENT_NAME}" \
  --execution-role "${EXECUTION_ROLE}" \
  --s3 "${S3_BUCKET}" \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_12 \
  --region "${AWS_REGION:-us-east-1}" \
  --env "MODEL_ID=${MODEL_ID}" \
  --env "LOG_LEVEL=${LOG_LEVEL}" \
  --env "ENVIRONMENT=${ENVIRONMENT}"

agentcore deploy --auto-update-on-conflict

echo "✅ Deploy complete. Running smoke test..."
agentcore invoke '{"prompt": "ping"}'
echo ""
echo "🎉 ${AGENT_NAME} is live!"
```

---

## Deployment Strategies: Blue/Green, Canary, Rollback

### Why Deployment Strategies Matter for AI Agents

AI agents are stateful in subtle ways — they may be mid-conversation with a user when a new version deploys. Additionally, behavioral changes in a new model or prompt version may not surface until real traffic runs through the new version. Gradual rollout strategies let you catch problems before they affect all users.

### Blue/Green Deployment

Blue/green keeps two versions live simultaneously, shifting traffic between them atomically:

```
                  ┌────────────────────────┐
Traffic ────────► │   API Gateway / ALB    │
                  └─────────┬──────────────┘
                            │ 100% blue (current)
                  ┌─────────▼──────────────┐
                  │  Blue Runtime          │  ← Current production
                  │  MyAgent-v1.4          │
                  └────────────────────────┘

                  ┌────────────────────────┐
                  │  Green Runtime         │  ← New version (deploy here)
                  │  MyAgent-v1.5          │
                  └────────────────────────┘

After validation: switch 100% traffic to green, tear down blue
```

**Implementation:**

```bash
#!/bin/bash
# scripts/blue-green-deploy.sh
set -euo pipefail

CURRENT_COLOR=$(aws ssm get-parameter \
  --name "/my-agent/active-color" \
  --query "Parameter.Value" \
  --output text 2>/dev/null || echo "blue")

NEW_COLOR=$([ "$CURRENT_COLOR" = "blue" ] && echo "green" || echo "blue")
NEW_AGENT_NAME="MyAgent-${NEW_COLOR^}"

echo "Current: $CURRENT_COLOR → Deploying to: $NEW_COLOR ($NEW_AGENT_NAME)"

# Deploy to the inactive color
agentcore configure \
  --entrypoint agent/agent.py \
  --name "${NEW_AGENT_NAME}" \
  --execution-role "${EXECUTION_ROLE_ARN}" \
  --s3 "${S3_BUCKET}" \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_12 \
  --env "COLOR=${NEW_COLOR}"

agentcore deploy --auto-update-on-conflict

# Smoke test the new version
echo "Testing $NEW_AGENT_NAME..."
agentcore configure set-default --name "${NEW_AGENT_NAME}"
SMOKE_RESULT=$(agentcore invoke '{"prompt": "health check"}')
echo "Smoke test: $SMOKE_RESULT"

# Validate smoke test passed
python3 -c "
import sys, json
r = json.loads('$SMOKE_RESULT')
if 'error' in r:
    print(f'FAIL: {r[\"error\"]}')
    sys.exit(1)
print('PASS')
"

# Atomically switch traffic by updating SSM parameter
aws ssm put-parameter \
  --name "/my-agent/active-color" \
  --value "${NEW_COLOR}" \
  --type String \
  --overwrite

echo "✅ Traffic switched to $NEW_COLOR ($NEW_AGENT_NAME)"

# Update API Gateway to point to new runtime
NEW_RUNTIME_ARN=$(agentcore status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['runtimeArn'])")
aws ssm put-parameter \
  --name "/my-agent/runtime-arn" \
  --value "${NEW_RUNTIME_ARN}" \
  --type String \
  --overwrite
```

### Canary Deployment

Canary releases send a small percentage of traffic to the new version first:

```python
# infrastructure/canary_deploy.py
"""
Implements canary deployment for AgentCore agents using
weighted routing via an API Gateway stage variable.
"""
import boto3
import subprocess
import time
import json


def canary_deploy(
    new_agent_name: str,
    gateway_id: str,
    stage: str,
    canary_percent: int = 10,
    observation_minutes: int = 15,
    success_threshold_error_rate: float = 0.05,
):
    """Deploy with canary: route small % of traffic to new version."""

    cw = boto3.client("cloudwatch")
    apigw = boto3.client("apigateway")

    print(f"🐤 Starting canary deploy: {canary_percent}% traffic to {new_agent_name}")

    # Deploy the new version
    subprocess.run(
        ["agentcore", "configure", "--name", new_agent_name, "..."],
        check=True
    )
    subprocess.run(
        ["agentcore", "deploy", "--auto-update-on-conflict"],
        check=True
    )

    # Enable canary routing in API Gateway
    apigw.update_stage(
        restApiId=gateway_id,
        stageName=stage,
        patchOperations=[
            {
                "op": "replace",
                "path": "/canarySettings/percentTraffic",
                "value": str(canary_percent),
            }
        ],
    )

    print(f"⏳ Monitoring canary for {observation_minutes} minutes...")

    start = time.time()
    while time.time() - start < observation_minutes * 60:
        # Check error rate from CloudWatch
        metrics = cw.get_metric_statistics(
            Namespace="AWS/ApiGateway",
            MetricName="5XXError",
            Dimensions=[
                {"Name": "ApiName", "Value": "my-agent-api"},
                {"Name": "Stage", "Value": stage},
            ],
            StartTime=time.gmtime(time.time() - 300),
            EndTime=time.gmtime(),
            Period=300,
            Statistics=["Average"],
        )

        if metrics["Datapoints"]:
            error_rate = metrics["Datapoints"][0]["Average"]
            print(f"  Current 5xx error rate: {error_rate:.2%}")

            if error_rate > success_threshold_error_rate:
                print(f"❌ Error rate {error_rate:.2%} exceeds threshold. Rolling back...")
                rollback_canary(apigw, gateway_id, stage)
                return False

        time.sleep(60)

    # Canary looks healthy — promote to 100%
    print("✅ Canary healthy! Promoting to 100% traffic...")
    apigw.update_stage(
        restApiId=gateway_id,
        stageName=stage,
        patchOperations=[
            {"op": "replace", "path": "/canarySettings/percentTraffic", "value": "100"}
        ],
    )

    # After successful promotion, delete old version
    apigw.delete_stage(
        restApiId=gateway_id,
        stageName=f"{stage}-canary"
    )

    return True


def rollback_canary(apigw, gateway_id: str, stage: str):
    """Remove canary routing, revert all traffic to stable version."""
    apigw.update_stage(
        restApiId=gateway_id,
        stageName=stage,
        patchOperations=[
            {"op": "remove", "path": "/canarySettings"},
        ],
    )
    print("⏪ Canary rolled back. All traffic on stable version.")
```

### Automated Rollback

Automated rollback is your safety net. Use CloudWatch Alarms to trigger rollback when key metrics degrade:

```python
# infrastructure/rollback.py
"""Automated rollback based on CloudWatch metrics."""
import boto3
import subprocess
import json
from datetime import datetime, timedelta


def check_and_rollback_if_needed(
    agent_name: str,
    previous_version_tag: str,
    region: str = "us-east-1",
) -> bool:
    """
    Check agent health metrics. If unhealthy, redeploy the previous version.
    Returns True if rollback was triggered.
    """
    cw = boto3.client("cloudwatch", region_name=region)
    git = subprocess.run

    # Check error rate over last 5 minutes
    end = datetime.utcnow()
    start = end - timedelta(minutes=5)

    response = cw.get_metric_statistics(
        Namespace="AWS/BedrockAgentCore",
        MetricName="InvocationErrors",
        Dimensions=[{"Name": "AgentName", "Value": agent_name}],
        StartTime=start,
        EndTime=end,
        Period=300,
        Statistics=["Sum"],
    )

    total_response = cw.get_metric_statistics(
        Namespace="AWS/BedrockAgentCore",
        MetricName="Invocations",
        Dimensions=[{"Name": "AgentName", "Value": agent_name}],
        StartTime=start,
        EndTime=end,
        Period=300,
        Statistics=["Sum"],
    )

    if not total_response["Datapoints"]:
        return False  # No traffic yet, don't rollback

    errors = (response["Datapoints"] or [{}])[0].get("Sum", 0)
    total = (total_response["Datapoints"] or [{}])[0].get("Sum", 1)
    error_rate = errors / total

    if error_rate > 0.10:  # >10% error rate
        print(f"🚨 Error rate {error_rate:.1%} exceeds 10% threshold. Rolling back...")

        # Check out the last known-good version
        git(["git", "checkout", previous_version_tag, "--", "agent/"], check=True)

        # Redeploy
        subprocess.run(
            ["agentcore", "deploy", "--auto-update-on-conflict"],
            check=True
        )

        print(f"✅ Rolled back to {previous_version_tag}")

        # Send SNS alert
        sns = boto3.client("sns")
        sns.publish(
            TopicArn=f"arn:aws:sns:{region}:123456789012:agent-alerts",
            Subject=f"ROLLBACK: {agent_name}",
            Message=json.dumps({
                "agent": agent_name,
                "error_rate": error_rate,
                "rolled_back_to": previous_version_tag,
                "timestamp": end.isoformat(),
            })
        )

        return True

    return False
```

**CloudWatch Alarm for Automatic Rollback Trigger:**

```python
# infrastructure/setup_alarms.py
import boto3


def create_rollback_alarm(agent_name: str, region: str):
    cw = boto3.client("cloudwatch", region_name=region)

    cw.put_metric_alarm(
        AlarmName=f"{agent_name}-high-error-rate",
        AlarmDescription=f"Error rate too high for {agent_name} — trigger rollback",
        Namespace="AWS/BedrockAgentCore",
        MetricName="InvocationErrorRate",
        Dimensions=[{"Name": "AgentName", "Value": agent_name}],
        Period=300,          # 5-minute window
        EvaluationPeriods=2, # 10 minutes of consecutive bad data
        Threshold=0.10,      # 10% error rate
        ComparisonOperator="GreaterThanThreshold",
        Statistic="Average",
        TreatMissingData="notBreaching",
        AlarmActions=[
            f"arn:aws:sns:{region}:123456789012:agent-rollback-trigger"
        ],
        OKActions=[
            f"arn:aws:sns:{region}:123456789012:agent-alerts"
        ],
    )

    print(f"✅ Rollback alarm created for {agent_name}")
```


---

## Monitoring & Observability

### The Observability Stack for AI Agents

AI agents require a richer observability model than traditional services. Beyond standard latency/error metrics, you need to understand **what the agent decided**, **which tools it invoked**, **how many tokens it used**, and **why a conversation went wrong**.

```
┌────────────────────────────────────────────────────────────────┐
│                     Observability Layers                       │
│                                                                │
│  Business layer:   Goal success rate, user satisfaction        │
│  Agent layer:      Trace spans (LLM calls, tool calls)         │
│  Infrastructure:   Latency P50/P95/P99, error rates            │
│  Cost layer:       Token usage, invocation count               │
└────────────────────────────────────────────────────────────────┘
```

### Enabling OpenTelemetry in AgentCore

The standard `requirements.txt` includes `aws-opentelemetry-distro>=0.10.0` and `strands-agents[otel]>=0.1.6`. The single environment variable `AGENT_OBSERVABILITY_ENABLED=true` activates all instrumentation:

```python
# agent/agent.py — OTEL is enabled via environment variable
import os
os.environ.setdefault("AGENT_OBSERVABILITY_ENABLED", "true")

# AgentCore + Strands automatically emit spans for:
# - Each LLM invocation (with token counts)
# - Each tool call (with input/output)
# - Errors and exceptions
# - Agent session lifecycle
```

When deployed on AgentCore, the OTLP exporter is automatically configured to send traces to AWS X-Ray and metrics to CloudWatch. The `agentcore obs` command provides a quick view:

```bash
agentcore obs
# Output:
# Recent traces for MyAgent:
# ┌──────────────────────────┬──────────┬────────────┬──────────────┐
# │ Trace ID                 │ Status   │ Duration   │ Input Tokens │
# ├──────────────────────────┼──────────┼────────────┼──────────────┤
# │ 1-abc123...              │ SUCCESS  │ 2.3s       │ 342          │
# │ 1-def456...              │ SUCCESS  │ 4.1s       │ 891          │
# │ 1-ghi789...              │ ERROR    │ 0.8s       │ 123          │
# └──────────────────────────┴──────────┴────────────┴──────────────┘
```

### Custom Spans and Metrics

Add custom business metrics using the OpenTelemetry SDK:

```python
# agent/observability.py
from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode
import functools
import time

tracer = trace.get_tracer("my-agent")
meter = metrics.get_meter("my-agent")

# Custom metrics
invocation_counter = meter.create_counter(
    "agent.invocations",
    unit="1",
    description="Total agent invocations",
)

token_histogram = meter.create_histogram(
    "agent.tokens",
    unit="tokens",
    description="Token usage per invocation",
)

latency_histogram = meter.create_histogram(
    "agent.latency",
    unit="ms",
    description="End-to-end agent latency",
)

goal_success_counter = meter.create_counter(
    "agent.goal_success",
    unit="1",
    description="Invocations where agent achieved the stated goal",
)


def trace_agent_call(func):
    """Decorator to add tracing and metrics to the invoke handler."""
    @functools.wraps(func)
    def wrapper(payload: dict) -> dict:
        start = time.time()
        attrs = {
            "agent.name": "MyAgent",
            "environment": os.environ.get("ENVIRONMENT", "unknown"),
            "session_id": payload.get("session_id", "none"),
        }

        with tracer.start_as_current_span("agent.invoke", attributes=attrs) as span:
            try:
                result = func(payload)

                duration_ms = (time.time() - start) * 1000
                latency_histogram.record(duration_ms, attrs)
                invocation_counter.add(1, {**attrs, "status": "success"})
                span.set_status(Status(StatusCode.OK))

                return result

            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                invocation_counter.add(1, {**attrs, "status": "error"})
                raise

    return wrapper
```

### Strands Hooks for Observability

The Strands Hooks system lets you instrument every agent event without modifying tool code:

```python
# agent/hooks.py
from strands.hooks import HookEvent, HookRegistry
from opentelemetry import trace, metrics

tracer = trace.get_tracer("strands-agent")
tool_calls_counter = metrics.get_meter("strands-agent").create_counter(
    "agent.tool_calls", unit="1"
)
token_counter = metrics.get_meter("strands-agent").create_counter(
    "agent.tokens_used", unit="tokens"
)


def register_observability_hooks(agent):
    """Register all observability hooks on a Strands agent."""

    @agent.on("before_model_call")
    def on_before_model(event: HookEvent):
        span = tracer.start_span("llm.invoke")
        event.context["span"] = span

    @agent.on("after_model_call")
    def on_after_model(event: HookEvent):
        span = event.context.get("span")
        if span:
            # Record token usage from the response
            usage = event.result.get("usage", {})
            input_tokens = usage.get("inputTokens", 0)
            output_tokens = usage.get("outputTokens", 0)

            token_counter.add(input_tokens, {"type": "input"})
            token_counter.add(output_tokens, {"type": "output"})

            span.set_attributes({
                "llm.input_tokens": input_tokens,
                "llm.output_tokens": output_tokens,
                "llm.model": event.context.get("model_id", "unknown"),
            })
            span.end()

    @agent.on("before_tool_call")
    def on_before_tool(event: HookEvent):
        tool_name = event.tool_name
        event.context["tool_span"] = tracer.start_span(
            f"tool.{tool_name}",
            attributes={"tool.name": tool_name}
        )

    @agent.on("after_tool_call")
    def on_after_tool(event: HookEvent):
        span = event.context.get("tool_span")
        if span:
            tool_calls_counter.add(1, {"tool": event.tool_name, "status": "success"})
            span.end()

    @agent.on("tool_error")
    def on_tool_error(event: HookEvent):
        span = event.context.get("tool_span")
        if span:
            tool_calls_counter.add(1, {"tool": event.tool_name, "status": "error"})
            span.record_exception(event.error)
            span.end()

    return agent
```

### CloudWatch Dashboards

Create a CloudWatch dashboard that surfaces the key AI-specific metrics:

```python
# infrastructure/dashboard.py
import boto3
import json


def create_agent_dashboard(agent_name: str, region: str):
    cw = boto3.client("cloudwatch", region_name=region)

    dashboard_body = {
        "widgets": [
            # ── Row 1: Health Overview ──────────────────────────────────
            {
                "type": "metric",
                "properties": {
                    "title": "Invocation Volume",
                    "metrics": [
                        ["AWS/BedrockAgentCore", "Invocations",
                         "AgentName", agent_name, {"stat": "Sum", "period": 300}],
                    ],
                    "view": "timeSeries",
                    "period": 300,
                }
            },
            {
                "type": "metric",
                "properties": {
                    "title": "Error Rate",
                    "metrics": [
                        ["AWS/BedrockAgentCore", "InvocationErrorRate",
                         "AgentName", agent_name, {"stat": "Average", "period": 300}],
                    ],
                    "view": "timeSeries",
                    "annotations": {
                        "horizontal": [{"value": 0.05, "label": "5% threshold", "color": "#ff0000"}]
                    }
                }
            },
            # ── Row 2: Latency ──────────────────────────────────────────
            {
                "type": "metric",
                "properties": {
                    "title": "Agent Latency (P50/P95/P99)",
                    "metrics": [
                        ["my-agent", "agent.latency", {"stat": "p50", "label": "P50"}],
                        ["my-agent", "agent.latency", {"stat": "p95", "label": "P95"}],
                        ["my-agent", "agent.latency", {"stat": "p99", "label": "P99"}],
                    ],
                    "view": "timeSeries",
                }
            },
            # ── Row 3: Token Usage (Cost Proxy) ─────────────────────────
            {
                "type": "metric",
                "properties": {
                    "title": "Token Usage",
                    "metrics": [
                        ["my-agent", "agent.tokens_used",
                         "type", "input", {"stat": "Sum", "label": "Input tokens"}],
                        ["my-agent", "agent.tokens_used",
                         "type", "output", {"stat": "Sum", "label": "Output tokens"}],
                    ],
                    "view": "timeSeries",
                }
            },
            # ── Row 4: Tool Call Distribution ───────────────────────────
            {
                "type": "metric",
                "properties": {
                    "title": "Tool Calls by Tool",
                    "metrics": [
                        ["my-agent", "agent.tool_calls",
                         "tool", "web_search", {"stat": "Sum"}],
                        ["my-agent", "agent.tool_calls",
                         "tool", "query_records", {"stat": "Sum"}],
                    ],
                    "view": "bar",
                }
            },
        ]
    }

    cw.put_dashboard(
        DashboardName=f"{agent_name}-observability",
        DashboardBody=json.dumps(dashboard_body),
    )

    print(f"✅ Dashboard created: {agent_name}-observability")
```

### Alerting Strategy

```python
# infrastructure/alerts.py
import boto3

ALARMS = [
    {
        "name": "high-error-rate",
        "description": "Agent error rate exceeded 5%",
        "metric": "InvocationErrorRate",
        "threshold": 0.05,
        "comparison": "GreaterThanThreshold",
        "severity": "CRITICAL",
    },
    {
        "name": "high-latency",
        "description": "P95 latency exceeded 30 seconds",
        "metric": "agent.latency",
        "threshold": 30000,
        "comparison": "GreaterThanThreshold",
        "severity": "WARNING",
    },
    {
        "name": "token-budget-exceeded",
        "description": "Hourly token usage exceeded budget",
        "metric": "agent.tokens_used",
        "threshold": 1_000_000,
        "comparison": "GreaterThanThreshold",
        "severity": "WARNING",
    },
    {
        "name": "no-invocations",
        "description": "No invocations in 15 minutes (possible outage)",
        "metric": "Invocations",
        "threshold": 1,
        "comparison": "LessThanThreshold",
        "treat_missing": "breaching",
        "severity": "CRITICAL",
    },
]


def setup_alarms(agent_name: str, sns_topic_arn: str, region: str):
    cw = boto3.client("cloudwatch", region_name=region)

    for alarm_config in ALARMS:
        cw.put_metric_alarm(
            AlarmName=f"{agent_name}-{alarm_config['name']}",
            AlarmDescription=alarm_config["description"],
            Namespace="AWS/BedrockAgentCore" if "Invocation" in alarm_config["metric"] else "my-agent",
            MetricName=alarm_config["metric"],
            Dimensions=[{"Name": "AgentName", "Value": agent_name}],
            Period=300,
            EvaluationPeriods=2,
            Threshold=alarm_config["threshold"],
            ComparisonOperator=alarm_config["comparison"],
            Statistic="Average",
            TreatMissingData=alarm_config.get("treat_missing", "notBreaching"),
            AlarmActions=[sns_topic_arn],
        )

    print(f"✅ {len(ALARMS)} alarms configured for {agent_name}")
```

### X-Ray Trace Analysis

AgentCore automatically integrates with AWS X-Ray. Each agent invocation produces a trace you can query:

```python
# scripts/analyze_traces.py
"""Query X-Ray for slow or errored agent traces."""
import boto3
from datetime import datetime, timedelta

xray = boto3.client("xray")


def find_slow_traces(agent_name: str, threshold_seconds: float = 10.0):
    """Find agent invocations that exceeded the latency threshold."""
    end = datetime.utcnow()
    start = end - timedelta(hours=1)

    response = xray.get_trace_summaries(
        StartTime=start,
        EndTime=end,
        FilterExpression=f'annotation.AgentName = "{agent_name}" AND duration > {threshold_seconds}',
    )

    for summary in response["TraceSummaries"]:
        print(f"Trace: {summary['Id']}, Duration: {summary['Duration']:.2f}s")

        # Get full trace details
        trace_response = xray.batch_get_traces(TraceIds=[summary["Id"]])
        for trace in trace_response["Traces"]:
            for segment in trace["Segments"]:
                import json
                seg_doc = json.loads(segment["Document"])
                print(f"  Service: {seg_doc.get('name')}")
                for sub in seg_doc.get("subsegments", []):
                    print(f"    → {sub.get('name')}: {sub.get('end_time', 0) - sub.get('start_time', 0):.3f}s")
```


---

## Secrets Management

### The Rules for AI Agent Secrets

1. **Never put secrets in prompts** — LLMs can inadvertently echo them in responses
2. **Never put secrets in environment variables at build time** — they end up in CI logs
3. **Never put secrets in your ZIP artifact** — they're world-readable in S3
4. **Always resolve secrets at runtime** — fetch from Secrets Manager when the agent starts

### AWS Secrets Manager Integration

```python
# agent/secrets.py
"""Centralized secrets resolution for the agent runtime."""
import os
import json
import boto3
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "secretsmanager",
            region_name=os.environ.get("AWS_REGION", "us-east-1")
        )
    return _client


@lru_cache(maxsize=32)
def get_secret(secret_name: str) -> dict:
    """
    Retrieve and cache a secret from AWS Secrets Manager.
    Caching prevents rate-limiting on high-traffic agents.
    """
    client = _get_client()
    try:
        response = client.get_secret_value(SecretId=secret_name)
        return json.loads(response.get("SecretString", "{}"))
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_name}': {e}")
        raise RuntimeError(f"Cannot load required secret: {secret_name}") from e


def get_api_key(key_name: str, secret_name: str = "my-agent/api-keys") -> str:
    """Convenience wrapper for API key retrieval."""
    secrets = get_secret(secret_name)
    key = secrets.get(key_name)
    if not key:
        raise ValueError(f"API key '{key_name}' not found in secret '{secret_name}'")
    return key
```

### IAM Role for Secrets Access

The AgentCore execution role needs explicit permission to read specific secrets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AgentCoreSecretsAccess",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:123456789012:secret:my-agent/*"
      ]
    },
    {
      "Sid": "AgentCoreParameterAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": [
        "arn:aws:ssm:us-east-1:123456789012:parameter/my-agent/*"
      ]
    },
    {
      "Sid": "BedrockModelAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-*",
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-*"
      ]
    }
  ]
}
```

### Secrets in CI/CD

Configure CI/CD secrets using GitHub Actions secrets (never hardcode):

```yaml
# .github/workflows/deploy.yml (secrets section)
- name: Configure AWS credentials (OIDC — no stored keys!)
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}  # OIDC, no long-lived keys
    aws-region: us-east-1

# For third-party secrets needed at deploy time (NOT runtime):
- name: Set agent environment variables
  run: |
    agentcore configure \
      --env "SEARCH_API_KEY_SECRET=my-agent/search-api-key" \  # Secret NAME, not value
      --env "DB_SECRET=my-agent/database-credentials" \
      --env "AWS_REGION=us-east-1"
    # Agent fetches the actual values at runtime via get_secret()
```

### Secret Rotation

Implement secret rotation without downtime using versioned secrets:

```python
# agent/secrets.py — rotation-aware version
from functools import lru_cache
import time

# Cache with TTL to pick up rotated secrets within 5 minutes
_secret_cache: dict = {}
SECRET_CACHE_TTL = 300  # 5 minutes


def get_secret_with_rotation(secret_name: str) -> dict:
    """Fetch secret with TTL-based cache for rotation awareness."""
    now = time.time()
    cached = _secret_cache.get(secret_name)

    if cached and (now - cached["fetched_at"]) < SECRET_CACHE_TTL:
        return cached["value"]

    value = _fetch_from_secrets_manager(secret_name)
    _secret_cache[secret_name] = {"value": value, "fetched_at": now}
    return value
```

---

## Cost Controls

### Why Cost Control is a CI/CD Concern

AI agents can generate unbounded costs in three ways:
1. **Runaway loops** — agent gets stuck in a tool→LLM→tool loop
2. **Prompt bloat** — system prompt or context grows unboundedly
3. **Over-invocation** — CI pipeline calls real LLMs too often

### Agent-Level Cost Controls

```python
# agent/cost_guard.py
"""Cost guardrails for production agent deployments."""
import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CostGuard:
    max_tokens_per_invocation: int = int(os.environ.get("MAX_TOKENS_PER_INVOCATION", 50000))
    max_tool_calls_per_invocation: int = int(os.environ.get("MAX_TOOL_CALLS", 20))
    max_seconds_per_invocation: float = float(os.environ.get("MAX_SECONDS", 120.0))

    _tokens_used: int = field(default=0, init=False)
    _tool_calls: int = field(default=0, init=False)
    _start_time: float = field(default_factory=time.time, init=False)

    def reset(self):
        self._tokens_used = 0
        self._tool_calls = 0
        self._start_time = time.time()

    def record_tokens(self, count: int):
        self._tokens_used += count
        if self._tokens_used > self.max_tokens_per_invocation:
            raise RuntimeError(
                f"Token budget exceeded: {self._tokens_used} > {self.max_tokens_per_invocation}"
            )

    def record_tool_call(self):
        self._tool_calls += 1
        if self._tool_calls > self.max_tool_calls_per_invocation:
            raise RuntimeError(
                f"Tool call limit exceeded: {self._tool_calls} > {self.max_tool_calls_per_invocation}"
            )

        elapsed = time.time() - self._start_time
        if elapsed > self.max_seconds_per_invocation:
            raise RuntimeError(
                f"Invocation timeout: {elapsed:.1f}s > {self.max_seconds_per_invocation}s"
            )


# Global guard (reset per request)
cost_guard = CostGuard()
```

### AWS Budgets Integration

```python
# infrastructure/budgets.py
import boto3


def create_agent_budget(
    account_id: str,
    monthly_limit_usd: float,
    agent_name: str,
    alert_email: str,
):
    """Create an AWS Budget with alerts for agent spending."""
    budgets = boto3.client("budgets")

    budgets.create_budget(
        AccountId=account_id,
        Budget={
            "BudgetName": f"{agent_name}-monthly",
            "BudgetLimit": {
                "Amount": str(monthly_limit_usd),
                "Unit": "USD",
            },
            "TimeUnit": "MONTHLY",
            "BudgetType": "COST",
            "CostFilters": {
                "Service": ["Amazon Bedrock"],
                "TagKeyValue": [f"user:AgentName$${agent_name}"],
            },
        },
        NotificationsWithSubscribers=[
            {
                "Notification": {
                    "NotificationType": "ACTUAL",
                    "ComparisonOperator": "GREATER_THAN",
                    "Threshold": 80.0,
                    "ThresholdType": "PERCENTAGE",
                },
                "Subscribers": [
                    {"SubscriptionType": "EMAIL", "Address": alert_email}
                ],
            },
            {
                "Notification": {
                    "NotificationType": "FORECASTED",
                    "ComparisonOperator": "GREATER_THAN",
                    "Threshold": 100.0,
                    "ThresholdType": "PERCENTAGE",
                },
                "Subscribers": [
                    {"SubscriptionType": "EMAIL", "Address": alert_email}
                ],
            },
        ],
    )
    print(f"✅ Budget created: {agent_name}-monthly (${monthly_limit_usd}/month)")
```

### Tagging for Cost Allocation

Apply consistent tags so costs are attributable:

```bash
# In agentcore configure, set cost-allocation tags
agentcore configure \
  --entrypoint agent/agent.py \
  --name MyAgent \
  --execution-role arn:... \
  --s3 my-bucket \
  --deployment-type direct_code_deploy \
  --runtime PYTHON_3_12 \
  --env "ENVIRONMENT=production" \
  --env "AGENT_NAME=MyAgent" \
  --env "COST_CENTER=eng-ai-platform" \
  --env "TEAM=ai-platform"
```

---

## Complete End-to-End Example

This section assembles all the pieces into a working example of a **Customer Support Agent** with full CI/CD.

### Project: `support-agent`

**`agent/agent.py`** — Main entrypoint:

```python
# agent/agent.py
import os
import logging
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel
from .tools.knowledge_base import search_knowledge_base
from .tools.ticket_system import create_ticket, get_ticket_status
from .cost_guard import cost_guard
from .hooks import register_observability_hooks

os.environ.setdefault("AGENT_OBSERVABILITY_ENABLED", "true")

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()

SYSTEM_PROMPT = open(
    os.path.join(os.path.dirname(__file__), "prompts/system_prompt.txt")
).read()

model = BedrockModel(
    model_id=os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

agent = Agent(
    model=model,
    tools=[search_knowledge_base, create_ticket, get_ticket_status],
    system_prompt=SYSTEM_PROMPT,
)

register_observability_hooks(agent)


@app.entrypoint
def invoke(payload: dict) -> dict:
    cost_guard.reset()

    prompt = payload.get("prompt", "").strip()
    session_id = payload.get("session_id", "default")
    customer_id = payload.get("customer_id")

    if not prompt:
        return {"error": "Missing 'prompt' in payload"}

    if customer_id:
        prompt = f"[Customer ID: {customer_id}]\n\n{prompt}"

    try:
        result = agent(prompt)
        return {
            "response": str(result),
            "session_id": session_id,
        }
    except RuntimeError as e:
        if "budget exceeded" in str(e).lower() or "timeout" in str(e).lower():
            logger.warning(f"Cost guard triggered: {e}")
            return {"error": "Request exceeded resource limits. Please try a simpler query."}
        raise


if __name__ == "__main__":
    app.run()
```

**`requirements.txt`**:

```
bedrock-agentcore-starter-toolkit
strands-agents-tools>=0.1.6
bedrock-agentcore==1.4.3
aws-opentelemetry-distro>=0.10.0
strands-agents[otel]>=0.1.6
requests>=2.32.0
beautifulsoup4>=4.12.0
opentelemetry-sdk>=1.29.0
opentelemetry-api>=1.29.0
boto3>=1.37.0
```

**Complete GitHub Actions CI + Deploy (`.github/workflows/ci.yml`)**:

```yaml
name: CI/CD for Support Agent

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main, staging]

env:
  PYTHON_VERSION: "3.12"
  AWS_REGION: us-east-1

permissions:
  id-token: write
  contents: read
  pull-requests: write

jobs:
  lint:
    name: Lint & Security
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}", cache: pip }
      - run: pip install ruff mypy bandit
      - run: ruff check agent/ tests/
      - run: mypy agent/ --ignore-missing-imports
      - run: bandit -r agent/ -ll

  test:
    name: Unit & Integration Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}", cache: pip }
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Run tests
        run: pytest tests/unit tests/integration -v --cov=agent --cov-fail-under=80
        env:
          AGENT_OBSERVABILITY_ENABLED: "false"
          AWS_ACCESS_KEY_ID: testing
          AWS_SECRET_ACCESS_KEY: testing
          AWS_DEFAULT_REGION: us-east-1

  evals:
    name: LLM Evaluations
    runs-on: ubuntu-latest
    if: github.base_ref == 'main' && github.event_name == 'pull_request'
    needs: [lint, test]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}", cache: pip }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_CI_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - run: pip install -r requirements.txt -r requirements-dev.txt strands-agents-evals
      - name: Run evaluations
        run: pytest tests/evals -m eval --timeout=300 -v
        timeout-minutes: 20

  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: github.ref == 'refs/heads/staging' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}", cache: pip }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - run: pip install -r requirements.txt bedrock-agentcore-starter-toolkit
      - name: Deploy to Staging
        run: |
          agentcore configure \
            --entrypoint agent/agent.py \
            --name SupportAgent-Staging \
            --execution-role ${{ secrets.EXECUTION_ROLE_ARN }} \
            --s3 ${{ secrets.DEPLOY_BUCKET }}-staging \
            --deployment-type direct_code_deploy \
            --runtime PYTHON_3_12 \
            --env MODEL_ID=us.anthropic.claude-haiku-4-5 \
            --env ENVIRONMENT=staging
          agentcore deploy --auto-update-on-conflict
          agentcore invoke '{"prompt": "smoke test ping"}'

  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}", cache: pip }
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_DEPLOY_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}
      - run: pip install -r requirements.txt bedrock-agentcore-starter-toolkit
      - name: Deploy to Production
        run: |
          agentcore configure \
            --entrypoint agent/agent.py \
            --name SupportAgent-Production \
            --execution-role ${{ secrets.EXECUTION_ROLE_ARN }} \
            --s3 ${{ secrets.DEPLOY_BUCKET }}-production \
            --deployment-type direct_code_deploy \
            --runtime PYTHON_3_12 \
            --env MODEL_ID=us.anthropic.claude-sonnet-4-5 \
            --env ENVIRONMENT=production
          agentcore deploy --auto-update-on-conflict
      - name: Smoke test
        run: |
          RESULT=$(agentcore invoke '{"prompt": "Hello, can you help me?"}')
          echo "Response: $RESULT"
          echo "$RESULT" | python3 -c "
          import sys, json
          r = json.load(sys.stdin)
          assert 'error' not in r, f'Deploy failed smoke test: {r}'
          print('✅ Smoke test passed')
          "
      - name: Tag production deploy
        run: |
          git config user.email "ci@example.com"
          git config user.name "CI Bot"
          git tag "prod-$(date +%Y%m%d-%H%M%S)"
          git push --tags
```

### Local Developer Workflow Summary

```bash
# Day 1: Clone and set up
git clone https://github.com/myorg/support-agent.git
cd support-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
bash scripts/setup-hooks.sh

# Daily development
git checkout -b feature/TICKET-456-add-faq-tool
# ... edit code ...
pytest tests/unit -x -q                # Fast feedback
git add -p                              # Stage carefully
git commit -m "feat(tools): add FAQ search tool"   # Hook validates message
# pre-commit runs: lint, type-check, prompt validation

# Before pushing
git push origin feature/TICKET-456-add-faq-tool    # pre-push runs unit tests
# GitHub Actions CI runs: lint, unit tests, integration tests
# After PR review + merge → staging deploy
# After staging validation → production deploy (with approval gate)

# Deploying manually (emergency)
export AWS_REGION=us-east-1
agentcore configure --entrypoint agent/agent.py --name SupportAgent-Production \
  --execution-role arn:aws:iam::123456789012:role/bedrock-agentcore-runtime-role \
  --s3 my-deployments-production --deployment-type direct_code_deploy --runtime PYTHON_3_12
agentcore deploy --auto-update-on-conflict
agentcore invoke '{"prompt": "smoke test"}'
agentcore obs   # View traces
agentcore status
```


---

## Conclusion

Building AI agents is an iterative craft, but shipping them reliably requires engineering discipline. This guide has walked through every layer of the CI/CD stack for agents built with Strands Agents and deployed on AWS AgentCore.

### Key Takeaways

**On testing:**
- Unit tests should be fast and fully mocked — they are your first line of defense
- Integration tests with `moto` give real-enough coverage without real LLM cost
- LLM evaluations (Strands Evals) should gate only the highest-stakes branches (PRs to `main`)
- Golden datasets are living documents — update them when you change agent behavior

**On deployment:**
- `agentcore deploy --auto-update-on-conflict` is idempotent — safe to call from CI on every push
- Use separate agent names (e.g., `SupportAgent-Staging`, `SupportAgent-Production`) rather than branches within a single runtime
- Blue/green gives you the safest switch; canary gives you gradual confidence; automated rollback gives you a safety net

**On observability:**
- Set `AGENT_OBSERVABILITY_ENABLED=true` in production — it's low overhead and high value
- Instrument tool calls and LLM calls with custom spans to understand the agent's reasoning path
- Build CloudWatch dashboards for both infrastructure metrics (latency, errors) and AI metrics (token usage, tool call distribution)

**On secrets:**
- Pass secret **names** as environment variables, never secret **values**
- Use Secrets Manager with TTL caching for rotation support
- OIDC authentication in CI eliminates the need for long-lived AWS credentials entirely

**On costs:**
- Implement `CostGuard` to cap tokens, tool calls, and wall-clock time per invocation
- Tag all resources with `AgentName`, `Environment`, and `CostCenter` for precise billing attribution
- Use cheaper models (e.g., Claude Haiku) in staging/CI to reduce eval costs

### The CI/CD Maturity Model for AI Agents

```
Level 0 │ Manual deploy from local machine
Level 1 │ Automated deploy on merge (no tests)
Level 2 │ Unit tests + lint in CI before deploy
Level 3 │ Integration tests + secrets management + environment separation
Level 4 │ LLM evaluations + blue/green + automated rollback + cost controls
Level 5 │ Canary deployments + continuous evaluation + real-time safety monitoring
```

Most teams should target **Level 3** as their initial goal, with **Level 4** for production systems handling sensitive workloads. The tooling in this guide provides everything needed for both.

### What's Next

As the ecosystem evolves, watch for:

- **Strands Evals SDK enhancements** — richer evaluators for safety, faithfulness, and multi-turn conversations
- **AgentCore versioning** — native support for pinning specific agent versions rather than relying on git tags
- **AWS Bedrock Guardrails in CI** — automated content safety evaluation as a CI check
- **Model evaluation pipelines** — automated testing when the underlying LLM version changes

---

## References

### AWS Documentation
- [Amazon Bedrock AgentCore — User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- [AWS X-Ray — Service Map and Traces](https://docs.aws.amazon.com/xray/latest/devguide/aws-xray.html)
- [AWS CloudWatch — Metrics and Alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/)
- [AWS Secrets Manager — Rotation Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/)
- [AWS Budgets — Cost Control](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)
- [AWS OIDC in GitHub Actions](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_create_oidc.html)

### Strands Agents
- [Strands Agents — GitHub (Python SDK)](https://github.com/strands-agents/sdk-python)
- [Strands Agents — Documentation](https://strandsagents.com/)
- [Strands Agents Tools Package](https://github.com/strands-agents/tools)
- [Strands Evals SDK](https://strandsagents.com/latest/user-guide/evals/)
- [Strands Agents Observability Guide](https://strandsagents.com/latest/user-guide/observability/)

### AgentCore CLI
- [bedrock-agentcore-starter-toolkit (PyPI)](https://pypi.org/project/bedrock-agentcore-starter-toolkit/)
- [bedrock-agentcore SDK (PyPI)](https://pypi.org/project/bedrock-agentcore/)

### CI/CD & DevOps
- [GitHub Actions — OIDC with AWS](https://github.com/aws-actions/configure-aws-credentials)
- [AWS CodePipeline — User Guide](https://docs.aws.amazon.com/codepipeline/latest/userguide/)
- [pre-commit Framework](https://pre-commit.com/)
- [Conventional Commits Specification](https://www.conventionalcommits.org/)
- [OpenTelemetry Python SDK](https://opentelemetry.io/docs/languages/python/)

### Security & Quality
- [Bandit — Python Security Linter](https://bandit.readthedocs.io/)
- [detect-secrets](https://github.com/Yelp/detect-secrets)
- [moto — AWS Mock Library](https://docs.getmoto.org/)
- [Ruff — Python Linter](https://docs.astral.sh/ruff/)

---

*Tutorial compiled March 2026. AWS AgentCore and Strands Agents are active projects — always verify against the latest documentation for version-specific details.*

