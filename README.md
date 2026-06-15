# V-CORE

**VR Cognitive-state Observation, Rules & Environment adaptation** — a research platform for
real-time VR cognitive-state monitoring and adaptation.

V-CORE is the **middleware** between a physiological-sensing pipeline and a swappable
Unity runtime ("Jerry"). It provides a **schema-driven dashboard** that renders whatever
signal channels the pipeline declares (and lets you **author rules from the browser**, and —
during a study session — shows a **live mirror of the participant's VR view** beside the
signals), and a **rule engine** that evaluates declarative rules against live signals and
emits **object-status change requests** to the VR environment.

The system is **plug-and-play along three axes** — indicators, rules, and VR environments —
with no core-code changes required to exercise any of them. That modularity is enforced by
three versioned contracts:

| #   | Contract                           | Between                     | Carries                                                                                                                        |
| --- | ---------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1   | **Signal Schema**                  | Pipeline → Dashboard/Engine | self-describing channels (name · unit · type · range · display hint)                                                           |
| 2   | **Rule Grammar**                   | Rule files ↔ Engine/UI      | declarative `IF (signal) → THEN (set object status)`; authored in the UI or dropped in as files                                |
| 3   | **Object-Status & Status-Request** | Engine ↔ VR Runtime         | runtime declares each object's settable statuses (over WebSocket); engine sends `{target, status, value}` matched against them |

## Status

🟢 **Implemented** — all nine phases complete. The system runs end-to-end: signal ingestion,
rule evaluation, Unity WebSocket delivery, session recording (XDF + SQLite), schema-driven
dashboard, rule builder, and participant video mirror over WebRTC. See [`TODO.md`](./TODO.md)
for a full phase-by-phase checklist.

## Quick start

### Prerequisites

- Python 3.11+ and Node 20+
- `pip install -e ".[dev]"` inside `backend/`
- `npm install` inside `frontend/`

### 1. Backend

```bash
cd backend
uvicorn vcore.app:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm run dev          # serves on http://localhost:5173 (proxies API to :8000)
```

### 3. Mock signal pipeline (no hardware required)

```bash
# streams synthetic signals over LSL at 10 Hz
python tools/mock_pipeline.py

# optional flags
python tools/mock_pipeline.py --pattern high --rate 5   # constant-high values, 5 Hz
python tools/mock_pipeline.py --manifest path/to/my.manifest.json
```

### 4. Mock Unity client (no Unity required)

```bash
# connects to WsSink, sends Object-Status Manifest, prints incoming StatusRequests
python tools/mock_unity.py --port 9001
```

### Running tests

```bash
cd backend
pytest               # 165+ tests, ~14 s, no hardware needed

cd frontend
npm test             # vitest unit tests
npm run lint         # ESLint + type check
```

### Config

Copy `backend/config.example.yaml` → `backend/config.yaml` and adjust LSL stream names,
WsSink bind address, and (optional) auth token for multi-machine deployments.

## Documents

- **[`ARCHITECTURE.md`](./ARCHITECTURE.md)** — single source of truth for the design: tech
  stack, patterns, the three contract specs, folder layout, data-flow walkthroughs, failure
  modes, deployment.
- **[`TODO.md`](./TODO.md)** — sequenced, atomic implementation checklist (contracts and
  validators first).
- **[`contracts/`](./contracts)** — language-neutral JSON Schemas for the three contracts
  _(created in Phase 1)_.

## Tech stack (summary)

Python 3.11 · FastAPI · pylsl · pydantic — backend (LSL ingestion, rule engine, WebSocket
bridge to the dashboard and the Unity runtime, plus WebRTC signaling). React · TypeScript ·
Vite — schema-driven browser dashboard with a rule builder and a live participant video feed.
A thin Unity reference POC (`unity-poc/`). Participant video over **WebRTC** (peer-to-peer;
V-CORE brokers signaling only). Contracts as JSON Schema, validated on both sides.
See [`ARCHITECTURE.md §3`](./ARCHITECTURE.md#3-tech-stack--rationale).

Backend (from backend/ directory):

uv run uvicorn vcore.app:app --reload --host 0.0.0.0 --port 8000
Frontend (from frontend/ directory):

npm run dev

uv run python tools/mock_unity.py

uv run python tools/mock_pipeline.py
