# V-CORE Unity POC

A thin Unity reference implementation for the V-CORE platform — a **ready-to-run demo** of the
full Contract 3 loop (Object-Status Manifest up, Status-Change Requests down) plus the video
plane (a **LiveKit** SFU; recording via LiveKit Egress). It exists so the whole backend ↔ runtime
loop is demonstrable without a real VR project.

**Target Unity version:** 2022.3 LTS (any 2022.3.x patch)

> **Reusing the client in your own project?** The runtime code lives in the embedded UPM package
> [`Packages/com.vcore.client`](Packages/com.vcore.client/README.md) — **its README is the
> install + configuration + API reference.** This page is only about running *this* demo project.

---

## What's in here

The reusable client is the embedded package at
[`Packages/com.vcore.client`](Packages/com.vcore.client/README.md) (assemblies `VCore.Client` +
the optional `VCore.Client.LiveKit`). Only the **demo content** lives under `Assets/`: the
`StatusVisualizer` script, the `VCore` prefab, and the Sample scene + props.

The pre-built **Sample scene** (`Assets/Scenes/Sample.unity`) contains:

| GameObject | Components |
|---|---|
| **VCoreManager** | `VCoreLauncher` · `VCoreConnection` · `StatusCollector` · `RequestDispatcher` · reporters |
| **CampfireLight** | `Light` · two `ObjectStatus` components (`brightness` continuous + `crackle` discrete) |
| **SpectatorCamera** | `Camera` · `SpectatorCamera` · `LiveKitPublisher` |
| **Main Camera** | `Camera` · `AudioListener` |

What each component does, and the full `VCoreLauncher` field reference, is in the
[package README](Packages/com.vcore.client/README.md).

---

## Step-by-step: open and run the demo

### 1  Install Unity 2022.3 LTS via Unity Hub

1. Open **Unity Hub** → **Installs** → **Install Editor**.
2. Choose **2022.3.x LTS** (any patch).
3. In the module selector, enable **Windows Build Support (IL2CPP)** (or the target platform
   you need). You do **not** need Android/iOS/WebGL support for a desktop lab POC.
4. Finish the install.

### 2  Open the project

1. Unity Hub → **Projects** → **Open** → browse to this folder (`unity-poc/`).
2. Unity detects `ProjectSettings/ProjectVersion.txt` and opens the project.
3. On first open Unity resolves the packages in `Packages/manifest.json` (needs internet) —
   notably `com.unity.nuget.newtonsoft-json`. Wait for the **Package Manager** progress bar and
   the **Asset Database** reimport to finish before touching anything (2–5 minutes on first open).

> **Tip:** if Unity Hub can't find a 2022.3.x editor for this project it will prompt you to
> install one — click "Install suggested version".

### 3  Open the Sample scene

In the **Project** panel: `Assets → Scenes → Sample`. Double-click `Sample` to open it. You
should see four GameObjects in the Hierarchy:

```
▼ VCoreManager       (VCoreLauncher + VCoreConnection / StatusCollector / RequestDispatcher / reporters)
▼ CampfireLight      (Directional Light + two ObjectStatus components)
▼ SpectatorCamera    (Camera + SpectatorCamera + LiveKitPublisher)
▼ Main Camera        (Camera + AudioListener)
```

### 4  Point it at your backend

Select **VCoreManager** → on the **VCoreLauncher**, set `Backend Config` to the `BackendConfig`
whose `Host`/`Port` point at your backend (Machine A). To change the address itself, edit the
`BackendConfig` asset (`Assets/Settings/BackendConfig.asset`) — it flows to every V-CORE
component. (Full launcher/`BackendConfig` field reference: [package README §4–5](Packages/com.vcore.client/README.md).)

### 5  Wire the light-control event (the demo effect)

The sample sends a brightness status request to `campfire_01` when V-CORE fires a rule. To
actually see the light dim:

1. Select **CampfireLight** in the Hierarchy.
2. In the Inspector find the **ObjectStatus** with `Status Name = brightness`.
3. Under **On Continuous Value (Single)** click **+** and drag the `CampfireLight` GameObject
   into the object slot.
4. In the function dropdown select **Light → intensity**.

Now when V-CORE sends `{target:{tag:"ambient_light"}, status:"brightness", value:20}` the light's
intensity is set to `20` (on the 0–100 scale you declared). The `crackle` ObjectStatus (discrete:
`off / low / high`) works the same way — wire `On Discrete Value (String)` to drive an audio
source, etc.

### 6  Start the V-CORE backend

From the repo root:

```bash
cd backend
pip install -e ".[dev]"
cp config.example.yaml config.yaml
uvicorn vcore.app:app --reload --host 0.0.0.0 --port 8000
```

Or with Docker Compose: `docker compose up backend`.

### 7  Press Play

Press **▶ Play** in Unity. In the Console you should see:

```
[VCore] Connecting → ws://localhost:8000/ws/runtime
[VCore] Connected to V-CORE
[Dispatcher] Index built: 1 object(s), 2 tag(s)
[LiveKit] connected → ws://localhost:7880
[LiveKit] publishing spectator camera
```

V-CORE logs that it received the Object-Status Manifest and indexed it. The manifest exposes:

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

Open the **V-CORE dashboard** (`http://localhost:5173`) → **Rule Manager** → **New Rule**. The
THEN side offers `campfire_01` with `brightness` and `crackle`.

---

## Going further

These are all **client features documented once in the
[package README](Packages/com.vcore.client/README.md)** — the same package this POC consumes:

- **Add your own adaptable objects / commands** — `ObjectStatus` (§6) and `VCoreAction` (§7).
- **Stream behaviour & study context** — `BehaviourReporter` / `BehaviourMetric` and
  `VrContextReporter`, with real-data snippets (§8–9).
- **Author rules before scenes load** — **V-CORE ▸ Bake Project Catalog** (§11).
- **Reuse the client in another project** — copy/reference the package and run
  **V-CORE ▸ Add to Scene** (§3, §5).

Multi-scene behaviour (`persistAcrossScenes`, manifest re-send on scene load) is covered there
too.

---

## Video & recording (in this demo)

The SpectatorCamera rig publishes over a **LiveKit** SFU; the dashboard subscribes for the live
mirror, and the backend records it **server-side** (LiveKit Egress, anchored to the LSL clock) to
`backend/data/video/<session_id>.webm`, playable in the dashboard's **Data History** screen.
There's nothing to call from Unity. LiveKit + Egress run via Docker and need one per-machine value
(`node_ip` = your LAN IP) — see [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md).

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `[VCore] Connect failed` | Is the backend running? Is the `BackendConfig` host/port correct? |
| Scene opens with broken script references (yellow ?) | Unity hasn't resolved the `com.vcore.client` package yet — wait for Package Manager + reimport to finish (the scripts live in `Packages/com.vcore.client/Runtime/`, not `Assets/`). |
| No video mirror in the dashboard | Is the LiveKit + Egress stack up and `node_ip` set to your LAN IP? See [`../docs/LIVEKIT_SETUP.md`](../docs/LIVEKIT_SETUP.md). |
| `[Dispatcher] No object with tag '…'` | The `ObjectStatus` doesn't have the expected tag set in the Inspector. |

More client-level troubleshooting (assemblies, LiveKit define, Newtonsoft) is in the
[package README](Packages/com.vcore.client/README.md#troubleshooting).
