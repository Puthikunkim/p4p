# Changelog

All notable changes to V-CORE are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project does not yet publish tagged releases, so history is grouped into
**dated development milestones** (newest first). New work accrues under
`[Unreleased]` until it is cut into a dated milestone.

> **Maintainers:** when you make a notable change (feature, fix, removal, or
> behaviour change), add a bullet to `[Unreleased]` under the right category
> (`Added` / `Changed` / `Fixed` / `Removed`). Skip trivial or internal-only
> edits. Periodically roll the accumulated entries into a new dated milestone.

## [Unreleased]

### Added
- `LevelBar` renderer (`level_bar` hint): a segmented ordinal meter for ranked categoricals (Low < Medium < High) that fills up to the current level along a teal→amber→red severity ramp. Cognitive load now renders through it instead of the 2×2 `quadrant` grid.

### Changed
- Re-vendored the sensor-pipeline manifests to the pipeline team's confirmed source of truth: `emotion` now carries the real valence/arousal quadrant labels (`Positive / High arousal`, …) instead of placeholder indices; `cognitive_load` uses the `level_bar` hint; `eda_scr_peaks` gets `precision: 0` (renders as an integer count) and the physiological time-series channels declare `window_s: 30`.
- Rewrote the two affect rules to target the real `emotion` channel: `clear-fog-stressed` on `Negative / High arousal`, `increase-fog-bored` on `Negative / Low arousal` (previously keyed on a non-existent `affect` signal, so they never fired).

## [2026-06-28 – 06-29] — Documentation restructure & dead-code cleanup

Reworked the docs to onboard newcomers and stripped superseded scaffolding now
that LiveKit and the abstract-action contract are the settled design.

### Changed
- Corrected the as-built docs (LiveKit, `.webm`, ports, Unity package paths) and restructured them to read top-to-bottom for newcomers.
- Slimmed `ARCHITECTURE.md` to a design reference, deferring operational detail to `HOW_IT_WORKS.md`.
- Rewrote the `com.vcore.client` README as a comprehensive beginner setup/usage guide; surfaced package import/usage from the main docs; slimmed the `unity-poc` README to an implementation map + run steps.
- Added a **`V-CORE > Add to Scene`** Unity setup wizard and split the client/POC READMEs by role.
- Clarified the Unity action contract, the status/action distinction, per-object metric declaration, `ObjectStatus` value handling, action targeting, and scene/session scope.
- `mock_unity` now connects over `/ws/runtime` directly.

### Fixed
- Rule builder: dedupe shared statuses in the tag target picker.
- Rule builder: allow targeting object-scoped actions by tag.

### Removed
- Standalone `WsSink` server + `ActionSink` seam (the runtime is served over `/ws/runtime`).
- Test-only `ReplaySource` + `SignalSource` ABC, and the `HOW_IT_WORKS` as-built-notes section.
- Five unused shadcn UI components (card, scroll-area, separator, switch, tabs).
- Custom-WebRTC / signaling migration leftovers (dead code, stale docs, `TODO.md`).
- The `Jerry` codename and the `jerry-unity` runtime identifier; POC-internal references in the package README.

## [2026-06-26 – 06-27] — Session deletion, Windows/Docker fixes, dark-lime UI

### Added
- Delete recorded sessions from Data History (DB row, events, XDF + video files).
- Dark-lime theme with per-signal chart colours and restyled rule cards.
- Theme-aware charts and a shadcn component sweep across every screen; new components config + theme handling.
- `pnpm-lock.yaml` with updated dependencies.

### Changed
- Stop orphaned egresses on session start to prevent pile-up.
- Session stop returns immediately and finalises the egress in the background.
- Distinct orange/lime trigger-vs-action rule chips; clearer section separators, metric titles, and tagged log/warning entries on the Session Monitor.

### Fixed
- Show the full recorded signals when the video timeline is truncated.
- Render all connectivity links on every screen.
- Bind LiveKit media to a single UDP port for Windows.
- Visible link-button text (Download Report) and pointer cursor on shadcn buttons.
- Make the tailwind + shadcn branch build (tsconfig `baseUrl`, eslint `react-refresh`, lockfile).

### Performance
- Memoized signal-chart geometry for smooth seeking.

## [2026-06-21] — Abstract actions (Contract 3c) & rule-authoring catalog

Introduced fire-and-forget **actions** alongside object statuses, and a
project-wide catalog so rules can be authored against real runtime capabilities.

### Added
- **Contract 3c (`action_request`)** — abstract-action contract plus rule-engine support for `then.action`.
- Unity `VCoreAction` component with dispatcher/collector action support.
- Author and render rule actions in the UI; `action_fired` events.
- Project-wide `ObjectStatus` / `VCoreAction` catalog for rule authoring, auto-baked on build (`IPreprocessBuildWithReport`).

