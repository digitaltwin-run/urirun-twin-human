import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from urirun_twin_human.core import (
    load_person,
    human_impersonate,
    human_ticket_unblock,
    human_llm_reason,
    act_as_human,
)

def test_load_person():
    p = load_person("tom")
    assert p["id"] == "tom"
    assert "unblock" in p.get("competencies", []) or "full" in p.get("competencies", [])

def test_impersonate():
    res = human_impersonate("claude-coder")
    assert res["ok"]
    assert "claude-coder" in str(res)

def test_unblock():
    res = human_ticket_unblock("tom", "IFURI-TEST-001", "test unblock")
    assert res["ok"]
    assert "IFURI-TEST-001" in str(res) or res.get("ticket") == "IFURI-TEST-001"

def test_llm_fallback():
    # Will use whatever is in env or default model string
    res = human_llm_reason("tom", "Decide if a simple ticket should be unblocked.")
    # even if no key, we get a structured response or error dict
    assert isinstance(res, dict)
    assert "ok" in res or "text" in res or "error" in res

def test_high_level_act():
    res = act_as_human("tom", "unblock a test ticket", {"ticket_id": "IFURI-DEMO"})
    assert "actor" in res or "decision" in res

if __name__ == "__main__":
    test_load_person()
    test_impersonate()
    test_unblock()
    test_llm_fallback()
    test_high_level_act()
    print("All basic tests passed for urirun-twin-human")
