# Environment Setup Runbook

This is a step-by-step runbook for setting up the full environment from scratch.
Each step shows: what to run, what it produces, and exactly where that output goes.

Steps 0-2 are one-time machine setup. Steps 3-8 are one-time per AWS account.
Steps 9-11 are one-time per GitHub repo.

---

## What you will need before starting

- AWS CLI configured with an IAM profile that has permissions to create IAM roles and Bedrock resources
- Python 3.12+
- `git` installed
- A GitHub account

---

## Step 0 — SSH and Git setup (one-time per machine)

```bash
ssh-keygen -t ed25519 -C "your-email@example.com" -f ~/.ssh/id_ed25519_personal
ssh-add ~/.ssh/id_ed25519_personal
cat ~/.ssh/id_ed25519_personal.pub   # paste this into GitHub > Settings > SSH keys
```

Add to `~/.ssh/config`:

```
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_personal
    IdentitiesOnly yes
```

Test: `ssh -T git@github-personal`

---

## Step 1 — Clone and install

```bash
git clone git@github-personal:yaakovtayeb/bible_agent.git
cd bible_agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## Step 2 — Set up .env

```bash
cp .env.example .env
```

Edit `.env`. You will fill in `MEMORY_ID` after Step 6. Leave it empty for now.

| Variable | Where to get it |
|---|---|
| `MODEL_ID` | Use `us.anthropic.claude-sonnet-4-6` |
| `MEMORY_ID` | Populated after Step 7 (first deploy) |
| `AWS_REGION` | `us-east-1` |
| `MAX_TOKENS` | `16384` |
| `LOCAL_MODE` | `false` for real deploy, `true` to skip memory locally |

---

## Step 3 — Create GitHub OIDC provider in AWS (once per account)

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
  --profile <your-profile>
```

Output: `arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com`
-> No further action needed. Used implicitly by Steps 4 and 5.

---

## Step 4 — Create the CI IAM role

This role is assumed by GitHub Actions during CI (lint + tests on every PR).

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
        "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
        "StringLike": {"token.actions.githubusercontent.com:sub": "repo:<GITHUB_USERNAME>/<REPO_NAME>:*"}
      }
    }]
  }' --profile <your-profile>

aws iam put-role-policy \
  --role-name GitHubActions-BibleAgent-CI \
  --policy-name BibleAgentCIPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"], "Resource": "*"}]
  }' --profile <your-profile>
```

Output: `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-CI`
-> Add as GitHub secret `AWS_CI_ROLE_ARN` (see Step 9)

---

## Step 5 — Create the Deploy IAM role

This role is assumed by GitHub Actions on every merge to main to run `agentcore deploy`.

```bash
aws iam create-role \
  --role-name GitHubActions-BibleAgent-Deploy \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"},
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_USERNAME>/<REPO_NAME>:ref:refs/heads/main"
        }
      }
    }]
  }' --profile <your-profile>

aws iam put-role-policy \
  --role-name GitHubActions-BibleAgent-Deploy \
  --policy-name BibleAgentDeployPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream",
        "bedrock-agentcore:CreateAgentRuntime", "bedrock-agentcore:UpdateAgentRuntime",
        "bedrock-agentcore:GetAgentRuntime", "bedrock-agentcore:ListAgentRuntimes",
        "bedrock-agentcore:CreateAgentRuntimeEndpoint", "bedrock-agentcore:UpdateAgentRuntimeEndpoint",
        "bedrock-agentcore:GetAgentRuntimeEndpoint", "bedrock-agentcore:InvokeAgentRuntime",
        "ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:CreateRepository", "iam:PassRole",
        "s3:CreateBucket", "s3:PutObject", "s3:GetObject",
        "codebuild:CreateProject", "codebuild:StartBuild", "codebuild:BatchGetBuilds"
      ],
      "Resource": "*"
    }]
  }' --profile <your-profile>
```

Output: `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-Deploy`
-> Add as GitHub secret `AWS_DEPLOY_ROLE_ARN` (see Step 9)

---

## Step 6 — Create the AgentCore execution role

This role is assumed by the agent runtime itself inside Bedrock AgentCore.
The trust policy file `ci-role-trust-policy.json` is in the repo root — update `<ACCOUNT_ID>` in it first.

```bash
aws iam create-role \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1 \
  --description "Execution role for BedrockAgentCore Runtime - BiblicalNewsAgent_CloudWatch" \
  --assume-role-policy-document file://ci-role-trust-policy.json \
  --profile <your-profile>

