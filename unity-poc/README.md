# V-CORE Unity POC

Thin Unity reference implementation for the V-CORE platform. Demonstrates the full
Contract 3 loop — Object-Status Manifest (3b) up, Status-Change Requests (3a) down —
plus the Amendment 2 video plane (a **LiveKit** SFU; recording via LiveKit Egress).

**Target Unity version:** 2022.3 LTS (any 2022.3.x patch)

---

## What's in here

The reusable client lives as an **embedded UPM package** at
[`Packages/com.vcore.client`](Packages/com.vcore.client/README.md) (assembly `VCore.Client`,
plus `VCore.Client.LiveKit` for the optional video publisher). Only the demo content
(`StatusVisualizer`, the Sample scene + props) stays under `Assets/`. The scripts below ship
in that package:

| Script | Role |
|---|---|
| `ObjectStatus.cs` | Component that declares one settable status (discrete or continuous) on a GameObject |
| `VCoreAction.cs` | Component that declares a parameterless **action** (command). Backend invokes it (scene- or object-scoped); wire `OnInvoke` to anything — the free-form counterpart to `ObjectStatus` |
| `StatusCollector.cs` | Scans the scene for all `ObjectStatus` components → builds the manifest JSON |
| `VCoreConnection.cs` | WebSocket client (`/ws/runtime`): sends manifest on connect, routes incoming requests, exposes `Send()` for reporters |
| `RequestDispatcher.cs` | Resolves incoming `{target, status, value}` requests to the matching `ObjectStatus` and invokes it |
| `VrContextReporter.cs` | Sends study-step / scene context (`vr_context`, Contract 4) → dashboard VR Context panel |
| `BehaviourReporter.cs` | Declares behavioural channels and streams their values (`behaviour_manifest` / `behaviour_sample`, Contract 5) → dashboard, rule engine, recorder |
| `BehaviourMetric.cs` | Per-object behavioural channel declaration, scene-scanned by `BehaviourReporter` (the behaviour analogue of `ObjectStatus`) |
| `SpectatorCamera.cs` | Mono camera rendering to a `RenderTexture` for video streaming |
| `LiveKitPublisher.cs` | Fetches a token from `/api/livekit/token` and publishes the spectator-cam video to the LiveKit SFU (the dashboard subscribes; recording is server-side via LiveKit Egress) |
| `BackendConfig.cs` | Shared `ScriptableObject` holding the backend host/port, referenced by `VCoreConnection` + `LiveKitPublisher` |
| `VCoreLauncher.cs` | One-component bootstrap: brings up the connection + reporters from a single Inspector with enable-toggles, and toggles the video publisher. The "drop into any scene" entry point. |

The pre-built **Sample scene** (`Assets/Scenes/Sample.unity`) contains:

| GameObject | Components |
|---|---|
| **VCoreManager** | `VCoreLauncher` · `VCoreConnection` · `StatusCollector` · `RequestDispatcher` · reporters |
| **CampfireLight** | `Light` · two `ObjectStatus` components (`brightness` continuous + `crackle` discrete) |
| **SpectatorCamera** | `Camera` · `SpectatorCamera` · `LiveKitPublisher` |
| **Main Camera** | `Camera` · `AudioListener` |

---

## Drop V-CORE into your own scene (the launcher)

`VCoreLauncher` is the single entry point for reusing the V-CORE client in any scene —
you don't wire the individual components by hand. Two ways to add it:

- **Prefab (recommended):** drag `Assets/Prefabs/VCore.prefab` into your scene. It bundles
  the launcher, connection, collector, dispatcher, and both reporters, pre-configured.
- **Bare component:** add `VCoreLauncher` to an empty GameObject. On play it adds the core
  `VCoreConnection` (which auto-pulls `StatusCollector` + `RequestDispatcher` via
  `[RequireComponent]`) and the enabled reporters for you.

Then set these on the **VCoreLauncher** Inspector — it's the one place you configure the stack:

