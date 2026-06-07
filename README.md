# V-CORE

**VR Cognitive-state Observation, Rules & Environment adaptation** — a research platform for
real-time VR cognitive-state monitoring and adaptation.

V-CORE is the **middleware** between a physiological-sensing pipeline ("Om") and a swappable
Unity runtime ("Jerry"). It provides a **schema-driven dashboard** that renders whatever
signal channels the pipeline declares (and lets you **author rules from the browser**, and —
during a study session — shows a **live mirror of the participant's VR view** beside the
signals), and a **rule engine** that evaluates declarative rules against live signals and
emits **object-status change requests** to the VR environment.

The system is **plug-and-play along three axes** — indicators, rules, and VR environments —
with no core-code changes required to exercise any of them. That modularity is enforced by
three versioned contracts:

| # | Contract | Between | Carries |
|---|----------|---------|---------|
| 1 | **Signal Schema** | Pipeline → Dashboard/Engine | self-describing channels (name · unit · type · range · display hint) |
| 2 | **Rule Grammar** | Rule files ↔ Engine/UI | declarative `IF (signal) → THEN (set object status)`; authored in the UI or dropped in as files |
| 3 | **Object-Status & Status-Request** | Engine ↔ VR Runtime | runtime declares each object's settable statuses (over WebSocket); engine sends `{target, status, value}` matched against them |

## Status

🟡 **Design phase** (reflecting Amendment 1: frontend rule authoring + Unity object-status
context; Amendment 2: participant video mirror + recording + manual rule trigger). The
architecture and implementation plan are complete and approved; no application code has been
written yet. Implementation proceeds **one phase at a time** through [`TODO.md`](./TODO.md),
pausing for review between phases.

## Documents

- **[`ARCHITECTURE.md`](./ARCHITECTURE.md)** — single source of truth for the design: tech
  stack, patterns, the three contract specs, folder layout, data-flow walkthroughs, failure
  modes, deployment.
- **[`TODO.md`](./TODO.md)** — sequenced, atomic implementation checklist (contracts and
  validators first).
- **[`contracts/`](./contracts)** — language-neutral JSON Schemas for the three contracts
  *(created in Phase 1)*.

## Tech stack (summary)

Python 3.11 · FastAPI · pylsl · pydantic — backend (LSL ingestion, rule engine, WebSocket
bridge to the dashboard and the Unity runtime, plus WebRTC signaling). React · TypeScript ·
Vite — schema-driven browser dashboard with a rule builder and a live participant video feed.
A thin Unity reference POC (`unity-poc/`). Participant video over **WebRTC** (peer-to-peer;
V-CORE brokers signaling only). Contracts as JSON Schema, validated on both sides.
See [`ARCHITECTURE.md §3`](./ARCHITECTURE.md#3-tech-stack--rationale).