aws iam put-role-policy \
  --role-name AmazonBedrockAgentCoreSDKRuntime-us-east-1 \
  --policy-name BedrockAgentCoreRuntimeExecutionPolicy-BiblicalNewsAgent_CloudWatch \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {"Effect": "Allow", "Action": ["logs:DescribeLogStreams", "logs:CreateLogGroup"], "Resource": ["arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/*"]},
      {"Effect": "Allow", "Action": ["logs:DescribeLogGroups"], "Resource": ["arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:*"]},
      {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": ["arn:aws:logs:us-east-1:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"]},
      {"Effect": "Allow", "Action": ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"], "Resource": ["*"]},
      {"Effect": "Allow", "Action": "cloudwatch:PutMetricData", "Resource": "*", "Condition": {"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}}},
      {"Effect": "Allow", "Action": ["logs:CreateLogGroup", "logs:PutDeliverySource", "logs:PutDeliveryDestination", "logs:CreateDelivery", "logs:GetDeliverySource", "logs:DeleteDeliverySource", "logs:DeleteDeliveryDestination"], "Resource": "*"},
      {"Sid": "BedrockModelInvocation", "Effect": "Allow", "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ApplyGuardrail"], "Resource": ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:*:*:inference-profile/*", "arn:aws:bedrock:us-east-1:<ACCOUNT_ID>:*"]},
      {"Sid": "MarketplaceSubscribeOnFirstCall", "Effect": "Allow", "Action": ["aws-marketplace:ViewSubscriptions", "aws-marketplace:Subscribe"], "Resource": "*", "Condition": {"StringEquals": {"aws:CalledViaLast": "bedrock.amazonaws.com"}}},
      {"Sid": "AwsJwtFederation", "Effect": "Allow", "Action": "sts:GetWebIdentityToken", "Resource": "*"}
    ]
  }' --profile <your-profile>
```

Output: `arn:aws:iam::<ACCOUNT_ID>:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1`
-> Used in Step 7 as `--execution-role`

---

## Step 7 — Configure and deploy the agent (first time)

This generates `.bedrock_agentcore.yaml`, creates the memory, and deploys the runtime.

```bash
# Delete any existing config to start fresh
rm -rf .bedrock_agentcore .bedrock_agentcore.yaml

# Configure — generates .bedrock_agentcore.yaml
export $(cat .env | xargs) && export AWS_PROFILE=<your-profile> && agentcore configure \
  --name BiblicalNewsAgent_CloudWatch \
  --entrypoint agent/agent.py \
  --execution-role arn:aws:iam::<ACCOUNT_ID>:role/AmazonBedrockAgentCoreSDKRuntime-us-east-1 \
  --region us-east-1 \
  --non-interactive

# Fix hardcoded local paths in the generated yaml:
# - entrypoint: agent/agent.py
# - source_path: .

# Deploy — creates S3 bucket, builds via CodeBuild, creates memory, deploys runtime
agentcore deploy
```

After deploy, read the memory ID:

```bash
python -c "
import yaml
with open('.bedrock_agentcore.yaml') as f:
    cfg = yaml.safe_load(f)
agent = cfg['agents']['BiblicalNewsAgent_CloudWatch']
print('memory_id:', agent['memory']['memory_id'])
print('agent_id: ', agent['bedrock_agentcore']['agent_id'])
"
```

Output: `memory_id: BiblicalNewsAgent_CloudWatch_mem-XXXXXXXXX`
-> Set `MEMORY_ID=<value>` in `.env`
-> Add as GitHub secret `MEMORY_ID` (see Step 9)

Deploy takes 5-10 minutes. To check when the runtime is live:

```bash
agentcore status --profile <your-profile>
```

Wait until status shows `READY`. Then invoke the deployed runtime directly:

```bash
agentcore invoke \
  '{"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-1", "session_id": "s-1"}' \
  --profile <your-profile>
```

---

## Step 8 — Verify model access

Confirm the model works in your account before running the agent:

```bash
AWS_PROFILE=<your-profile> python -c "
import boto3
client = boto3.client('bedrock-runtime', region_name='us-east-1')
resp = client.converse(
    modelId='us.anthropic.claude-sonnet-4-6',
    messages=[{'role': 'user', 'content': [{'text': 'say hello'}]}]
)
print(resp['output']['message']['content'][0]['text'])
"
```

If this fails, go to AWS Console > Bedrock > Model access and enable the model.

---

## Step 9 — Add GitHub secrets

Go to: github.com > your repo > Settings > Secrets and variables > Actions

| Secret name | Value | Where it comes from |
|---|---|---|
| `AWS_CI_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-CI` | Step 4 output |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::<ACCOUNT_ID>:role/GitHubActions-BibleAgent-Deploy` | Step 5 output |
| `MODEL_ID` | `us.anthropic.claude-sonnet-4-6` | Step 8 |
| `MEMORY_ID` | `BiblicalNewsAgent_CloudWatch_mem-XXXXXXXXX` | Step 7 output |

If you need to look up the role ARNs after the fact:

```bash
aws iam get-role --role-name GitHubActions-BibleAgent-CI --query 'Role.Arn' --profile <your-profile>
aws iam get-role --role-name GitHubActions-BibleAgent-Deploy --query 'Role.Arn' --profile <your-profile>
```

---

## Step 10 — Enable branch protection on main

Go to: github.com > your repo > Settings > Branches > Add rule

- Branch name pattern: `main`
- Require a pull request before merging
- Require status checks to pass: `Lint`, `Unit Tests`

---

## Step 11 — Run the agent locally

```bash
export $(cat .env | xargs) && export AWS_PROFILE=<your-profile> && python -m agent.agent
```

In another terminal:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-1", "session_id": "s-1"}'
```

---

## Step 12 — Pre-commit hooks (optional, blocked on Amazon machines)

```bash
pip install pre-commit
pre-commit install
```

On Amazon-managed machines, Code Defender sets `core.hooksPath` at the system level
which blocks pre-commit. Run manually instead:

```bash
pre-commit run --all-files
```