| Field | Purpose |
|---|---|
| `Backend Config` | The shared `BackendConfig` asset. Pushed to the connection **and** the video publisher, so the address lives in one place. Leave empty to keep whatever each component already has. |
| `Scene Name` / `Runtime Id` | Identity reported in the Object-Status Manifest. |
| `Persist Across Scenes` | Keep the session (connection + reporters) alive across scene loads. |
| `Behaviour Metrics` | Enable/disable `BehaviourReporter`. |
| `Vr Context` | Enable/disable `VrContextReporter`. |
| `Video Publishing` | Enable/disable the assigned `LiveKitPublisher`. |
| `Publisher` | Reference to the `LiveKitPublisher` on your spectator-camera rig. Video needs its own `Camera`, so it lives on a separate GameObject — assign it here and `Video Publishing` toggles it. |

The launcher only overwrites a component's shared config when its own field is set, so it
never clobbers settings you authored directly on the bundled components.

---

## Step-by-step: open in Unity

### 1  Install Unity 2022.3 LTS via Unity Hub

1. Open **Unity Hub** → **Installs** → **Install Editor**.
2. Choose **2022.3.x LTS** (any patch).
3. In the module selector, enable **Windows Build Support (IL2CPP)** (or the target platform
   you need). You do **not** need Android/iOS/WebGL support for a desktop lab POC.
4. Finish the install.

### 2  Open the project

1. Unity Hub → **Projects** → **Open** → browse to this folder (`unity-poc/`).
2. Unity will detect the `ProjectSettings/ProjectVersion.txt` and open the project.
3. On first open Unity resolves the packages in `Packages/manifest.json`. This requires
   internet access — it will download:
   - `com.unity.webrtc` (≈ 50 MB, includes native WebRTC libs)
   - `com.unity.nuget.newtonsoft-json` (tiny)
4. Wait for the **Package Manager** progress bar and the **Asset Database** reimport to
   finish before touching anything. This takes 2–5 minutes on first open.

> **Tip:** if Unity Hub cannot find a 2022.3.x editor for this project, it will prompt you
> to install one. Click "Install suggested version".

### 3  Open the Sample scene

In the **Project** panel: `Assets → Scenes → Sample`.  
Double-click `Sample` to open it.  
You should see four GameObjects in the Hierarchy:

```
▼ VCoreManager       (VCoreLauncher + VCoreConnection / StatusCollector / RequestDispatcher / reporters)
▼ CampfireLight      (Directional Light + two ObjectStatus components)
▼ SpectatorCamera    (Camera + SpectatorCamera + LiveKitPublisher)
▼ Main Camera        (Camera + AudioListener)
```

### 4  Configure the backend address

Select **VCoreManager** in the Hierarchy. The **VCoreLauncher** is the single place to
configure the stack (it pushes the address to both the connection and the publisher):

| Component | Field | Default | Change to |
|---|---|---|---|
| `VCoreLauncher` | `Backend Config` | the shared asset | the `BackendConfig` whose `Host`/`Port` point at Machine A |
| `VCoreLauncher` | `Scene Name` | `sample_scene` | any string identifying this scene |
| `VCoreLauncher` | `Publisher` | the scene's `LiveKitPublisher` | already wired to the SpectatorCamera rig in the sample |

To change the address itself, edit the `BackendConfig` asset (`Assets/Settings/BackendConfig.asset`):
its `Host`/`Port` flow to every V-CORE component.

### 5  Wire the light-control event (optional but recommended)

The sample scene sends a brightness status request to `campfire_01` when V-CORE fires a rule.
To actually see the light dim:

1. Select **CampfireLight** in the Hierarchy.
2. In the Inspector find the **ObjectStatus** component with `Status Name = brightness`.
3. Under **On Continuous Value (Single)** click **+** and drag the `CampfireLight` GameObject
   into the object slot.
4. In the function dropdown select **Light → intensity**.

Now when V-CORE sends `{target:{tag:"ambient_light"}, status:"brightness", value:20}` the
light's intensity will be set to `20` (on the 0–100 scale you declared).

> The `crackle` ObjectStatus (discrete: `off / low / high`) works the same way — wire
> `On Discrete Value (String)` to whatever you want to drive (e.g. an audio source).

### 6  Start V-CORE backend

From the repo root:

