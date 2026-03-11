"""
Biblical News Agent - AgentCore Runtime (CloudWatch Observability)
User provides news text; agent rewrites it in biblical Hebrew style.
STM via Strands AgentCoreMemorySessionManager — session/actor swappable per invocation.
"""

import os
import re

import requests
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bs4 import BeautifulSoup
from strands import Agent, tool
from strands.models import BedrockModel

os.environ["AGENT_OBSERVABILITY_ENABLED"] = "true"

MEMORY_ID = os.environ.get("MEMORY_ID", "BiblicalNewsAgent_CloudWatch_mem-dPJBb549Dg")
REGION = os.environ.get("AWS_REGION", "us-east-1")

app = BedrockAgentCoreApp()
MODEL_ID = "arn:aws:bedrock:us-east-1:019904893923:application-inference-profile/xgxp6saj37q7"
MODEL_ID
model = BedrockModel(model_id=MODEL_ID)

SYSTEM_PROMPT = (
    "אתה סופר עברי עתיק, בקי בלשון המקרא. "
    "המשתמש ישלח לך חדשה עכשווית. "
    "עליך לשכתב אותה בסגנון לשון המקרא, כפי שהנביאים היו כותבים. "
    "השתמש בכלי fetch_bible_text כדי למצוא פסוקים רלוונטיים ולשלב אותם בסגנונך. "
    "כל פלט יהיה בעברית בלבד."
)


@tool
def fetch_bible_text(query: str) -> str:
    """Fetch relevant biblical text from mechon-mamre. Args: query: topic or keyword to look for."""
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "he,en-US;q=0.9"}
    try:
        resp = requests.get("https://mechon-mamre.org/i/t/t15.htm", headers=headers, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r" {3,}", " ", text).strip()[:3000]
    except Exception as e:
        return f"Error: {e}"


@app.entrypoint
def invoke(payload):
    news_text = payload.get("news", "") if isinstance(payload, dict) else ""
    actor_id = payload.get("actor_id", "default-user") if isinstance(payload, dict) else "default-user"
    session_id = payload.get("session_id", "default-session") if isinstance(payload, dict) else "default-session"

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
        tools=[fetch_bible_text],
        system_prompt=SYSTEM_PROMPT,
        session_manager=session_manager,
    )

    try:
        response = agent(f"חדשה לשכתוב:\n{news_text}")
        result_text = response.message["content"][0]["text"]
    finally:
        session_manager.close()

    return {"result": result_text, "session_id": session_id, "actor_id": actor_id}


if __name__ == "__main__":
    app.run()

# agentcore invoke '{"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-123", "session_id": "chat-456"}'