### Fixed
- Typed the LiveKit client as `Any` to satisfy mypy `no-untyped-call`.

### Removed
- ZMQ transport stub and the dead `replay_fixture` config (ARCHITECTURE.md synced).

## [2026-06-19 – 06-20] — LiveKit video migration & `com.vcore.client` package

Replaced the hand-rolled WebRTC video plane with a **LiveKit** SFU + server-side
**Egress** recording, and extracted the reusable Unity client into a UPM package.

### Added
- LiveKit SFU + Egress + Redis services in `docker-compose`.
- Backend LiveKit token endpoint + Egress recording orchestration (gated, LSL-anchored).
- Frontend subscribes to LiveKit for the live mirror (replacing custom WebRTC + browser recording).
- Unity LiveKit publisher + SDK manifest entry, wired into the Sample scene.
- Backend (Python + liblsl) and frontend (Vite) Dockerfiles; `tools/` mounted into the backend container.
- `GET /api/sessions/{id}/signals` — reads the recorded XDF for post-session review.
- Video-synced signal cursor + event-log highlighting in Data History.
- Two-point video/signal drift correction (anchored at Egress start).
- **`com.vcore.client` UPM package** extracted from the POC, with a `VCoreLauncher` one-component bootstrap and a `VCore` prefab.

### Changed
- LiveKit Egress start is best-effort — it never aborts a session.
- Dockerized frontend proxies to the backend service.
- Record via Track Egress (Room Composite failed in Docker; avoids headless Chrome).

### Fixed
- Correct LiveKit SDK package name; match `LiveKitPublisher` to the installed SDK API; disambiguate `RoomOptions`.
- Resolve LSL streams over loopback unicast in Docker (`KnownPeers`).
- `lsl_api.cfg` must be comment-free (liblsl has no `#` comments).

### Removed
- Dead `VideoRecorder` (unwired; posted to a missing endpoint).
- **Legacy custom-WebRTC signaling path** (`WebRtcSender`, `SignalingBroker`, browser-upload endpoints) — superseded by LiveKit.

## [2026-06-15 – 06-16] — Clinical redesign, sensor-pipeline rebrand, config wiring

### Added
- Clinical-precision design-system redesign of the dashboard.
- Shared Unity `BackendConfig` asset; namespaced Unity scripts.
- MCP for Unity package + required built-in modules.
- As-built `HOW_IT_WORKS.md` end-to-end walkthrough.

### Changed
- **Rebranded `Om` / `om-lsl` to the vendor-neutral "sensor pipeline"** across the stack.
- Wired `config.yaml` into `create_app`.
- Split recording into configurable `xdf_dir` / `video_dir` / `sqlite_path`; renamed the DB to `vcore.db`.
- Split the monolithic `App.css` into per-area style files.

### Fixed
- Dropped a redundant Dashboard-WS row from the New Session status list.
- Session Monitor video mirror fills width without pillarboxing.
- Hid low-level link-detail text from System Config and New Session.
- Reset the session timer during render to satisfy the react-hooks lint.

### Removed
- Unwired config keys (route paths, reconnect backoff, `sqlite_enabled`, video block).
- Dead Unity manifest builder.

## [2026-06-14] — Video playback, warnings split, connectivity log, 1080p spectator

### Added
- Play recorded session video back in Data History.
- Record the session video app-wide so it persists across screen changes.
- Stream the spectator feed at 1080p30 with configurable encoder caps.
- Separate genuine warnings from rule firings into two distinct logs; always show the Warnings panel with a healthy empty state.
- Record deduped per-link connectivity changes in the session event log.
- Scale-driven `StatusVisualizer` demo cube in the Unity scene.

### Changed
- Enabled Run In Background and synced Unity project settings.

### Fixed
- Normalized the `CampfireLight` rotation and set the spectator camera to 1080p.
- Correctly typed the `then.set` access in the Data History event summary.
- Gave the new Unity reporter scripts unique meta GUIDs.

### Removed
- Unused warnings CSS rules.

## [2026-06-12] — Link-status watchdog, Contract 4 (VR context) & Contract 5 (Unity behaviour)

Added two new contracts that let the VR runtime describe its study context and
feed its own behavioural telemetry through the same pipeline as sensor signals.