```bash
cd backend
pip install -e ".[dev]"
cp config.example.yaml config.yaml
uvicorn vcore.app:app --reload --host 0.0.0.0 --port 8000
```

Or with Docker Compose:

```bash
docker compose up backend
```

### 7  Press Play

Press **▶ Play** in Unity. In the Console you should see:

```
[VCore] Connecting → ws://localhost:8000/ws/runtime
[VCore] Connected to V-CORE
[Dispatcher] Index built: 1 object(s), 2 tag(s)
[LiveKit] connected → ws://localhost:7880
[LiveKit] publishing spectator camera
```

V-CORE will log that it received the Object-Status Manifest and index it. The manifest
exposes:

```json
{
  "scene": "sample_scene",
  "objects": [
    {
      "id": "campfire_01",
      "tags": ["ambient_light", "fire"],
      "statuses": [
        { "name": "brightness", "type": "continuous", "range": {"min": 0, "max": 100} },
        { "name": "crackle",    "type": "discrete",   "values": ["off", "low", "high"] }
      ]
    }
  ]
}
```

Open the **V-CORE dashboard** (`http://localhost:5173`) → **Rule Manager** → **New Rule**.
The THEN side will offer `campfire_01` with `brightness` and `crackle`.

---

## Adding your own objects

1. Drop an **ObjectStatus** component onto any GameObject.
2. Set `Status Name`, `Type`, and the range/values.
3. Fill in `Object Id` (or leave empty to use the GameObject name) and add `Tags`.
4. Wire the `On Continuous Value` / `On Discrete Value` event in the Inspector.
5. Press Play — `StatusCollector` auto-collects it and sends the updated manifest.

Multiple `ObjectStatus` components on the same GameObject are grouped under one object
declaration in the manifest (same `id`, multiple `statuses`).

---

## Reporting context & behaviour (Contracts 4 & 5)

These two components push *upstream* telemetry to V-CORE over the same `/ws/runtime`
socket. They're already on the **VCoreManager** (and in the `VCore` prefab), gated by the
`VCoreLauncher`'s `Behaviour Metrics` / `Vr Context` toggles — untick a toggle to drop that
reporter. (To add them to a bare GameObject yourself: **Add Component** → `VrContextReporter`
/ `BehaviourReporter`, or just let the launcher add them.)

Out of the box they behave exactly like `tools/mock_unity.py` — no extra wiring needed:

| Component | Sends | Default behaviour |
|---|---|---|
| `VrContextReporter` | `vr_context` (Contract 4) | Walks the `Steps` list every `Step Interval` (6 s). Each step is a **free-form list of key/value fields** — any scene authors its own context keys in the Inspector. Renders in the dashboard's **VR Context** panel. |
| `BehaviourReporter` | `behaviour_manifest` + `behaviour_sample` (Contract 5) | Declares its channels, then streams each one swept across its range every `Sample Interval` (1 s). Renders in the **Behavioural** panel, feeds the rule engine, and is recorded. |

Behavioural channels can be declared in **two interchangeable ways** (merged, deduped by name):

- **Centralised** — the `Channels` list on `BehaviourReporter` (quick; good for a demo).
- **Per-object** — drop a `BehaviourMetric` component on any GameObject that tracks a metric.
  `BehaviourReporter` scene-scans them on connect, exactly like `StatusCollector` scans
  `ObjectStatus`. Call `BehaviourMetric.Report(value)` from that object's own script to feed
  real data; otherwise it sweeps synthetically like the centralised channels.

Both are **hybrid**: synthetic by default, but you drive them with real data from your own
scripts whenever you're ready —

```csharp
var ctx = FindObjectOfType<VrContextReporter>();
ctx.autoPlay = false;                       // stop the scripted walk-through
ctx.ReportContext(new Dictionary<string, object> {
    ["scene"] = "Aisle 3 – Dairy", ["step"] = "3 / 4", ["instruction"] = "Find the cheese",
});

var beh = FindObjectOfType<BehaviourReporter>();
beh.SetMetric("response_latency", 9.2f);    // real value overrides the synthetic sweep
beh.SetMetric("task_accuracy", 84f);
// beh.generateSyntheticData = false;        // optional: send only values you supply
```

