# Biblical News Agent

An AWS Bedrock AgentCore agent that rewrites modern news in biblical Hebrew style.
Built as a learning project for CI/CD pipelines with Bedrock AgentCore.

## What it does

Takes a news headline as input and returns a rewrite in the style of the Hebrew Bible,
drawing from local bible text files as reference.

## Quick start

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in values
export $(cat .env | xargs) && export AWS_PROFILE=<your-profile> && python -m agent.agent
```

Then in another terminal:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-1", "session_id": "s-1"}'
```

## Documentation

| Document | Read when |
|---|---|
| [doc/Deployment.md](doc/Deployment.md) | Understanding the CI/CD pipeline design — what each step does and why |
| [doc/ENVIRONMENT_SETUP.md](doc/ENVIRONMENT_SETUP.md) | Setting up the environment for the first time — AWS roles, GitHub secrets, first deploy |
| [doc/CI_GUIDE.md](doc/CI_GUIDE.md) | A PR check failed — how to fix it, or how to add a new required check |
| [doc/HOW_TO_MITIGATE_GIT_HOOKS.md](doc/HOW_TO_MITIGATE_GIT_HOOKS.md) | Pre-commit hooks are blocked on your machine |

## Project structure

```
agent/              # agent source code
  agent.py          # entrypoint — BedrockAgentCoreApp
  tools/bible.py    # fetch_local_bible tool
  prompts/          # system prompt
tests/
  unit/             # fast tests, no AWS calls
  integration/      # requires local server running
doc/                # all documentation
.github/workflows/
  ci.yml            # lint + tests on every PR
  deploy.yml        # deploy to AgentCore on merge to main (agent/ changes only)
resources/bible_md/ # 39 bible books as markdown files
```

## CI/CD

Every PR to `main` runs lint (ruff, bandit) and unit tests via GitHub Actions.
Every merge to `main` that touches `agent/` triggers an automatic deploy to Bedrock AgentCore.
