# urirun-twin-human

Digital Twin "human actors" from the **urirun-twin-*** series.

Exposes **URI processes** (`human://...`) that let digital twins impersonate concrete persons from the Digital Twin registry (`digital-persons.json`).

These twins can:
- **Unblock tickets** (record grants via unblock_ledger + force planfile open/ready + clean blocking labels like `actor:human`, `waiting:*`)
- **Click / control desktops** via KVM (on lenovo "laptop", nvidia etc.)
- **Reason with LLM** (OpenRouter — uses three complementary roles loaded from `urirun/.env`:
  - `LLM_MODEL_EXECUTOR` — fast actor (Gemini 3.5 Flash)
  - `LLM_MODEL_VALIDATOR` — knowledge & safety checker
  - `LLM_MODEL_TEACHER` — graphics/image analysis specialist (stronger vision than Gemini for UI screenshots))
- Act with the identity/competencies/grants of a chosen person (e.g. `tom`, `claude-coder`, custom "human-actor")

## Goal in the system
Make autonomous loops (koru + work queue) able to perform steps that used to require a real human:
- Unblock waiting tickets
- Perform GUI clicks on controlled nodes (lenovo desktop via KVM)
- Decide using LLM while "pretending" to be a specific actor

## URI scheme

`human://<person_id>/...`

Examples (direct use):

```bash
# Impersonate
human://tom/actor/command/impersonate

# Unblock a ticket (as this actor)
human://tom/ticket/command/unblock?ticket=IFURI-226&reason="kolejno autonomous unblock via twin"

# KVM click / type on lenovo laptop (as the actor)
human://lenovo-node/kvm/command/click?node=laptop&x=420&y=180
human://tom/kvm/command/click?node=laptop&text="hello mateusz"&key=return

# LLM reasoning as the person
human://claude-coder/llm/command/reason?prompt="Should I unblock this KVM ticket now?"

# High-level execute (LLM decides + acts)
human://tom/action/command/execute?goal="unblock IFURI-226 and send signal via desktop"
```

When using `urirun start` / koru loop the delegation is automatic — you don't need to call `human://` manually for kvm tickets.

## Logging of real commands

All `kvm://laptop/...` (and other URIs executed by the twin) are written to `.planfile/.koru/queue.log` so they are visible in the dashboard "Na żywo — koru (realne komendy URI)" panel.

## Configuration (LLM from urirun/.env)

The system uses a **triple LLM setup** for safe real-world automation (especially KVM/GUI tasks on remote nodes like lenovo):

```env
OPENROUTER_API_KEY=sk-or-...

# Executor — fast decisions during live automation (observe-act loops, clicks, typing)
LLM_MODEL_EXECUTOR=openrouter/google/gemini-3.5-flash

# Validator — checks that the executor truly understands the task + risks BEFORE any real actions
LLM_MODEL_VALIDATOR=openrouter/qwen/qwen3.7-plus

# Teacher — specialized in analyzing graphics/screenshots (low-res captures, quad zooms)
# Better than Gemini at visual UI understanding, screen reading, GUI state verification.
LLM_MODEL_TEACHER=openrouter/qwen/qwen3.7-plus

# Executor Twin — drugi blizniak executora. System porównuje obu (czas + skuteczność)
# i wybiera lepszy do rzeczywistego wykonania akcji.
LLM_MODEL_EXECUTOR_TWIN=openrouter/minimax/minimax-m3
```

**Recommended OpenRouter models for TEACHER** (strong vision/graphics analysis):
- `openrouter/qwen/qwen3.7-plus` — excellent at screenshot perception, GUI grounding, UI element localization, vision-to-action (currently recommended).
- Alternatives with strong vision: `openrouter/minimax/minimax-m3` (good multimodal + video), or higher-tier vision models available on OpenRouter.

The system uses `litellm`. Any `openrouter/...` model works.

### The three complementary LLM roles

| Role | Variable | Main strength | Typical OpenRouter choice | Used for |
|------|----------|---------------|---------------------------|----------|
| **Executor** | `LLM_MODEL_EXECUTOR` | Speed + basic vision for live control loops | `openrouter/google/gemini-3.5-flash` | Real-time decisions (click, type, zoom requests) during KVM |
| **Validator** | `LLM_MODEL_VALIDATOR` | Rigorous reasoning & critique | `openrouter/qwen/qwen3.7-plus` or `deepseek/deepseek-v4-pro` | Pre-execution knowledge quiz. Must PASS before any real action |
| **Teacher**       | `LLM_MODEL_TEACHER`       | **Superior graphics / image analysis** (screenshots, UI state)                          | `openrouter/qwen/qwen3.7-plus` (recommended) or `minimax/minimax-m3` | Deep visual analysis of low-res captures + quad zooms. Helps Executor & Validator understand what is actually on screen |
| **Executor Twin** | `LLM_MODEL_EXECUTOR_TWIN` | Second "blizniak" executor. During preparation the system runs both on the same visual task, measures time + quality (via Validator), and automatically selects the better one for real KVM actions. | `openrouter/minimax/minimax-m3` | A/B testing between two executors. Chooses the faster and more effective based on response time and success of the defensive probe + verification. |

