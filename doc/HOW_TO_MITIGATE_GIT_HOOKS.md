# Git Hooks — What They Are and How to Work With Them

## What are git hooks?

Git hooks are scripts that git runs automatically at specific points in the git workflow.
They live in `.git/hooks/` and are triggered by actions like `git commit`, `git push`, or `git merge`.
They are local to your machine — they are not committed to the repository and do not run in CI unless explicitly configured.

## What is pre-commit?

`pre-commit` is a framework that manages git hooks through a config file (`.pre-commit-config.yaml`).
Instead of writing raw shell scripts in `.git/hooks/`, you declare which hooks to run and pre-commit handles installation, versioning, and execution.

## Goal of git hooks in this project

The hooks in this project act as a first line of defense before code reaches GitHub.
They catch issues locally — faster and cheaper than catching them in CI.

Hooks configured in this project:

- `ruff` — lints and auto-formats Python code on every commit
- `ruff-format` — enforces consistent code style
- `detect-private-key` — blocks commits that contain private keys or credentials
- `check-added-large-files` — prevents committing files larger than 500KB (e.g. model weights, datasets)
- `bandit` — scans `agent/` for security vulnerabilities before every commit

## How to install

```bash
pip install pre-commit
pre-commit install
```

After this, hooks run automatically on every `git commit`.

> Note: On Amazon-managed machines, Code Defender sets `core.hooksPath` at the system level,
> which prevents pre-commit from installing hooks automatically. In this case, run hooks manually
> before committing (see below), and rely on CI (Step 6) for automated enforcement.

## How to run manually (without committing)

```bash
pre-commit run --all-files
```

## How to skip hooks for a single commit

If you need to commit urgently and the hooks are blocking you:

```bash
git commit --no-verify -m "your message"
```

Use this sparingly. Skipping hooks means skipping safety checks.

## How to pause hooks temporarily

```bash
pre-commit uninstall
```

This removes the hooks from `.git/hooks/` but keeps `.pre-commit-config.yaml`.
To re-enable:

```bash
pre-commit install
```

## How to remove hooks permanently

```bash
pre-commit uninstall
```

Then delete `.pre-commit-config.yaml` from the repo root.
Without the config file, `pre-commit install` has nothing to install.

## Important notes

- Hooks only run on your local machine after `pre-commit install` is run.
- New team members must run `pre-commit install` themselves after cloning the repo.
- Hooks do not replace CI — they are a fast local check, not a substitute for the full pipeline.
- The `.pre-commit-config.yaml` file is committed to the repo so all team members use the same hooks.
