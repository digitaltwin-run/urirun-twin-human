# Author: Tom Sapletta · Part of the ifURI solution.
"""human_llm_reason must not crash when llm_reason echoes ticket in res."""
from __future__ import annotations

from urirun_twin_human import core


def test_human_llm_reason_no_duplicate_ticket_kwarg(monkeypatch):
    monkeypatch.setattr(core, "load_person", lambda _p: {"name": "Tom", "competencies": "kvm"})
    monkeypatch.setattr(core, "llm_reason", lambda *a, **k: {
        "ok": True, "model": "m", "text": "ok", "ticket": "IFURI-229",
    })
    r = core.human_llm_reason(person_id="tom", prompt="next?", ticket="IFURI-229")
    assert r.get("ok") is True
    assert r.get("ticket") == "IFURI-229"
    assert r.get("text") == "ok"
