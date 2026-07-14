#!/usr/bin/env python3
"""
Quickstart for urirun-twin-human.

Demonstrates creating human digital twin actors that can:
- impersonate persons from the registry
- unblock tickets
- reason with OpenRouter LLM (from urirun/.env)
- perform (or simulate) KVM clicks
"""

import os
import sys
sys.path.insert(0, "..")

from urirun_twin_human.core import (
    get_actor,
    human_impersonate,
    human_ticket_unblock,
    human_kvm_click,
    human_llm_reason,
    act_as_human,
    load_person,
)

print("=== urirun-twin-human quickstart ===\n")

# 1. Load / impersonate an actor (uses digital-persons.json or fallback)
actor = "tom"
print("Actor profile:", get_actor(actor))

print("\n--- Impersonate via URI handler ---")
print(human_impersonate(person_id=actor))

# 2. Unblock a ticket as this human twin (records grant + opens)
print("\n--- Unblock ticket (simulated) ---")
print(human_ticket_unblock(person_id=actor, ticket_id="IFURI-226",
                           reason="kolejno: autonomous human twin unblock via urirun-twin-human"))

# 3. LLM reasoning (uses OPENROUTER_API_KEY + LLM_MODEL from urirun/.env)
print("\n--- LLM reason as the actor ---")
reason = human_llm_reason(
    person_id=actor,
    prompt="Ticket IFURI-226 is open for sending a Signal message on lenovo via KVM. "
           "Should I unblock it and then use kvm://laptop to type the message? "
           "Current grants exist for kvm:lenovo. Answer with decision + short justification."
)
print(reason)

# 4. High-level act (LLM decides + can execute unblock/click)
print("\n--- High level act_as_human ---")
result = act_as_human(
    person_id="claude-coder",   # digital with kvm competency
    goal="Unblock IFURI-226 and prepare a KVM click sequence on lenovo to send the Signal message",
    context={"ticket_id": "IFURI-226", "node": "laptop"}
)
print(result)

# 5. KVM click example (will try real node if URIRUN_LENOVO_URL reachable, else simulate)
print("\n--- KVM action (as human) ---")
print(human_kvm_click(person_id=actor, node="laptop", x=300, y=500,
                      text="Test message from twin", reason="demo click+type"))

print("\nDone. The twin can now be driven via URI from koru, work queue, or other agents.")
print("Example URIs:")
print("  human://tom/ticket/command/unblock?ticket=IFURI-XXX")
print("  human://claude-coder/kvm/command/click?node=laptop&x=..&y=..")
print("  human://tom/action/command/execute?goal=...")
