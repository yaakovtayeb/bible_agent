"""
Integration test for local agent. Requires the agent running locally:
    python agent/agent.py
"""

import pytest
import requests

BASE_URL = "http://localhost:8080/invocations"


def is_server_running():
    try:
        requests.get("http://localhost:8080", timeout=2)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not is_server_running(), reason="local agent not running")
def test_agent_returns_hebrew_response():
    resp = requests.post(
        BASE_URL,
        json={"news": "ממשלת ישראל אישרה תקציב חדש", "actor_id": "user-test", "session_id": "session-test"},
        timeout=60,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert len(data["result"]) > 0