### Added
- **Contract 4 (`vr_context`)** — free-form study/scene context flows Unity → dashboard + recorder, rendered in a live VR-context panel, authored as key/value fields.
- **Contract 5 (`unity_behaviour`)** — behavioural channels ingested from Unity into the pipeline (charted, rule-evaluable, recorded); behavioural metrics declared per-object and re-scanned on scene change.
- Object-status manifest accepted as a typed, re-sendable message; object status re-handshakes on Unity scene change; `VCoreManager` persists across scene loads.
- Stale/recovery link-status transitions from the LSL watchdog; escalate a stale link to offline after prolonged silence; emit `browser-ws` status on dashboard connect/disconnect.
- Forward `rule_fired` events to the dashboard and always show the adaptation log.
- Signal-pipeline status section in System Config.
- `clear-fog-stressed` rule.

### Changed
- Decoupled mock-Unity behaviour values from specific rule thresholds.
- Source behavioural channels from Unity instead of the sensor stream.

### Fixed
- Prevent stale/offline oscillation after the stream goes silent.
- Push live link state on reconnect, clear stale statuses on disconnect, and push cached statuses to newly connected clients.
- Place the live VR-context panel within the signal-panel row.

### Removed
- Redundant Dashboard-WS entry (use `browser-ws` throughout); dead `wsState` labels; support/system logs from the sidebar; signal-pipeline & connection-detail sections from System Config; VR-context channels from the sensor manifest.

## [2026-06-11] — Unity POC & dashboard UX

### Added
- Unity 2022.3 project structure + package manifest, upgraded to editor `2022.3.62f3`.
- `ObjectStatus` + `StatusCollector` components; `VCoreConnection` WS client + `RequestDispatcher`.
- `SpectatorCamera`, `WebRtcSender`, and `VideoRecorder` components; a Sample scene wired to all V-CORE components.
- Extended signal manifest with grouped channels; three-panel grouped layout on the Session Monitor.
- Mock rule set for cognitive-load and affect-based VR adaptations.
- Clickable, editable rule cards with a pre-filled form; rich session detail view in Data History (chart + event log).
- Session timer + stop/pause controls; New Session link-status checks and nav callback.
- Rule-type colours + condition formatting (Rule Manager); chip labels + connection-state display (System Config); base / component / signal-panel styles.

### Changed
- Added `uv.lock` for reproducible Python dependencies; updated npm dependencies.

### Fixed
- snake_case serialization to match Contract 3b; Unity `imageconversion` module + `TagManager` YAML format.
- Handle and parse the nested ice-candidate signaling format from the browser; build a `MediaStream` from the track when Unity sends a trackless stream.
- Auto-start the LSL source on startup and fix categorical-channel decoding.
- Push Unity link status to the dashboard on reconnect; pin `time.monotonic` in the cooldown test; make the session event log scrollable.

## [2026-06-09] — Session recording, WebRTC video & first end-to-end tests

### Added
- XDF writer, SQLite session store, recorder, and sessions API; New Session + Data History wired to the recording API.
- WebRTC signaling broker, video store, and video-recording endpoints (backend); `VideoFeed` component, signaling client, and session-store wiring (frontend).
- Phase 8 graceful-degradation integration tests; end-to-end smoke tests and the `mock_pipeline` tool.

### Fixed
- ruff violations (contextlib.suppress, unused imports, import sort); ESLint violations (useCallback ordering, no-explicit-any in tests).
- Added the `httpx` dev dependency for the Starlette `TestClient`.

### Changed
- README updated with implemented status + quick-start instructions.

## [2026-06-07 – 06-08] — Contracts & backend core

The foundational milestone: the JSON-Schema contracts (the single source of
truth for cross-component messages) and the backend event pipeline that runs on
top of them, plus the first schema-driven dashboard.

### Added
- Project scaffold: backend (Python) + frontend (Vite) with pytest/vitest wired up.
- **Four JSON-Schema contracts** — Signal Schema, Rule Grammar, Object-Status Manifest, and Status Request — with valid + invalid golden examples.
- Python contract validators (pydantic models) + pytest suite; TypeScript ajv validators, a TS type-gen script, and a contracts CI gate.
- Async event bus + active manifest registry (Phase 2).
- Ingestion adapters, a signal-source ABC, stale detection, and fixtures.
- Rule-engine registry (hot-reloads + validates YAML/JSON rules), a degradation reconciler, and the evaluator.
- Outbound `ActionSink` + `WsSink` with target matching, a ZMQ transport stub, and the `mock_unity` tool.
- WebSocket dashboard bridge, the rules REST API, and the FastAPI app (composition root).
- Schema-driven dashboard with a renderer registry and screens.

### Fixed
- pytest empty-collection exit-5 and the vitest config type error.
- Vite dev proxy for the backend API + WebSocket routes.
- Stable empty array in `useChannels`; guarded the stale-socket `onclose`.
