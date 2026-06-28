# V-CORE Unity POC

A thin Unity reference project that **demonstrates** the [`com.vcore.client`](Packages/com.vcore.client/README.md)
package end-to-end: a ready-to-run Sample scene that declares adaptable objects, streams behaviour
and study-context upstream, and mirrors a spectator camera over LiveKit — so the whole backend ↔
runtime loop is demonstrable without a real VR project. Open it, point it at a backend, press Play.

**Target Unity version:** 2022.3 LTS (any 2022.3.x patch).

> **This page only documents what *this demo* implements and how to run it.** The client itself —
> install, configuration, every component, the full API — lives in the embedded UPM package and is
> documented once in **[`Packages/com.vcore.client/README.md`](Packages/com.vcore.client/README.md)**.
> If you want to *reuse* the client in your own project, start there, not here.

---

## What package features this POC implements, and where

Everything below is a feature of the package; this table is just the map of where each one is
wired up in the Sample scene (`Assets/Scenes/Sample.unity`). The **§** column points to the full
explanation in the [package README](Packages/com.vcore.client/README.md).

| Package feature | Where it's wired in this demo | Docs |
|---|---|---|
| One-component setup (`VCoreLauncher`) | **VCoreManager** (with `VCoreConnection` · `StatusCollector` · `RequestDispatcher`) | [§5](Packages/com.vcore.client/README.md#5-add-the-client-to-your-scene-vcorelauncher) |
| Adaptable object — **continuous** (`ObjectStatus`) | **CampfireLight** `brightness` (0–100) → already wired to the Light's `intensity`; **Cube** `brightness` → wired to `StatusVisualizer` (scales the cube) | [§6](Packages/com.vcore.client/README.md#6-make-objects-adaptable-objectstatus) |
| Adaptable object — **discrete** (`ObjectStatus`) | **CampfireLight** `crackle` (`off`/`low`/`high`) — declared; effect left unwired (wire to your own audio) | [§6](Packages/com.vcore.client/README.md#6-make-objects-adaptable-objectstatus) |
| **Tag fan-out** | **CampfireLight** and **Cube** are both tagged `ambient_light`, so one tag-targeted `brightness` rule drives both at once | [§6](Packages/com.vcore.client/README.md#6-make-objects-adaptable-objectstatus) |
| Command (`VCoreAction`) | **VCoreManager** `advance_scene` (Scene scope) — declared; `On Invoke` left empty for you to fill | [§7](Packages/com.vcore.client/README.md#7-expose-commands-vcoreaction) |
| Behaviour metrics (`BehaviourReporter`) | **VCoreManager** — 6 synthetic channels (response latency, accuracy, idle time, …) | [§8](Packages/com.vcore.client/README.md#8-stream-behaviour-metrics-behaviourreporter--behaviourmetric) |
| Study context (`VrContextReporter`) | **VCoreManager** — a 4-step supermarket walkthrough on a timer | [§9](Packages/com.vcore.client/README.md#9-report-study-context-vrcontextreporter) |
| Video — spectator mirror + recording (`SpectatorCamera` + `LiveKitPublisher`) | **SpectatorCamera** (1920×1080), published to LiveKit | [§10](Packages/com.vcore.client/README.md#10-video--spectator-mirror--recording-spectatorcamera--livekit) |
| Multi-scene persistence | `Persist Across Scenes` ticked on **VCoreManager**'s `VCoreLauncher` | [§12](Packages/com.vcore.client/README.md#12-multi-scene-sessions) |

### Sample scene Hierarchy

```
VCoreManager     VCoreLauncher · VCoreConnection · StatusCollector · RequestDispatcher
                 · BehaviourReporter · VrContextReporter · VCoreAction (advance_scene)
CampfireLight    Light · ObjectStatus (brightness → Light.intensity) · ObjectStatus (crackle, discrete)
Cube             MeshRenderer · ObjectStatus (brightness → StatusVisualizer) · StatusVisualizer
SpectatorCamera  Camera · SpectatorCamera · LiveKitPublisher
Main Camera      Camera · AudioListener
```

### Demo-only content (not part of the package)

These live under `Assets/` and exist purely to make the demo tangible — they are **not** part of
the reusable client:

- `Assets/Scripts/StatusVisualizer.cs` — maps a continuous status value to a GameObject's scale, so
  a rule's effect is visible in the camera feed (used by **Cube**).
- The **CampfireLight** and **Cube** props and the **Sample** scene.
- `Assets/Prefabs/VCore.prefab` — a pre-assembled **VCoreManager** you can drag into another scene
  as a starting point (see package [§5](Packages/com.vcore.client/README.md#5-add-the-client-to-your-scene-vcorelauncher)).

---

## Run this demo

The scene is already fully wired — there is **no in-Editor setup** beyond pointing it at a backend.

1. **Open the project.** Unity Hub → **Open** → select this `unity-poc/` folder. On first open, wait
   for the Package Manager to resolve packages and the asset import to finish (a few minutes — it
   pulls `com.unity.nuget.newtonsoft-json`). If Hub offers to install a matching 2022.3.x editor,
   accept it.
2. **Open the scene.** Project window → `Assets/Scenes/Sample`.
3. **Point it at your backend.** Select `Assets/Settings/BackendConfig.asset` and set **Host**/**Port**
   in the Inspector. Leave `localhost` / `8000` if the backend runs on the same machine; otherwise
   enter the backend machine's LAN IP. (One asset feeds every component — see package
   [§4](Packages/com.vcore.client/README.md#4-point-it-at-your-backend-backendconfig).)
4. **Start the backend** (from the repo root):

   ```bash
   cd backend
   pip install -e ".[dev]"
   cp config.example.yaml config.yaml
   uvicorn vcore.app:app --reload --host 0.0.0.0 --port 8000
   ```

   Or with Docker: `docker compose up backend`.
5. **Press ▶ Play.** The Console shows the connect + manifest lines (the exact lines and how to
   verify are in package [§13](Packages/com.vcore.client/README.md#13-verify-it-works)).

**See it react:** open the dashboard (`http://localhost:5173`) → **Rule Manager ▸ New Rule**, and on
the THEN side target tag `ambient_light`, status `brightness`. When the rule fires, the campfire
dims **and** the cube scales — both objects respond to the one tag-targeted rule.

---

## Video & recording (in this demo)

The **SpectatorCamera** rig publishes over a LiveKit SFU; the dashboard subscribes for the live
mirror, and the backend records it **server-side** (LiveKit Egress, anchored to the LSL clock) to
`backend/data/video/<session_id>.webm`, replayable in the dashboard's **Data History** screen.
There is nothing to call from Unity. The LiveKit + Egress stack runs via Docker and needs one
per-machine value (`node_ip` = your LAN IP) — see [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md).

---

## See also

- [`Packages/com.vcore.client/README.md`](Packages/com.vcore.client/README.md) — the client: install,
  configuration, every component, and troubleshooting (start here to reuse it).
- [`../docs/HOW_IT_WORKS.md`](../docs/HOW_IT_WORKS.md) — how the whole V-CORE system fits together.
- [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md) — the video server (LiveKit + recording) setup.
