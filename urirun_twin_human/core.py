# Author: Tom Sapletta · Part of the ifURI solution.
"""
urirun-twin-human — Digital Twin "human actors" exposed as URI processes.

Part of the urirun-twin-* series.

Purpose:
- Generate / instantiate digital twins that can "udawać" (impersonate) concrete actors/persons
  from the Digital Twin registry (digital-persons.json).
- The twins can perform human-like operations in the system:
  * Click / UI control (via kvm:// on nodes like "laptop"/lenovo)
  * Unblock tickets (via grants ledger + planfile status/labels + work queue)
  * Reason with LLM (OpenRouter via urirun/.env)
- Allows koru / autonomous loops to drive work that previously required real human
  (unblocks, approvals, desktop clicks) by delegating to a capable twin actor.

URI scheme: human:// or twin-human://
Examples:
  human://tom/ticket/command/unblock?ticket=IFURI-226&reason=autonomous
  human://claude-coder/kvm/command/click?node=laptop&x=120&y=340
  human://lenovo-node/llm/command/reason?prompt=Should I unblock this KVM ticket?

The actor carries the identity, competencies and grants of the chosen person.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Make sure we can import siblings in the monorepo during dev
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for p in (str(_ROOT / "urirun" / "adapters" / "python"),
          str(_ROOT / "urirun-connector-grants"),
          str(_ROOT / "urirun-connector-kvm")):
    if p not in sys.path:
        sys.path.insert(0, p)

import urirun

try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT / "urirun" / ".env")
except Exception:
    pass  # fall back to already-set env

import litellm

# --- persons / twin registry -------------------------------------------------

def _persons_file() -> Path:
    p = Path(os.environ.get("URIRUN_DIGITAL_PERSONS") or
             "~/.urirun/host-dashboard/digital-persons.json").expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_person(person_id: str) -> dict | None:
    try:
        data = json.loads(_persons_file().read_text(encoding="utf-8"))
        for p in data if isinstance(data, list) else []:
            if p.get("id") == person_id:
                # respect enable/disable (incl. temporary)
                if p.get("enabled") is False:
                    return None
                du = p.get("disabled_until")
                if du:
                    try:
                        now = __import__("time").time()
                        if isinstance(du, (int,float)) and du > now: return None
                        if isinstance(du, str):
                            from datetime import datetime
                            if datetime.fromisoformat(du.replace("Z","+00:00")).timestamp() > now: return None
                    except: pass
                return p
    except Exception:
        pass
    # fallback minimal human actor
    if person_id in ("tom", "human", "default"):
        return {
            "id": person_id,
            "type": "human",
            "name": person_id.title(),
            "competencies": ["unblock", "kvm", "click", "approve", "signal", "full"],
            "grants": ["unblock:*", "kvm:*", "ticket:*", "human:*"]
        }
    return {"id": person_id, "type": "human", "name": person_id, "competencies": ["unblock", "kvm"], "grants": []}


# --- LLM (OpenRouter from urirun/.env) ---------------------------------------

def _llm_model() -> str:
    """Primary executor model (LLM_MODEL_EXECUTOR).
    Szybki model wykonujący akcje i decyzje.
    """
    return (
        os.environ.get("LLM_MODEL_EXECUTOR")
        or os.environ.get("LLM_MODEL")
        or "openrouter/google/gemini-3.5-flash"
    )


def _llm_validator_model() -> str:
    """Drugi LLM (walidator) do sprawdzania wiedzy i świadomości modelu podstawowego (Gemini).
    Używany w fazie prepare_and_validate przed realnymi akcjami.
    """
    return (
        os.environ.get("LLM_MODEL_VALIDATOR")
        or "openrouter/deepseek/deepseek-v4-pro"
    )


def _llm_teacher_model() -> str:
    """Model nauczyciela specjalizujący się w analizie grafiki/obrazów (lepszy od Gemini w wizji).
    Używany do oceny zrzutów ekranu, low-res i quad crops.
    """
    return (
        os.environ.get("LLM_MODEL_TEACHER")
        or "openrouter/qwen/qwen3.7-plus"
    )


def _llm_executor_twin_model() -> str:
    """Drugi executor (blizniak) do porównywania wydajności i skuteczności.
    Używany razem z głównym executorem. Wybieramy lepszy na podstawie czasu + sukcesu.
    """
    return (
        os.environ.get("LLM_MODEL_EXECUTOR_TWIN")
        or "openrouter/minimax/minimax-m3"
    )


def _get_uri_processes_knowledge(node: str = "lenovo", ticket: dict | None = None) -> str:
    """Środowisko URI + katalog procesów — wspólny moduł z goal.py."""
    try:
        from urirun_runtime.ticket_llm_context import build_first_system_prompt, record_first_prompt
        prompt = build_first_system_prompt(ticket=ticket, node=node)
        if ticket:
            record_first_prompt(ticket, node, prompt)
        return prompt
    except Exception:  # noqa: BLE001
        return f"(uri catalog unavailable; node={node})"


def _mt(base_tokens: int) -> int:
    """Multiply a hardcoded max_tokens budget by LLM_MAX_TOKENS_MULTIPLIER (env, default 10x) —
    same convention as urirun_connector_work.goal._mt() — so responses aren't silently truncated.
    """
    try:
        mult = float(os.environ.get("LLM_MAX_TOKENS_MULTIPLIER", "10"))
    except ValueError:
        mult = 10.0
    return max(1, int(base_tokens * mult))


def _litellm_call_kwargs() -> dict[str, Any]:
    api_base = (
        os.environ.get("URIRUN_LLM_API_BASE")
        or os.environ.get("OPENAI_API_BASE")
        or os.environ.get("OPENROUTER_BASE_URL")
        or ""
    ).strip().rstrip("/")
    return {"api_base": api_base} if api_base else {}


def llm_reason(prompt: str, system: str = None, max_tokens: int = 800, *, use_validator: bool = False, use_teacher: bool = False, ticket: str | None = None, context: dict | None = None) -> dict:
    """Use OpenRouter (via litellm) to let the human twin reason about an action.

    use_validator=True → używa LLM_MODEL_VALIDATOR
    use_teacher=True  → używa LLM_MODEL_TEACHER (lepsza analiza obrazów/grafiki niż Gemini)
    ticket: optional ticket id for automatic tagging in LLM history
    context: opcjonalny dict (np. {"node": "lenovo"}) — steruje wstrzykiwaną wiedzą o URI-procesach.
    """
    model = _llm_validator_model() if use_validator else _llm_model()
    role = "validator/examiner" if use_validator else "executor"
    ticket_dict = None
    if ticket:
        ticket_dict = (context or {}).get("ticket") if isinstance((context or {}).get("ticket"), dict) else {"id": ticket}
    node = (context or {}).get("node", "lenovo") if context else "lenovo"
    uri_knowledge = ""
    try:
        uri_knowledge = "\n\n" + _get_uri_processes_knowledge(node, ticket=ticket_dict)
    except Exception:
        pass
    sys_msg = system or (
        "You are a digital twin acting as a specific human actor in the IF-URI autonomous system. "
        "You execute tickets via URI processes on nodes (e.g. lenovo), not ad-hoc Python scripts. "
        "When producing plans, output a ```urirun:processes``` JSON block (urirun-llm-runtime standard). "
        "Be precise, conservative on irreversible actions, and output JSON when asked."
        + uri_knowledge +
        "\nDECISION LOOP: intent->flow->execution->observation->nextIntent. Use router diagnose before, verify post, emit nextIntent on end. inquiry/reflection for continuous."
    )
    try:
        msgs = [{"role": "system", "content": sys_msg}]
        user_content = prompt
        if ticket:
            user_content = f"[ticket:{ticket}] {prompt}"
            # also add to system for context
            sys_msg = f"{sys_msg}\nCurrent ticket context: {ticket}. Include in any history/logs."
        msgs.append({"role": "user", "content": user_content})
        resp = litellm.completion(
            model=model,
            messages=msgs,
            max_tokens=_mt(max_tokens),
            temperature=0.15 if use_validator else 0.2,
            **_litellm_call_kwargs(),
        )
        content = resp.choices[0].message.content or ""
        if "{" in content:
            try:
                j = json.loads(content[content.find("{"):content.rfind("}")+1])
                return {"ok": True, "model": model, "role": role, "decision": j, "raw": content, "ticket": ticket}
            except Exception:
                pass
        return {"ok": True, "model": model, "role": role, "text": content, "ticket": ticket}
    except Exception as e:
        return {"ok": False, "model": model, "role": role, "error": str(e), "ticket": ticket}


def llm_prepare_and_validate(task_description: str, *, executor_model: str = None, validator_model: str = None, teacher_model: str = None, executor_twin_model: str = None, ticket: str | None = None, node: str = "lenovo") -> dict:
    """Pomocnik do przygotowania (triple LLM + executor twin):
    - executor (LLM_MODEL_EXECUTOR) + twin (LLM_MODEL_EXECUTOR_TWIN) — porównujemy prędkość i jakość
    - validator (LLM_MODEL_VALIDATOR) sprawdza wiedzę i wydaje PASS/FAIL
    - teacher (LLM_MODEL_TEACHER) analizuje grafikę (zrzuty ekranu) — lepszy od Gemini w wizji
    Wybieramy lepszy executor na podstawie czasu + skuteczności.
    """
    # Note: jeśli nie podano modeli, używa domyślnych z odpowiednich _llm_*_model() funkcji

    # Inject URI knowledge + environment (first prompt)
    uri_knowledge = _get_uri_processes_knowledge(node, ticket={"id": ticket, "name": task_description[:200]} if ticket else None)
    exec_m = executor_model or _llm_model()
    val_m = validator_model or _llm_validator_model()

    exec_resp = litellm.completion(
        model=exec_m,
        messages=[{"role": "user", "content": (
            f"{uri_knowledge}\n\n"
            "STANDARD: odpowiedź MUSI zawierać blok ```urirun:processes``` z JSON array "
            "(id, name, actor, uri, payload, depends_on). router diagnose przed keyboard.\n\n"
            f"Przygotuj plan jak wykonać zadanie:\n\n{task_description}\n node={node}\n"
            f"ticket={ticket or ''}"
        )}],
        max_tokens=_mt(1200),
        temperature=0.3,
        **_litellm_call_kwargs(),
    )
    exec_content = exec_resp.choices[0].message.content or ""
    plan_steps, plan_fmt = [], "none"
    try:
        from urirun_runtime.ticket_llm_context import parse_ticket_process_plan
        plan_steps, plan_fmt = parse_ticket_process_plan(exec_content)
    except Exception:
        pass

    val_prompt = (
        f"Jesteś surowym walidatorem.\n{uri_knowledge}\n\n"
        f"Zadanie: {task_description} node={node}\n\n"
        f"Raport Executora ({exec_m}):\n{exec_content}\n\n"
        "Oceń plan (czy ma blok urirun:processes z URI+payload + router diagnose). 0-100, verdict PASS/FAIL. JSON verdict,score,critical_gaps."
    )
    val_resp = litellm.completion(
        model=val_m,
        messages=[{"role": "user", "content": val_prompt}],
        max_tokens=_mt(900),
        temperature=0.1,
        **_litellm_call_kwargs(),
    )
    val_content = val_resp.choices[0].message.content or ""

    return {
        "executor_model": exec_m,
        "validator_model": val_m,
        "executor_report": exec_content,
        "validator_report": val_content,
        "plan": plan_steps,
        "plan_format": plan_fmt,
    }


# --- unblock (grants + planfile + work) --------------------------------------

def _import_unblock_ledger():
    try:
        from urirun_connector_grants import unblock_ledger as ul
        return ul
    except Exception:
        # direct fallback
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "unblock_ledger",
            str(_ROOT / "urirun-connector-grants" / "urirun_connector_grants" / "unblock_ledger.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def _import_planfile_adapter():
    try:
        from urirun.host import planfile_adapter as pa
        return pa
    except Exception:
        sys.path.insert(0, str(_ROOT / "urirun" / "adapters" / "python"))
        from urirun.host import planfile_adapter as pa
        return pa


def unblock_ticket_as(person_id: str, ticket_id: str, reason: str = "", labels_to_clean: list[str] | None = None) -> dict:
    """Human twin unblocks a ticket (per-type + per-ticket grant + force open + clean labels)."""
    ul = _import_unblock_ledger()
    pa = _import_planfile_adapter()

    person = load_person(person_id)
    note = f"[twin-human:{person_id}] {reason or 'autonomous unblock'}"

    # 1. record grant (so future similar tickets of type are also unblocked)
    ticket_dict = {"id": ticket_id, "labels": ["kvm", "lenovo", "signal", "approval", "waiting:*"], "name": ""}
    ul.record_unblock(ticket_id, ticket=ticket_dict, note=note, by=f"twin-human:{person_id}")

    # 2. force planfile state to open + ready, clean blocking labels
    clean_labels = [l for l in (labels_to_clean or []) if not any(x in l for x in ("actor:human", "approval", "waiting:"))]
    actor = f"twin-human:{person_id}"
    try:
        pa.update_ticket(None, ticket_id, {
            "status": "open",
            "labels": clean_labels or ["llm-ready", "kvm", "autonomous"],
        }, reason=note or "unblocked for autonomous work", actor=actor)
        pa.ready_ticket(None, ticket_id, note=note, reason=note or "unblocked", actor=actor)
    except Exception as e:
        # best effort
        pass

    # 3. also try via work queue style if available
    try:
        from urirun.host import work_queue as wq
        # wq has some unblock paths in handlers, but we did the core
    except Exception:
        pass

    return {
        "ok": True,
        "actor": person_id,
        "ticket": ticket_id,
        "granted_keys": [ticket_id, "kvm:lenovo", "unblock:*"],
        "note": note,
        "person_competencies": person.get("competencies", []),
    }


# --- kvm click (delegated through node / or direct connector) ---------------

def click_as(person_id: str, node: str = "laptop", x: int | None = None, y: int | None = None,
             text: str | None = None, key: str | None = None, reason: str = "") -> dict:
    """Human twin performs click / type / key on a KVM-controlled node (e.g. lenovo laptop)."""
    person = load_person(person_id)
    note = f"[twin-human:{person_id}] {reason or 'kvm action'}"

    # Prefer calling the live node if possible (same pattern as signal-gui)
    # Respect digital twin mode: if lenovo-node is "sim", we simulate inside click_as too
    try:
        from urirun.host import ticket_meta
        mode = ticket_meta.get_digital_person_mode("lenovo-node")
    except Exception:
        mode = "real"
    if mode == "sim":
        # simulate exactly like real for testing (no hardware)
        steps = []
        if x is not None and y is not None:
            steps.append({"op": "click", "x": x, "y": y})
        if text:
            steps.append({"op": "type", "text": text})
        if key:
            steps.append({"op": "key", "keys": key})
        return {"ok": True, "actor": person_id, "node": node, "steps": steps, "simulated": True, "via": "digital-twin-lenovo", "note": note}
    node_url = os.environ.get("URIRUN_LENOVO_URL") or os.environ.get("LENOVO_NODE") or "http://192.168.188.201:8765"

    steps = []
    if x is not None and y is not None:
        steps.append({"op": "click", "x": x, "y": y})
    if text:
        steps.append({"op": "type", "text": text})
    if key:
        steps.append({"op": "key", "keys": key})

    if steps:
        try:
            import urllib.request
            body = json.dumps({"uri": f"kvm://{node}/task/command/run", "payload": {"steps": steps}}).encode()
            req = urllib.request.Request(f"{node_url}/run", data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.loads(r.read().decode())
                return {"ok": True, "actor": person_id, "node": node, "steps": steps, "result": res, "note": note}
        except Exception as e:
            return {"ok": False, "actor": person_id, "error": str(e), "fallback": "would have executed via kvm"}

    return {"ok": True, "actor": person_id, "node": node, "simulated": True, "note": note,
            "hint": "Provide x,y or text or key. In real run this calls kvm:// on the node."}


# --- high level reason + act -------------------------------------------------

def act_as_human(person_id: str, goal: str, context: dict | None = None, ticket: str | None = None, node: str = "lenovo") -> dict:
    """LLM-powered human twin decides and (optionally) executes an action."""
    person = load_person(person_id)
    ctx = dict(context or {})
    if ticket:
        ctx["ticket"] = ticket

    prompt = (
        f"You are the digital twin acting as human '{person_id}' ({person.get('name')}).\n"
        f"Competencies: {person.get('competencies')}\n"
        f"Goal: {goal}\n"
        f"Context: {json.dumps(ctx, ensure_ascii=False)[:2000]}\n\n"
        "Decide the next concrete action. Output JSON with keys: action (unblock|click|noop), "
        "ticket_id?, node?, x?, y?, text?, reason, confidence (0-1)."
    )
    decision = llm_reason(prompt, system="Act as precise autonomous human operator in IF-URI system.", ticket=ticket)

    action = (decision.get("decision") or decision).get("action", "noop") if isinstance(decision.get("decision"), dict) else "noop"

    result = {"actor": person_id, "goal": goal, "decision": decision}

    if action == "unblock" and ctx.get("ticket_id"):
        result["unblock"] = unblock_ticket_as(person_id, ctx["ticket_id"], reason=goal)
    elif action == "click":
        result["click"] = click_as(person_id, node=ctx.get("node", "laptop"),
                                   x=ctx.get("x"), y=ctx.get("y"), text=ctx.get("text"))

    return result


# --- URI connector registration ----------------------------------------------

CONNECTOR_ID = "twin-human"
conn = urirun.connector(CONNECTOR_ID, scheme="human")


@conn.handler("actor/command/impersonate", isolated=False,
              meta={"label": "Create/activate a digital twin impersonating a specific person from the registry"})
def human_impersonate(person_id: str = "tom") -> dict[str, Any]:
    p = load_person(person_id)
    return urirun.ok(connector=CONNECTOR_ID, action="impersonate", person=p,
                     message=f"Now acting as {p.get('name', person_id)} (type={p.get('type')})")


@conn.handler("ticket/command/unblock", isolated=True,
              meta={"label": "Human twin unblocks a ticket (grants + open + clean labels)"})
def human_ticket_unblock(person_id: str = "tom", ticket_id: str = "", reason: str = "autonomous human twin") -> dict[str, Any]:
    if not ticket_id:
        return urirun.fail("ticket_id required", connector=CONNECTOR_ID, action="unblock")
    res = unblock_ticket_as(person_id, ticket_id, reason=reason)
    return urirun.ok(connector=CONNECTOR_ID, action="unblock", **res)


@conn.handler("kvm/command/click", isolated=True,
              meta={"label": "Human twin performs click/type/key on KVM node (e.g. lenovo laptop)"})
def human_kvm_click(person_id: str = "tom", node: str = "laptop", **kwargs) -> dict[str, Any]:
    res = click_as(person_id, node=node, **{k: v for k, v in kwargs.items() if k in ("x", "y", "text", "key")})
    return urirun.ok(connector=CONNECTOR_ID, action="kvm-click", **res)


@conn.handler("llm/command/reason", isolated=False,
              meta={"label": "Let the human twin (LLM from OpenRouter) reason about a situation"})
def human_llm_reason(person_id: str = "tom", prompt: str = "", context: dict | None = None, ticket: str | None = None) -> dict[str, Any]:
    p = load_person(person_id)
    ctx = dict(context or {})
    if ticket:
        ctx["ticket"] = ticket
    sys = f"You are {p.get('name')} (competencies: {p.get('competencies')}). Act as this person. Context: {ctx}"
    res = llm_reason(prompt or "What should I do next?", system=sys, ticket=ticket, context=ctx)
    if "ticket" in res:
        res = dict(res)
        res.pop("ticket", None)
    return urirun.ok(connector=CONNECTOR_ID, action="reason", person=person_id, ticket=ticket, **res)


@conn.handler("action/command/execute", isolated=True,
              meta={"label": "High-level: LLM decides + executes (unblock or click) as the human actor"})
def human_action_execute(person_id: str = "tom", goal: str = "", context: dict | None = None) -> dict[str, Any]:
    res = act_as_human(person_id, goal, context)
    return urirun.ok(connector=CONNECTOR_ID, action="execute", **res)


def urirun_bindings() -> dict[str, Any]:
    return conn.bindings()


# Convenience for direct use
def get_actor(person_id: str):
    return load_person(person_id)


def act_as_human_direct(person_id: str, goal: str, context: dict | None = None):
    return act_as_human(person_id, goal, context)
