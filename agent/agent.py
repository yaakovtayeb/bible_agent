"""
Biblical News Agent - AgentCore Runtime (CloudWatch Observability)
User provides news text; agent rewrites it in biblical Hebrew style.
STM via Strands AgentCoreMemorySessionManager — session/actor swappable per invocation.
"""

import os
import sys
from pathlib import Path

# When run as a script by AgentCore runtime, the parent dir is not on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

from agent.tools.bible import fetch_local_bible

os.environ["AGENT_OBSERVABILITY_ENABLED"] = "true"

MODEL_ID = os.environ["MODEL_ID"]
MEMORY_ID = os.environ["MEMORY_ID"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "16384"))

app = BedrockAgentCoreApp()
model = BedrockModel(model_id=MODEL_ID, max_tokens=MAX_TOKENS)

SYSTEM_PROMPT = Path(__file__).parent / "prompts" / "system_prompt.txt"
SYSTEM_PROMPT = SYSTEM_PROMPT.read_text(encoding="utf-8")

LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() == "true"


@app.entrypoint
def invoke(payload):
    news_text = payload.get("news", "") if isinstance(payload, dict) else ""
    actor_id = payload.get("actor_id", "default-user") if isinstance(payload, dict) else "default-user"
    session_id = payload.get("session_id", "default-session") if isinstance(payload, dict) else "default-session"

    session_manager = None
    if not LOCAL_MODE:
        config = AgentCoreMemoryConfig(
            memory_id=MEMORY_ID,
            actor_id=actor_id,
            session_id=session_id,
        )
        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=REGION,
        )

    agent = Agent(
        model=model,
        tools=[fetch_local_bible],
        system_prompt=SYSTEM_PROMPT,
        **({"session_manager": session_manager} if session_manager else {}),
    )

    try:
        response = agent(f"חדשה לשכתוב:\n{news_text}")
        result_text = response.message["content"][0]["text"]
    except Exception as e:
        if "MaxTokensReachedException" in type(e).__name__:
            result_text = str(e)
        else:
            raise
    finally:
        if session_manager:
            session_manager.close()

    return {"result": result_text, "session_id": session_id, "actor_id": actor_id}


if __name__ == "__main__":
    app.run()
