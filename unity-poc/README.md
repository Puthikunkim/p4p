# V-CORE Unity POC

Thin Unity reference implementation for the V-CORE platform. Demonstrates the full
Contract 3 loop — Object-Status Manifest (3b) up, Status-Change Requests (3a) down —
plus the Amendment 2 WebRTC video plane.

**Target Unity version:** 2022.3 LTS (any 2022.3.x patch)

---

## What's in here

| Script | Role |
|---|---|
| `ObjectStatus.cs` | Component that declares one settable status (discrete or continuous) on a GameObject |
| `StatusCollector.cs` | Scans the scene for all `ObjectStatus` components → builds the manifest JSON |
| `VCoreConnection.cs` | WebSocket client (`/ws/runtime`): sends manifest on connect, routes incoming requests, exposes `Send()` for reporters |
| `RequestDispatcher.cs` | Resolves incoming `{target, status, value}` requests to the matching `ObjectStatus` and invokes it |
| `VrContextReporter.cs` | Sends study-step / scene context (`vr_context`, Contract 4) → dashboard VR Context panel |
| `BehaviourReporter.cs` | Declares behavioural channels and streams their values (`behaviour_manifest` / `behaviour_sample`, Contract 5) → dashboard, rule engine, recorder |
| `BehaviourMetric.cs` | Per-object behavioural channel declaration, scene-scanned by `BehaviourReporter` (the behaviour analogue of `ObjectStatus`) |
| `SpectatorCamera.cs` | Mono camera rendering to a `RenderTexture` for WebRTC streaming |
| `WebRtcSender.cs` | Connects to `/ws/signaling`, negotiates WebRTC, streams spectator-cam video to the dashboard |
| `VideoRecorder.cs` | Captures the spectator cam to PNG frames stamped with the LSL session start time |

The pre-built **Sample scene** (`Assets/Scenes/Sample.unity`) contains:

| GameObject | Components |
|---|---|
| **VCoreManager** | `VCoreConnection` · `StatusCollector` · `RequestDispatcher` |
| **CampfireLight** | `Light` · two `ObjectStatus` components (`brightness` continuous + `crackle` discrete) |
| **SpectatorCamera** | `Camera` · `SpectatorCamera` · `WebRtcSender` · `VideoRecorder` |
| **Main Camera** | `Camera` · `AudioListener` |

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
▼ VCoreManager       (empty, has VCoreConnection / StatusCollector / RequestDispatcher)
▼ CampfireLight      (Directional Light + two ObjectStatus components)
▼ SpectatorCamera    (Camera + SpectatorCamera + WebRtcSender + VideoRecorder)
▼ Main Camera        (Camera + AudioListener)
```

### 4  Configure the backend address

Select **VCoreManager** in the Hierarchy. In the **Inspector**:

| Component | Field | Default | Change to |
|---|---|---|---|
| `VCoreConnection` | `Host` | `localhost` | IP of Machine A if running on a different machine |
| `VCoreConnection` | `Port` | `8000` | port V-CORE is bound to |
| `StatusCollector` | `Scene Name` | `sample_scene` | any string identifying this scene |
| `WebRtcSender` | `Host` / `Port` | same as above | same as `VCoreConnection` |

Select **SpectatorCamera**:

| Component | Field | Default | Notes |
|---|---|---|---|
| `VideoRecorder` | `Vcore Base Url` | `http://localhost:8000` | update if on a different machine |

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
[WebRTC] Connecting signaling → ws://localhost:8000/ws/signaling
[WebRTC] Registered as publisher (peer_id=…)
[WebRTC] SDP offer sent
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
socket. Add both to the **VCoreManager** GameObject (the one with `VCoreConnection`):

1. Select **VCoreManager** → **Add Component** → `VrContextReporter`.
2. **Add Component** → `BehaviourReporter`.

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

## WebRTC video (Amendment 2)

The video plane works without any extra setup if the dashboard browser is open while Unity
is playing:

1. The dashboard opens `ws://[host]:8000/ws/signaling` as a subscriber.
2. Unity opens the same path as a publisher and sends an SDP offer.
3. V-CORE brokers the offer/answer + ICE candidates.
4. The dashboard's `<video>` element shows the spectator-cam view within ~150 ms.

**V-CORE never relays media** — the video is peer-to-peer Unity → browser (UDP/WebRTC).

If WebRTC fails (NAT issues on a non-flat network), add a TURN server in
`WebRtcSender.iceServerUrls` in the Inspector.

---

## Session recording

Call the public API on `VideoRecorder` from any manager script:

```csharp
var rec = FindObjectOfType<VideoRecorder>();
rec.StartRecording("session-2026-06-11", lslStartTime: "2026-06-11T09:00:00.000Z");
// ... session runs ...
rec.StopRecording(upload: true);
```

Frames are saved to `Application.persistentDataPath/Recordings/<sessionId>/`. On Windows
this is typically `%APPDATA%/../LocalLow/<CompanyName>/<ProductName>/Recordings/`.

---

## Promoting to a UPM package

Each script has no inter-project dependencies beyond `Newtonsoft.Json` and
`com.unity.webrtc`. To package:

1. Move the scripts to a folder named `com.vcore.unity-poc/` with a `package.json`.
2. Add the package to any Unity project via the Package Manager's **Add package from disk**
   or a Git URL.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `[VCore] Connect failed` | Is V-CORE running? Is the host/port correct in the Inspector? |
| `[Dispatcher] No object with tag '…'` | Check that the `ObjectStatus` has the expected tag set in the Inspector |
| `[WebRTC] Signaling connect failed` | Is the dashboard also connected? V-CORE's signaling broker needs at least one subscriber before it is useful |
| Missing `Unity.WebRTC` namespace error | Package Manager hasn't resolved yet — wait for the reimport to finish |
| Scene opens with broken script references (yellow ?) | Unity couldn't find the scripts. Check that the `.cs` files are in `Assets/Scripts/` and Unity has finished importing |
