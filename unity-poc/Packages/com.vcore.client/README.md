# V-CORE Unity Client (`com.vcore.client`)

Reusable client for the [V-CORE](../../../README.md) adaptive-VR backend, packaged so it can
be dropped into any Unity project. It is the portable half of the `unity-poc` — the demo
scene, props, and `StatusVisualizer` stay in the project; everything reusable lives here.

**Unity:** 2022.3 LTS+

## What it provides

| Area | Components |
|---|---|
| Status loop (Contract 3) | `VCoreConnection` (WS link + reconnect + cross-scene lifetime), `StatusCollector` (manifest), `RequestDispatcher` (apply incoming changes), `ObjectStatus` (mark a GameObject adaptable) |
| Actions (Contract 3c) | `VCoreAction` — parameterless commands the backend can invoke (scene- or object-scoped). Wire its `OnInvoke` UnityEvent to anything; the rule builder offers it on the THEN side as an alternative to setting a status |
| Project catalog (Editor) | **V-CORE ▸ Bake Project Catalog** scans every Build-Settings scene + prefab for `ObjectStatus`/`VCoreAction` and writes `Assets/Resources/VCoreCatalog.json`. The client sends it on connect so the rule builder can author against objects/actions in scenes that aren't loaded yet |
| Upstream telemetry (Contracts 4 & 5) | `BehaviourReporter`, `BehaviourMetric`, `VrContextReporter` |
| Video (optional) | `SpectatorCamera`, and `LiveKitPublisher` in the separate **`VCore.Client.LiveKit`** assembly |
| Setup | `VCoreLauncher` (one-component bootstrap with enable-toggles), `BackendConfig` (shared address asset), `VCoreVideoPublisher` (base type the launcher toggles) |

## Assemblies

- **`VCore.Client`** — the core. Only depends on `com.unity.nuget.newtonsoft-json` (a package
  dependency, installed automatically).
- **`VCore.Client.LiveKit`** — `LiveKitPublisher`. Guarded by `defineConstraints: VCORE_LIVEKIT`,
  which a `versionDefines` entry sets **only when `io.livekit.livekit-sdk` is installed**. So the
  package compiles fine without the LiveKit SDK; the video publisher simply isn't built until you
  add the SDK. (The SDK is a git-URL package and can't be a `package.json` dependency, hence the
  opt-in module rather than a hard dependency.)

## Install

This repo embeds the package at `Packages/com.vcore.client`, so the `unity-poc` project uses it
directly. To use it in **another** project, either:

- copy this folder into that project's `Packages/`, or
- add it by path in the target `Packages/manifest.json`:
  `"com.vcore.client": "file:../path/to/com.vcore.client"`

For video, also add the LiveKit SDK to that project:
`"io.livekit.livekit-sdk": "https://github.com/livekit/client-sdk-unity.git"`

## Use

Add the `VCore` prefab (in the consuming project) or just add a **`VCoreLauncher`** component to a
GameObject, assign a `BackendConfig`, and tick the features you want. See the
[POC README](../../README.md#drop-v-core-into-your-own-scene-the-launcher) for the field-by-field
walkthrough.
