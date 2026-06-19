# V-CORE — Implementation Checklist

Sequential, atomic implementation plan. See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the
design this realises. *(Reflects Amendment 1: frontend rule authoring + Unity object-status
context + WebSocket transport + a thin Unity POC; Amendment 2: participant video mirror via
WebRTC, recording synced to signals, and a manual rule trigger.)*

**How to use this list**
- Each item is a single, independently-verifiable unit of work (a few hours max).
- Items name the file(s) they touch and an **AC** (acceptance criterion).
- **Phases are ordered so the contracts and their validators exist and pass before any
  feature that depends on them.** Do not start a phase before the previous one is green.
- **Process gate:** implementation proceeds **one phase at a time, pausing for review
  between phases**. Mark items `- [x]` as completed.

**Legend:** ⛔ stable core · 🔌 extension point · ⭐ single source of truth · 🌐 network/config · 🆕 Amendment 1 · 🎥 Amendment 2 (participant video)

---

## Phase 0 — Scaffolding & tooling

- [ ] **Repo skeleton** — create `backend/`, `frontend/`, `contracts/` (+ `examples/`),
  `tools/`, `unity-poc/`, `docs/`, and `data/` (gitignored). *AC:* tree matches
  [ARCHITECTURE §7](./ARCHITECTURE.md#7-file--folder-structure).
- [ ] **`.gitignore`** — Python (`venv`, `__pycache__`, `*.egg-info`), Node (`node_modules`,
  `dist`), Unity (`Library/`, `Temp/`, `obj/`), recordings (`data/`, `*.xdf`, `*.db`), local
  config (`config.yaml`). *AC:* no build artefacts or local config tracked.
- [ ] **`backend/pyproject.toml`** — deps: `fastapi`, `uvicorn`, `pylsl`, `pydantic`,
  `jsonschema`, `pyyaml`, `watchdog`, `pyxdf`, `websockets`; dev: `pytest`, `ruff`, `mypy`.
  *(No `pyzmq` unless/until the ZMQ alternative is built.)* *AC:* `pip install -e ".[dev]"`
  succeeds in a clean venv.
- [ ] **`backend/config.example.yaml`** 🌐 — ingestion (LSL stream names, stale_timeout),
  outbound (`transport: ws`, `runtime_ws_path`), bridge (WS bind, auth), recording paths, per
  [ARCHITECTURE §10](./ARCHITECTURE.md#10-deployment--configuration). *AC:* a config loader
  stub parses it without error.
- [ ] **Frontend app** — Vite React-TS; add `ajv`, `zustand`, chart lib; dev: `vitest`,
  `@testing-library/react`. *AC:* `npm run dev` serves a blank app; `npm run build` passes.
- [ ] **Lint/format** — `ruff` + `mypy` (backend); ESLint + Prettier (frontend). *AC:*
  `ruff check`, `mypy`, `npm run lint` pass on the empty scaffold.
- [ ] **`docker-compose.yml`** — backend + frontend dev services. *AC:* `docker compose
  config` validates.
- [ ] **CI workflow** (`.github/workflows/ci.yml`) — jobs: backend, frontend, contracts.
  *AC:* workflow file is valid; jobs are defined.

## Phase 1 — Contracts & validators ⭐ (GATE for everything downstream)

- [ ] **`contracts/signal_schema.schema.json`** — Contract 1, JSON Schema 2020-12. *AC:*
  validates against the draft 2020-12 metaschema.
- [ ] 🆕 **`contracts/rule_grammar.schema.json`** — Contract 2 with `then.set
  {target(tag|id), status, value}` + `cooldown_s`, **plus the `$defs/abstract_action`
  skeleton and `$comment`s** marking the future branch. *AC:* metaschema-valid; the example
  `then.set` rule validates and a `then.action` rule does **not** (skeleton not wired in).
- [ ] 🆕 **`contracts/status_request.schema.json`** — Contract 3a `{schema_version,
  intent_id, timestamp, target(tag|id), status, value, source_rule, source(engine|manual)}`.
  *AC:* metaschema-valid (`source` distinguishes engine-fired vs researcher-triggered).
- [ ] 🆕 **`contracts/object_status_manifest.schema.json`** — Contract 3b `objects:[{id,
  tags[], statuses:[{name,type,values|range}]}]` + `abstract_actions:[]` skeleton; discrete
  requires `values`, continuous requires `range`. *AC:* metaschema-valid; conditional
  requirements enforced.
- [ ] **`contracts/VERSIONING.md`** — SemVer policy + skew matrix per
  [ARCHITECTURE §6](./ARCHITECTURE.md#6-versioning--compatibility-policy). *AC:* documents
  patch/minor/major handling.
- [ ] 🆕 **`contracts/examples/`** — for each of the 4 contracts, ≥1 **valid** + ≥1
  **invalid** golden (e.g. discrete status missing `values`; status value out of range;
  rule using the unsupported `then.action`). *AC:* each invalid file is wrong in exactly one
  documented field.
- [ ] **Python validator** (`backend/vcore/core/schema.py` + `models.py`) — load + validate
  via `jsonschema`; pydantic models mirror the contracts. *AC:* `pytest` — all valid goldens
  pass, all invalid fail.
- [ ] **TS type-gen + validator** (`tools/gen-types.*` → `frontend/src/contracts/*.ts`; ajv)
  — generate types, validate with `ajv`. *AC:* `vitest` — same goldens pass/fail on TS side.
- [ ] **Cross-language contract test in CI** — both validators on the shared goldens. *AC:*
  the `contracts` CI job is green.

> **Do not proceed past Phase 1 until both validators agree on every golden payload.**

## Phase 2 — Core & event bus ⛔

- [ ] **`core/eventbus.py`** — async pub/sub, typed topics (`manifest.updated`, `sample`,
  `object_status.updated`, `rule.fired`, `warning`, `link.status`). *AC:* publish reaches
  multiple subscribers in order.
- [ ] **`core/schema.py` — active-manifest registry + version-skew check** — hold the active
  Signal Schema / Object-Status Manifest; SemVer compare → `ok | warn | refuse`. *AC:* tests
  for patch/minor (warn) vs major (refuse).
- [ ] **`core/models.py`** — pydantic models for SignalManifest, Rule, StatusRequest,
  ObjectStatusManifest. *AC:* round-trips every valid golden.

## Phase 3 — Ingestion adapters 🔌

- [ ] **`ingestion/base.py`** — `SignalSource` ABC. *AC:* documented; `mypy` clean.
- [ ] **`ingestion/replay_source.py`** (test-first, no hardware) — replay an XDF/CSV fixture +
  sidecar manifest at rate. *AC:* test replays a fixture; bus receives manifest then N samples.
- [ ] **`ingestion/lsl_source.py`** — `pylsl` resolve by name, read manifest from LSL header /
  sidecar, stream samples. *AC:* integration test against a local pylsl stream resolves + reads.
- [ ] **Stale-signal detection** — emit `stale` when no samples within `stale_timeout_s`.
  *AC:* test: silence for the timeout → a stale event.

## Phase 4 — Rule engine

- [ ] **`engine/registry.py` — load** — read all rule files (YAML + JSON), validate each
  against the Rule Grammar, capture per-file errors. *AC:* valid rules load; one malformed
  file is skipped with an error; others unaffected.
- [ ] **`engine/registry.py` — hot-reload** (`watchdog`) — add/modify/delete updates the
  registry. *AC:* dropping a file registers a rule; deleting removes it — no restart.
- [ ] **`engine/evaluator.py`** — condition eval (all ops incl. `between` + categorical
  `==`/`!=`), `all`/`any`, `sustain_s` windowing, `cooldown_s` refractory. *AC:* per-op tests;
  sustain fires only after a continuous hold; cooldown suppresses re-fire.
- [ ] 🆕 **`engine/degradation.py`** — reconcile rules against the active Signal Schema **and**
  the active Object-Status Manifest: a rule's `then.set.target`(tag|id)+`status`+`value` must
  resolve to a real object/status with a valid value; else disable + annotate. *AC:*
  missing-signal → disabled+reason; unresolved target/out-of-range value → disabled+reason; no
  exception.
- [ ] 🆕 **Engine emits status requests** — on fire, publish a schema-valid **StatusRequest**
  (`target`, `status`, `value`, `intent_id`, `source_rule`) on the bus. *AC:* a met condition
  yields a request that passes `status_request.schema.json`.

## Phase 5 — Outbound & object-status negotiation 🔌

- [ ] **`outbound/base.py`** — `ActionSink` ABC (connect → receive Object-Status Manifest →
  send StatusRequest → report link status). *AC:* documented; `mypy` clean.
- [ ] 🆕 **`outbound/ws_sink.py`** (primary) — accept the Unity WS client on `/ws/runtime`,
  receive + validate the Object-Status Manifest, publish it on the bus, send StatusRequests
  down the same socket. *AC:* integration test against `tools/mock_unity.py`: handshake
  received, request delivered.
- [ ] 🆕 **Target matching at send time** — resolve `target`(tag|id)+`status` against the
  active manifest, validate `value` (range/values); **drop + warn** on no match. *AC:*
  resolved target is sent; unresolved/out-of-range is dropped with a `warning` (no crash).
- [ ] **`outbound/zmq_sink.py`** — ZMQ alternative behind the same ABC, **left as a documented
  stub** (commented; not wired by default). *AC:* file documents how to enable; `transport: ws`
  remains default.
- [ ] **Link status + reconnect/backoff** for the runtime WS link. *AC:* simulated disconnect
  flips status + triggers backoff reconnect without crashing the engine.

## Phase 6 — WebSocket bridge, schema-driven dashboard & rule authoring

- [ ] 🆕 **`bridge/ws.py`** — FastAPI WS with **two paths**: `/ws/dashboard` (push manifest,
  object-status manifest, samples, warnings, link statuses) and `/ws/runtime` (the Unity
  link, delegated to `ws_sink`); optional bearer-token; bind from config. *AC:* a dashboard
  test client receives a Signal Schema, an Object-Status Manifest, and sample frames.
- [ ] **Frontend WS client + store** — reconnect; Zustand holds Signal Schema, Object-Status
  Manifest, samples, warnings, link statuses. *AC:* store updates on incoming messages;
  recovers on a dropped socket.
- [ ] **`renderers/registry.ts` + `FallbackRenderer.tsx`** ⭐ — map `type`/`display.hint` →
  component; unknown → fallback. *AC:* known hint → correct component; unknown → fallback.
- [ ] **Renderers** — `StatCard`, `LineChart`, `Quadrant`. *AC:* each renders from sample props.
- [ ] **Session Monitor screen** — render every channel from the manifest via the registry;
  show link statuses + warnings. *AC:* a 3-channel manifest renders 3 widgets; a 4th
  unknown-hint channel renders the fallback — **no code change**.
- [ ] 🆕 **`api/rules.py`** — `POST/PUT/DELETE /api/rules` → validate against the Rule Grammar
  → write/update/remove a YAML/JSON file in `backend/rules/`. *AC:* posting a valid rule
  writes a file that the registry hot-loads; an invalid rule returns a validation error and
  writes nothing.
- [ ] 🆕 **Rule Builder** (`frontend/src/screens/RuleManager/`) — IF side populated from the
  Signal Schema, THEN side from the Object-Status Manifest (pick tag/id → status →
  value-with-bounds); save calls `/api/rules`. *AC:* building & saving a rule produces a file,
  it appears enabled in the rule list, and bad inputs are blocked client-side and server-side.
- [ ] 🎥 **Manual rule trigger** — a Session Monitor "Activate" button → `POST
  /api/rules/{id}/trigger` → engine emits the rule's status request immediately with
  `source: manual`. *AC:* clicking Activate fires the request once, logs a
  researcher-attributed event, and still respects target reconciliation (unresolved → warning,
  nothing sent).
- [ ] **Remaining screens** scaffolded — New Session, Data History, System Config (endpoints +
  per-link status). *AC:* navigable; Rule Manager lists disabled rules with reasons.

## Phase 6.5 — Unity reference POC 🆕

- [ ] **`unity-poc/` project + `Sample.unity`** — empty scene with a single light object.
  *AC:* the scene opens and plays in Unity.
- [ ] **`ObjectStatus.cs`** — component declaring discrete (`values`) or continuous (`range`)
  statuses, with tags/id, editable in the Inspector. *AC:* a light has a `brightness`
  continuous `0–100` status set in the Editor.
- [ ] **`StatusCollector.cs`** — on `Start`, `FindObjectsOfType<ObjectStatus>()` → build the
  Object-Status Manifest (matches `object_status_manifest.schema.json`). *AC:* the emitted
  JSON validates against the contract.
- [ ] **`VCoreConnection.cs`** — WS client: connect to V-CORE, send the manifest, receive
  StatusRequests. *AC:* connects to a running backend and the manifest appears in V-CORE.
- [ ] **`RequestDispatcher.cs` / `OnRequest()`** — apply an incoming `{target, status, value}`
  to matching objects (by tag/id). *AC:* a status request changes the light's brightness in
  the running scene.
- [ ] 🎥 **`SpectatorCamera.cs`** — a mono camera mirroring the participant's view. *AC:* it
  renders the scene at the configured resolution.

> **As-built:** the two video scripts below were superseded by **`LiveKitPublisher.cs`** (publishes
> the spectator camera to a LiveKit SFU; recording is server-side via LiveKit Egress).
> `WebRtcSender.cs` and `VideoRecorder.cs` have been removed — see `docs/LIVEKIT_SETUP.md`.

- [ ] 🎥 **`WebRtcSender.cs`** (`com.unity.webrtc`) — connect to V-CORE signaling, negotiate,
  and send the spectator-cam video to the dashboard. *AC:* the participant view appears in the
  dashboard VideoFeed within ~150 ms on the LAN.
- [ ] 🎥 **`VideoRecorder.cs`** — record the spectator cam to a session file stamped with the
  session's LSL start time; upload to V-CORE on session end. *AC:* the file plays back and
  carries the start marker. *(A browser-side MediaRecorder is an acceptable POC stand-in.)*
- [ ] **Clean, separable scripts (package-ready)** — no monolith; ready to promote to a UPM
  package later. *AC:* each script is independently reusable; a short `unity-poc/README.md`
  explains drop-in usage.

## Phase 7 — Recording (Data History)

- [ ] **`recording/xdf_writer.py`** — raw streams → XDF per session (+ clock offsets). *AC:*
  a session produces an XDF that `pyxdf` loads with the expected streams.
- [ ] 🆕 **`recording/sqlite_store.py`** — `sessions` + `events` tables (rule fires, status
  requests, warnings). *AC:* a session + its events persist and are queryable.
- [ ] **Data History screen** — list sessions; event timeline; link to the XDF. *AC:* recorded
  sessions are listed; opening one shows its events.

## Phase 7.5 — Participant video mirror (WebRTC) + recording 🎥

> **As-built:** implemented, then **reimplemented on a LiveKit SFU** (Unity publishes → browser
> subscribes → server-side Track Egress recording, LSL-anchored). The `bridge/signaling.py`
> broker, `frontend/src/video` `RTCPeerConnection`/`MediaRecorder`, and the browser-upload
> endpoints below are **superseded and removed.** See `docs/HOW_IT_WORKS.md` §9 and
> `docs/LIVEKIT_SETUP.md`.

- [ ] **`bridge/signaling.py`** — WebRTC signaling broker: relay SDP offer/answer + ICE
  candidates between the Unity peer and the dashboard peer over `/ws/signaling`. **V-CORE
  relays no media.** *AC:* two test peers complete a handshake through the broker.
- [ ] **`frontend/src/video/` + VideoFeed** — `RTCPeerConnection` client; render the incoming
  stream in a `<video>` in Session Monitor beside the charts. *AC:* against a test-pattern
  peer the video renders and recovers after a forced ICE restart.
- [ ] **Session lifecycle wiring** — New Session start begins signaling + recording; End
  Session tears down the stream and finalises the recording. *AC:* start shows the feed; stop
  cleanly ends both.
- [ ] **`recording/video_store.py`** — receive/register the session video, store it in the
  session folder, link it to the SQLite session row. *AC:* after a session the video is listed
  and openable from Data History.
- [ ] **LSL-clock sync** — stamp the video start against the session's LSL time so it aligns
  with the XDF signals. *AC:* a replayed session shows video and signal traces aligned within
  one frame.
- [ ] **MJPEG-over-WS fallback** (optional, `video.transport: mjpeg`). *AC:* with WebRTC
  disabled, a low-FPS preview still renders in the VideoFeed.

## Phase 8 — Graceful-degradation hardening

- [ ] **Failure-mode test matrix** — one test per row of
  [ARCHITECTURE §9](./ARCHITECTURE.md#9-failure-modes--graceful-degradation): absent signal,
  unresolved target / out-of-range value, unknown hint, malformed rule / rejected API, invalid
  payload, stale signal. *AC:* each asserts disable-and-warn (or fallback), **never** an
  unhandled exception.
- [ ] **Schema version-skew end-to-end** — minor-bumped manifest (warn + continue) and a
  major-bumped one (refuse + blocking warning). *AC:* matches `contracts/VERSIONING.md`.
- [ ] 🆕 **Per-link independent reconnect + UI status** for all 3 links (Sensor-Pipeline-**LSL**,
  Unity-**WS**, browser-**WS**). *AC:* dropping each in turn — engine + UI survive; statuses
  reflect reality.
- [ ] 🎥 **Video-plane isolation** — drop/fail the WebRTC connection mid-session. *AC:* the
  VideoFeed shows "reconnecting" and renegotiates; the session, recording, signals, and rule
  engine are unaffected.

## Phase 9 — Dev ergonomics, reproducibility & docs

- [ ] **`tools/mock_pipeline.py`** — emit a configurable Signal Schema + synthetic signals over
  LSL. *AC:* V-CORE ingests it end-to-end with no hardware.
- [ ] 🆕 **`tools/mock_unity.py`** — headless **WS** client advertising an Object-Status
  Manifest + logging received StatusRequests (same protocol as `unity-poc/`); optionally emits
  a WebRTC **test-pattern** stream so the VideoFeed can be exercised without Unity. *AC:* a
  rule fire shows in the mock; an unresolved target is dropped + warned.
- [ ] **End-to-end smoke test** — mock_pipeline → V-CORE → rule fires → mock_unity receives a
  resolved request → recorded to XDF + SQLite. *AC:* a single test/script proves the chain
  (loopback or cross-host).
- [ ] **Docs sync** — reconcile `ARCHITECTURE.md` + this file with what shipped; finalise
  `README.md` run instructions. *AC:* docs match the code; completed boxes ticked.

---

### Definition of done (v1)

A channel added in the sensor pipeline appears on the dashboard *and* as a Rule-Builder IF with no V-CORE
change; a developer drops `ObjectStatus` onto a Unity object and it appears as a Rule-Builder
THEN; a rule authored in the browser is saved as a file, hot-loads, fires, and changes the
object over WebSocket; during a session the researcher watches the participant's VR view live
and can manually trigger a rule, and the recorded video aligns to the signals; swapping to a
scene without the target degrades to a warning; raw sessions record to XDF and replay; and
every failure-mode row has a passing test. All four contracts validate identically on the
Python and TypeScript sides.