`VCoreConnection` flushes the Object-Status Manifest first and only flips `IsConnected`
afterward, so the reporters always arrive after the handshake.

### Multi-scene sessions

`VCoreConnection.persistAcrossScenes` (on by default) keeps the **VCoreManager** —
connection and reporters — alive across scene loads via `DontDestroyOnLoad`, with a
singleton guard that destroys any duplicate manager a newly-loaded scene brings in. So one
V-CORE session spans many Unity scenes.

This gives you two natural scopes for behavioural metrics:

- **Session-scoped** (cross-scene): declare on the persistent manager — the `Channels` list,
  or a `BehaviourMetric` on the manager itself. These stay declared and rendering for the
  whole session.
- **Scene-scoped** (local): a `BehaviourMetric` on a scene prop. `BehaviourReporter` re-scans
  and re-declares on `sceneLoaded` / `sceneUnloaded`, so these channels join and leave the
  dashboard as scenes swap.

The **object-status side** tracks scenes too: on `sceneLoaded` / `sceneUnloaded`
`VCoreConnection` rebuilds `RequestDispatcher`'s target index and re-sends the
object-status manifest, so adaptations resolve against the live scene. Every
Unity → V-CORE frame — `object_status_manifest`, `vr_context`, `behaviour_manifest`,
`behaviour_sample` — is a typed `{"type", "payload"}` envelope, so any of them can be
(re)sent at any point in the session.

---

## Video (LiveKit)

The participant video runs over a **LiveKit** SFU:

1. `LiveKitPublisher` fetches a token from `…:8000/api/livekit/token` and connects to the
   LiveKit server, publishing the spectator-camera track.
2. The dashboard browser fetches a subscriber token and subscribes — its `<video>` shows the
   spectator view.
3. Recording is **server-side** (LiveKit Egress): the backend starts/stops it automatically on
   session start/stop, anchored to the LSL clock.

LiveKit + Egress run via Docker, and one value (`node_ip` = your LAN IP) must be set per
machine. See [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md) for the full setup.

---

## Session recording

Recording is **fully server-side** — there's nothing to call from Unity. When a session is
started from the dashboard, the backend's `LiveKitRecorder` finds the published video track and
starts a LiveKit **Track Egress**, writing `backend/data/video/<session_id>.webm` (anchored to
the LSL clock). Stopping the session stops the recording, and you can play it back in the
dashboard's **Data History** screen.

---

## Using this client in another project

The reusable client is **already a UPM package** —
[`Packages/com.vcore.client`](Packages/com.vcore.client/README.md) (assembly `VCore.Client`, plus
`VCore.Client.LiveKit` for the optional video publisher; its only hard dependency is
`Newtonsoft.Json`). To consume it in **another** Unity project, copy that folder into the target
project's `Packages/`, or reference it by path in the project's `manifest.json`
(`"com.vcore.client": "file:../path/to/com.vcore.client"`); add the LiveKit SDK
(`io.livekit.livekit-sdk`, a git-URL package) too if you want video. Then drop the `VCore` prefab
or add a `VCoreLauncher` and assign a `BackendConfig`. Full install + API reference:
[`com.vcore.client/README.md`](Packages/com.vcore.client/README.md).

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `[VCore] Connect failed` | Is V-CORE running? Is the host/port correct in the Inspector? |
| `[Dispatcher] No object with tag '…'` | Check that the `ObjectStatus` has the expected tag set in the Inspector |
| No video mirror in the dashboard | Is `livekit.enabled: true` and the LiveKit + Egress stack up? Is `node_ip` set to your LAN IP? See [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md) |
| Missing LiveKit/WebRTC namespace error | The LiveKit SDK isn't installed/resolved yet (the video publisher is guarded by `VCORE_LIVEKIT`) — add `io.livekit.livekit-sdk` and wait for the reimport |
| Scene opens with broken script references (yellow ?) | Unity couldn't resolve the `com.vcore.client` package — wait for the Package Manager + reimport to finish (the scripts live in `Packages/com.vcore.client/Runtime/`, not `Assets/`) |
