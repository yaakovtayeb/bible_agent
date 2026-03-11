# AWS Setup Guide — Manual Steps to Reproduce This Environment

This document lists every AWS, GitHub, and local setup step that is NOT in the code.
Run these once per machine / AWS account / GitHub repo when setting up a new environment.

---

## Prerequisites

- AWS CLI configured with sufficient permissions (IAM, Bedrock)
- Python 3.12+
- `git` installed

---

## 0. SSH and Git setup (one-time per machine)

This project uses a personal GitHub account (`yaakovtayeb`) separate from a work account.
SSH config lets you use different keys per host alias.

```bash
# Generate a dedicated SSH key for the personal GitHub account
ssh-keygen -t ed25519 -C "your-personal-email@example.com" -f ~/.ssh/id_ed25519_personal

# Add to SSH agent
ssh-add ~/.ssh/id_ed25519_personal

# Print the public key — paste this into GitHub > Settings > SSH keys
cat ~/.ssh/id_ed25519_personal.pub
```

Add this block to `~/.ssh/config` (create the file if it does not exist):

```
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

Test the connection:

```bash
ssh -T git@github-personal
# Expected: Hi yaakovtayeb! You've successfully authenticated...
```

---

## 1. Clone and install dependencies

```bash
# Uses the SSH alias defined in ~/.ssh/config above
git clone git@github-personal:yaakovtayeb/bible_agent.git
cd bible_agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in real values:
# MODEL_ID, MEMORY_ID, AWS_REGION, MAX_TOKENS, LOCAL_MODE
```

---

## 3. Create the GitHub OIDC provider in AWS

Run once per AWS account:

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

---

## 4. Create the CI IAM role

Replace `<ACCOUNT_ID>` and `<GITHUB_USERNAME>/<REPO_NAME>` with your values:

```bash
aws iam create-role \
  --role-name GitHubActions-BibleAgent-CI \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"},
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_USERNAME>/<REPO_NAME>:*"
        }
      }
    }]
  }'

aws iam put-role-policy \
  --role-name GitHubActions-BibleAgent-CI \
  --policy-name BibleAgentCIPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": "*"
    }]
  }'
```

---

## 5. Add GitHub secrets

Go to: github.com > your repo > Settings > Secrets and variables > Actions

| Secret name | Value |
|---|---|
| `AWS_CI_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-CI` |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-Deploy` (Step 7) |

---

## 6. Enable branch protection on main

Go to: github.com > your repo > Settings > Branches > Add rule

- Branch name pattern: `main`
- Enable: Require a pull request before merging
- Enable: Require status checks to pass
- Add checks: `Lint`, `Unit Tests` (available after first CI run)

---

## 7. Install pre-commit hooks (optional — blocked on Amazon machines)

```bash
pip install pre-commit
pre-commit install
```

On Amazon-managed machines, Code Defender sets `core.hooksPath` at the system level
which blocks pre-commit installation. Run hooks manually instead:

```bash
pre-commit run --all-files
```

---

## 8. Run the agent locally

```bash
export $(cat .env | xargs) && export AWS_PROFILE=<your-profile> && python -m agent.agent
```

In another terminal:
```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-1", "session_id": "s-1"}'
```