**Important:** The triple setup (Executor + Validator + Teacher) is mandatory for high-risk desktop automation. It is enforced in `prepare_and_validate_for_signal_kvm` (urirun-connector-work) and similar entry points. Real `kvm://` commands are blocked until the Validator approves understanding **and** the Teacher has contributed visual analysis of the UI state.

This directly addresses the requirement that "przed wykonaniem zadania LLM musi wiedzieć z czym ma do czynienia" (the model must demonstrate knowledge of the system and task before acting).

## Digital Twin integration

Twins load persons from:

`~/.urirun/host-dashboard/digital-persons.json` (or `URIRUN_DIGITAL_PERSONS`)

They inherit:
- `competencies`
- `grants` (used when recording unblocks)
- `type` (human vs digital)

Example persons already include `kvm`, `unblock`, `signal`, `node:lenovo` competencies.

## Installation (dev)

```bash
cd urirun-twin-human
pip install -e .
# or in the main if-uri venv
pip install -e /path/to/urirun-twin-human
```

The connector registers as `twin-human` (scheme `human`).

## How it helps autonomy (kolejno context)

Previously tickets like IFURI-226 (`wyślij wiadomość do mateusza na signal na lenovo`) were stuck on `actor:human` + manual handoff or fragile chat-drive.

The triple-LLM system adds **mandatory pre-execution safety**:
- Before any real `kvm://laptop/...` (especially Signal Desktop on lenovo), the Executor must produce a detailed plan + visual awareness report.
- The Validator (different model) quizzes it and issues PASS/FAIL.
- The Teacher (graphics-specialized model) analyzes low-res captures / quad zooms and provides visual understanding.
- Only on successful validation the real actions are allowed. This prevents "runtime lies" and wrong-field typing.

### Automatic integration (2026-07)

- koru loop (`urirun-connector-loop`) now detects `kvm` / `lenovo` / `signal-gui` labels (or "na lenovo" in text) and routes to `execute-via-twin-human`.
- `urirun start` launches the autonomous koru cycle with twin-human support.
- Real `kvm://laptop/...` commands (type, key, task/run) are executed via twin + `deliver_signal` (signal-gui-kvm channel) and logged to `.planfile/.koru/queue.log`.
- They appear in the dashboard panel **"Na żywo — koru (realne komendy URI)"**.

Usage:

```bash
urirun start                    # start autonomy (uses twin for kvm tasks)
urirun start --project . --apply
make -f app/Makefile koru-cycle # convenience target
```

With `urirun-twin-human`:
1. Grant the type (`kvm:lenovo`, `signal-gui`, `unblock:*`) via unblock_ledger or grants.
2. koru/work/loop will automatically claim + delegate via twin-human (no more chat-drive for desktop tasks).
3. Twin performs: `act_as_human`, `click_as`, direct `kvm://laptop/input/...` or `task/command/run`.
4. Status changes are recorded with rich history (`reason` + `actor: "twin-human:tom"`).

This turns "human required" steps into fully delegable autonomous twin actions that also produce visible real URI logs.

## `urirun start`

```bash
urirun start                    # launches koru loop with twin-human delegation for kvm/lenovo
urirun start --daemon           # background
urirun start --koru             # also ensure koru daemon
```

This is the recommended way to start the autonomy after the 2026-07 integration. The loop will prefer `twin-human` for any ticket that touches `kvm://laptop` (or equivalent lenovo desktop control) instead of trying to drive via IDE chat.

## Makefile helpers

```bash
make -f app/Makefile koru-cycle          # koru-cycle with apply (twin + logs)
make -f app/Makefile koru-plan           # dry run plan
make -f app/Makefile koru-execute-twin   # direct twin call for a ticket
make -f app/Makefile koru-logs           # tail the live koru log
```

## Related

- `urirun-connector-twin`
- `urirun-connector-human-twin`
- `urirun-connector-grants` (unblock_ledger)
- `urirun-connector-kvm`
- `urirun-connector-work/goal.py` (signal-gui-kvm channel)
- `urirun-connector-loop` (now emits `execute-via-twin-human`)
- Digital persons + work queue grants

See also the updated IFURI-226 operator handoff for a concrete use of this twin.
