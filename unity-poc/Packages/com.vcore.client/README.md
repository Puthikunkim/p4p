# V-CORE Unity Client (`com.vcore.client`)

Reusable Unity client for the [V-CORE](../../../README.md) adaptive-VR backend. Add it to **any
new or existing Unity project** and that project becomes a fully-working V-CORE runtime: it
tells the backend what it can do, applies the adaptations the rule engine sends back, streams
behaviour/context to the dashboard, and (optionally) mirrors a spectator camera over LiveKit.

This README is the **setup + configuration guide** — what the package can do, how to install it,
and a step-by-step to wire it into your project. For a ready-made working example, see the
[POC sample scene](../../README.md) that consumes this exact package.

**Requirements:** Unity **2022.3 LTS+**. Sole hard dependency: `com.unity.nuget.newtonsoft-json`
(installed automatically). Video is optional and needs the LiveKit Unity SDK (see [Video](#7-video-optional-livekit)).

---

## What you can achieve with it

Everything below is driven by V-CORE's versioned **contracts**, so your scene stays decoupled
from the backend — you only declare *what* your scene can do; the dashboard/rules decide *when*.

| Capability | Contract | What you add | Result |
|---|---|---|---|
| **Make objects adaptable** | 3 (status) | `ObjectStatus` on a GameObject | The backend can set a `brightness`/`density`/… value on it; you wire that to any property |
| **Expose commands** | 3c (action) | `VCoreAction` on a GameObject (or scene-level) | The backend can fire a parameterless command (`advance_scene`, `extinguish`, …) |
| **Stream behaviour metrics** | 5 | `BehaviourReporter` / `BehaviourMetric` | Per-frame behavioural channels (response latency, idle time, …) flow into the same pipeline as sensors — charted, rule-evaluable, recorded |
| **Report study context** | 4 | `VrContextReporter` | The dashboard's **VR Context** panel shows the current scene/step/instruction |
| **Author rules ahead of time** | — | bake the project catalog (Editor) | The rule builder can target objects/actions in scenes that aren't loaded yet |
| **Live video mirror + recording** | — | `SpectatorCamera` + `LiveKitPublisher` | The researcher sees the participant's view; the backend records it server-side, LSL-synced |
| **Multi-scene sessions** | — | `persistAcrossScenes` (default on) | One V-CORE session spans many Unity scene loads |

You configure **all of it from one component** (`VCoreLauncher`) plus one shared address asset
(`BackendConfig`); the individual pieces below are only needed when you want that capability.

---

## 1. Install the package

The package is embedded in this repo at `Packages/com.vcore.client`, so the POC uses it directly.
To add it to **another** project, pick one:

- **Copy** this folder into the target project's `Packages/`, **or**
- **Reference by path** in the target project's `Packages/manifest.json`:
  ```jsonc
  { "dependencies": { "com.vcore.client": "file:../relative/or/absolute/path/to/com.vcore.client" } }
  ```
- or **Package Manager ▸ + ▸ Add package from disk…** and select this folder's `package.json`.

Newtonsoft.Json is pulled in automatically. (For video, also add the LiveKit SDK — see step 7.)

---

## 2. Point it at your backend (`BackendConfig`)

Create one shared address asset: **Assets ▸ Create ▸ V-CORE ▸ Backend Config**. Set:

| Field | Default | Set to |
|---|---|---|
| `Host` | `localhost` | the V-CORE backend host/IP (Machine A). Same machine → `localhost`; another machine → its LAN IP |
| `Port` | `8000` | the backend port |

Every V-CORE component reads its address from this one asset, so the backend location lives in
exactly one place. (Components also have inline `host`/`port` fallbacks used only when no
`BackendConfig` is assigned.)

---

## 3. Add the launcher (`VCoreLauncher`) — the one-component setup

`VCoreLauncher` is the entry point: add it to one GameObject (call it e.g. **VCoreManager**) and
it brings up the whole client on `Awake`. You don't wire the sub-components by hand — adding the
launcher's `VCoreConnection` auto-adds `StatusCollector` + `RequestDispatcher` (via
`[RequireComponent]`), and the launcher adds/enables the reporters per its toggles.

> The package ships no prefab; you add the `VCoreLauncher` component. (The POC's
> `Assets/Prefabs/VCore.prefab` is a ready-made example you can copy into your project.)

Configure it in the Inspector — this is the single place you set up the stack:

| Field | Default | Purpose |
|---|---|---|
| `Backend Config` | — | The shared `BackendConfig` asset. Pushed to the connection **and** the video publisher. Leave empty to keep whatever each component already has. |
| `Scene Name` | `scene` | Scene name reported in the Object-Status Manifest. |
| `Runtime Id` | `unity` | Runtime identifier reported in the manifest. |
| `Persist Across Scenes` | `true` | Keep the connection + reporters alive across scene loads (one session spans scenes). |
| `Behaviour Metrics` | `true` | Enable `BehaviourReporter` (Contract 5). |
| `Vr Context` | `true` | Enable `VrContextReporter` (Contract 4). |
| `Video Publishing` | `true` | Enable the assigned video publisher (needs `Publisher` set). |
| `Publisher` | — | The `LiveKitPublisher` on your spectator-camera rig (video needs its own `Camera`, so it lives on a separate object — reference it here). |

The launcher only overwrites a sub-component's shared config when its own field is set, so it
never clobbers settings you authored directly on the bundled components.

With just steps 1–3 your project already connects, sends a (possibly empty) manifest, and streams
synthetic behaviour/context. Steps 4–7 add real capabilities.

---

## 4. Make objects adaptable (`ObjectStatus`, Contract 3)

Put an `ObjectStatus` on any GameObject the backend should be able to change. `StatusCollector`
auto-scans the scene and includes it in the manifest; when a rule fires, `RequestDispatcher`
resolves the target and invokes your wired event on the main thread.

| Field | Purpose |
|---|---|
| `Object Id` | Unique id in the manifest. Empty → uses the GameObject name. |
| `Tags` | Tags rules can address this by (e.g. `ambient_light`, `fog`). Tag targets fan out to every matching object — this is what makes rules portable across scenes. |
| `Status Name` | The status as it appears in rules (e.g. `brightness`, `density`). |
| `Type` | `Continuous` (a float in `[Range Min, Range Max]`) or `Discrete` (one of `Discrete Values`). |
| `Range Min/Max` | Allowed range (continuous). |
| `Discrete Values` | Allowed states, e.g. `off / low / high` (discrete). |
| `On Continuous Value (float)` / `On Discrete Value (string)` | **Wire this to the actual effect** — e.g. a `Light.intensity`, a fog density, an animator parameter. |

**Example:** on a campfire `Light`, add two `ObjectStatus` components — `brightness` (continuous
0–100, tag `ambient_light`, wire `OnContinuousValue → Light.intensity`) and `crackle` (discrete
`off/low/high`, wire `OnDiscreteValue` to an audio source). Multiple `ObjectStatus` on one
GameObject are grouped under a single object id with multiple statuses.

---

## 5. Expose commands (`VCoreAction`, Contract 3c)

The free-form counterpart to a status: a parameterless command the backend can invoke. Add a
`VCoreAction`, set `Action Name`, choose a `Scope`, and wire `On Invoke` to anything (a method,
coroutine, Timeline, state-machine transition…).

- **Object** scope — addressed by `Object Id` / `Tags`, like a status (tag targets fan out).
- **Scene** scope — a global command addressed by `Action Name` only (no target).

Rules pick these on the **THEN** side as `action` instead of `set`.

---

## 6. Stream behaviour & context (Contracts 5 & 4)

Both reporters are added/toggled by the launcher (`Behaviour Metrics` / `Vr Context`) and work
**out of the box with synthetic data** — no wiring needed to see them on the dashboard. Drive
them with real values whenever you're ready:

- **`BehaviourReporter`** (Contract 5) declares behavioural channels and streams them; they merge
  into the signal manifest so they chart, feed rules, and record like sensor signals. Declare
  channels two interchangeable ways (merged, deduped by name): the centralised `Channels` list,
  or a **`BehaviourMetric`** component on any object (scene-scanned like `ObjectStatus`; call
  `BehaviourMetric.Report(value)` to feed it).
- **`VrContextReporter`** (Contract 4) pushes a free-form `{key: value}` context map (scene, step,
  instruction, …) to the dashboard's VR Context panel.

```csharp
// Real data from your own scripts:
var beh = FindObjectOfType<VCore.BehaviourReporter>();
beh.SetMetric("response_latency", 9.2f);     // overrides the synthetic sweep for that channel
// beh.generateSyntheticData = false;         // optional: send only values you supply

var ctx = FindObjectOfType<VCore.VrContextReporter>();
ctx.autoPlay = false;                         // stop the scripted walk-through
ctx.ReportContext(new Dictionary<string, object> {
    ["scene"] = "Aisle 3 – Dairy", ["step"] = "3 / 4", ["instruction"] = "Find the cheese",
});
```

---

## 7. Video (optional, LiveKit)

Mirror a spectator camera to the dashboard and let the backend record it server-side.

1. **Install the LiveKit SDK** (it's a git-URL package, so it can't be a `package.json`
   dependency): Package Manager ▸ **+ ▸ Add package from git URL** →
   `https://github.com/livekit/client-sdk-unity.git`. This flips on the `VCORE_LIVEKIT` define,
   which is the only thing that compiles `LiveKitPublisher` (the package builds fine without it —
   video just isn't available).
2. **Add a camera rig:** a GameObject with a `Camera` + **`SpectatorCamera`** (it renders to its
   own `RenderTexture`; set `width/height`, and in VR assign `followTarget` = the HMD camera to
   mirror head pose) + **`LiveKitPublisher`**.
3. **Wire it:** assign your `BackendConfig` to the publisher, then set the launcher's `Publisher`
   field to it and keep `Video Publishing` on.
4. The publisher fetches a token from `…/api/livekit/token` and publishes; the dashboard
   subscribes for the mirror; recording is **server-side** (LiveKit Egress, started on session
   start). The server side (LiveKit + Egress + the `node_ip` you must set) is covered in
   [`docs/LIVEKIT_SETUP.md`](../../../docs/LIVEKIT_SETUP.md).

---

## 8. Author rules ahead of time — the project catalog (Editor)

The live per-scene manifest only describes what's loaded now. To let the rule builder target
objects/actions in scenes that aren't loaded yet, bake a project-wide catalog:

- **V-CORE ▸ Bake Project Catalog** scans every Build-Settings scene **and** all prefab assets for
  `ObjectStatus`/`VCoreAction` → `Assets/Resources/VCoreCatalog.json`. `VCoreConnection` sends it
  on connect as an `object_status_catalog`.
- It re-bakes **automatically on every player build** (`VCoreCatalogBuildHook`); run the menu item
  to refresh while editing. Rules targeting an unloaded object are simply dormant until its scene
  loads, then activate.

---

## Verifying it works

Press **Play** with the backend running. The Console should show:

```
[VCore] Connecting → ws://localhost:8000/ws/runtime
[VCore] Connected to V-CORE
[Dispatcher] Index built: N object(s), M tag(s)
```

Then open the dashboard (`http://localhost:5173`) → **Rule Manager ▸ New Rule**: your objects and
their statuses/actions appear on the THEN side, and behaviour channels appear on the dashboard.
`VCoreConnection` flushes the manifest before flipping `IsConnected`, so reporters always arrive
after the handshake; it also re-sends the manifest and rebuilds the dispatch index on every
scene load/unload, so adaptations always resolve against the live scene.

---

## Assemblies

- **`VCore.Client`** — the core (status loop, reporters, spectator camera, launcher, the
  `VCoreVideoPublisher` base). Only depends on Newtonsoft.Json.
- **`VCore.Client.LiveKit`** — `LiveKitPublisher`, guarded by `defineConstraints: VCORE_LIVEKIT`,
  which a `versionDefines` entry sets **only when `io.livekit.livekit-sdk` is installed**. So the
  package compiles with or without the SDK.
- **`VCore.Client.Editor`** — the catalog baker + build hook.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `[VCore] Connect failed` | Is the backend running? Is `BackendConfig` host/port correct (LAN IP, not `localhost`, for a different machine)? |
| `[Dispatcher] No object with tag '…'` | The rule's target tag isn't on any `ObjectStatus` in the live scene — add the tag, or the rule shows disabled in the dashboard. |
| Objects don't appear in the rule builder | Is `VCoreLauncher` (hence `VCoreConnection`/`StatusCollector`) in the scene? Did the manifest send (see the connect logs)? |
| Missing LiveKit/`Unity.WebRTC` types | The LiveKit SDK isn't installed/resolved — add `io.livekit.livekit-sdk` (the publisher is guarded by `VCORE_LIVEKIT`). |
| Compile error about `Newtonsoft.Json` | Let the Package Manager finish resolving the auto-added dependency. |

---

## See also

- [`../../README.md`](../../README.md) — the POC: a working sample scene that consumes this package (the field-by-field walkthrough + the campfire example).
- [`../../../docs/HOW_IT_WORKS.md`](../../../docs/HOW_IT_WORKS.md) — how the whole system fits together.
- [`../../../docs/LIVEKIT_SETUP.md`](../../../docs/LIVEKIT_SETUP.md) — the video server (LiveKit + Egress) setup.
- [`../../../contracts/`](../../../contracts) — the JSON-Schema contracts this client speaks.
</content>
