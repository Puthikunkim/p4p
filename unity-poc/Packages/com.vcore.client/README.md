# V-CORE Unity Client (`com.vcore.client`)

Reusable Unity client for the [V-CORE](../../../README.md) adaptive-VR backend. Add it to **any
new or existing Unity project** and that project becomes a fully-working V-CORE runtime: it tells
the backend what it can do, applies the adaptations the rule engine sends back, streams
behaviour and study-context to the dashboard, and (optionally) mirrors a spectator camera to the
researcher over LiveKit.

This README is a **complete, step-by-step setup and usage guide**. It assumes **no prior V-CORE
knowledge and only beginner-level Unity knowledge** — every Editor action is spelled out. For a
ready-made working scene that already wires all of this up, see the
[POC sample scene](../../README.md), which consumes this exact package.

**Requirements:** Unity **2022.3 LTS or newer**. The only hard dependency,
`com.unity.nuget.newtonsoft-json`, installs automatically. Video is optional and needs the
LiveKit Unity SDK (see [§10 Video](#10-video--spectator-mirror--recording-spectatorcamera--livekit)).

---

## Contents

1. [Unity terms used in this guide](#1-unity-terms-used-in-this-guide)
2. [What you can do with this package](#2-what-you-can-do-with-this-package)
3. [Install the package](#3-install-the-package)
4. [Point it at your backend (`BackendConfig`)](#4-point-it-at-your-backend-backendconfig)
5. [Add the client to your scene (`VCoreLauncher`)](#5-add-the-client-to-your-scene-vcorelauncher)
6. [Make objects adaptable (`ObjectStatus`)](#6-make-objects-adaptable-objectstatus)
7. [Expose commands (`VCoreAction`)](#7-expose-commands-vcoreaction)
8. [Stream behaviour metrics (`BehaviourReporter` / `BehaviourMetric`)](#8-stream-behaviour-metrics-behaviourreporter--behaviourmetric)
9. [Report study context (`VrContextReporter`)](#9-report-study-context-vrcontextreporter)
10. [Video — spectator mirror + recording (`SpectatorCamera` + LiveKit)](#10-video--spectator-mirror--recording-spectatorcamera--livekit)
11. [Author rules ahead of time — the project catalog](#11-author-rules-ahead-of-time--the-project-catalog)
12. [Multi-scene sessions](#12-multi-scene-sessions)
13. [Verify it works](#13-verify-it-works)
14. [Assemblies & how the package is structured](#14-assemblies--how-the-package-is-structured)
15. [Troubleshooting](#15-troubleshooting)
16. [See also](#16-see-also)

---

## 1. Unity terms used in this guide

If you're new to Unity, here are the only terms and windows you need. (In Unity, open a window
from the top menu under **Window** if you can't see it.)

| Term | What it means |
|---|---|
| **Scene** | The "level" you're editing — the set of things currently in your world. |
| **GameObject** | A single thing in a scene (a light, a camera, an empty container…). Everything in a scene is a GameObject. |
| **Component** | A behaviour you attach to a GameObject to give it abilities. A `Light` is a component; the V-CORE scripts you add (like `ObjectStatus`) are components too. |
| **Hierarchy** window | The list of GameObjects in the open scene (usually on the left). |
| **Inspector** window | Shows and edits the components of whatever GameObject you've selected (usually on the right). |
| **Project** window | Your asset files on disk (scripts, scenes, settings assets…), usually along the bottom. |
| **Console** window | Where log messages and errors appear (**Window ▸ General ▸ Console**). You'll watch this to confirm V-CORE connected. |
| **Add Component** | A button at the bottom of the Inspector that attaches a component to the selected GameObject. |
| **UnityEvent** | A hook you wire **in the Inspector** so that "when X happens, call this function." V-CORE uses these so you can connect a backend value to any property without writing code. |
| **ScriptableObject asset** | A small settings file saved in your project. V-CORE's `BackendConfig` is one — it just stores the backend address. |
| **Prefab** | A saved, reusable GameObject you can drag into any scene. |
| **Play mode** | Running the scene by pressing the **▶ Play** button at the top of the Editor. |

Throughout, **bold** names are exactly what you'll see/click in the Editor, and `code` names are
the underlying script field names.

---

## 2. What you can do with this package

Everything is driven by V-CORE's versioned **contracts**: your Unity scene only declares *what*
it can do, and the dashboard/rule-engine decides *when*. Your scene never hard-codes backend
logic.

| Capability | What you add | Result | Section |
|---|---|---|---|
| **Make objects adaptable** | an `ObjectStatus` component | The backend can set a value (e.g. `brightness`) on the object; you wire that value to any property (a light's intensity, fog density, an animator parameter…). | [§6](#6-make-objects-adaptable-objectstatus) |
| **Expose commands** | a `VCoreAction` component | The backend can fire a named, parameterless command (`advance_scene`, `extinguish`…) that runs any code you wire up. | [§7](#7-expose-commands-vcoreaction) |
| **Stream behaviour metrics** | `BehaviourReporter` (+ optional `BehaviourMetric`) | Per-second behavioural numbers (response latency, idle time…) flow into the dashboard, feed rules, and get recorded — exactly like sensor signals. | [§8](#8-stream-behaviour-metrics-behaviourreporter--behaviourmetric) |
| **Report study context** | `VrContextReporter` | The dashboard's **VR Context** panel shows the participant's current scene / step / instruction. | [§9](#9-report-study-context-vrcontextreporter) |
| **Mirror + record video** | `SpectatorCamera` + `LiveKitPublisher` | The researcher sees the participant's view live; the backend records it server-side, time-synced to the signals. | [§10](#10-video--spectator-mirror--recording-spectatorcamera--livekit) |
| **Author rules before a scene loads** | bake the project catalog (Editor menu) | The dashboard's rule builder can target objects/actions in scenes that aren't open yet. | [§11](#11-author-rules-ahead-of-time--the-project-catalog) |
| **One session across many scenes** | `Persist Across Scenes` (on by default) | One V-CORE session keeps running as your project loads and unloads Unity scenes. | [§12](#12-multi-scene-sessions) |

You configure most of it from **one component** (`VCoreLauncher`) plus **one settings asset**
(`BackendConfig`). The per-feature components in §6–§10 are only needed for the features you want.

---

## 3. Install the package

You need the `com.vcore.client` folder added to your Unity project. Pick whichever method fits:

### Option A — Copy the folder (simplest)

1. In your file explorer, copy the whole `com.vcore.client` folder.
2. Paste it into your Unity project's **`Packages/`** folder (next to `manifest.json`), so you
   have `YourProject/Packages/com.vcore.client/`.
3. Switch back to Unity. It will detect and import the package automatically (watch the bottom
   status bar; the first import takes a few seconds).

### Option B — Reference it by path (keeps one shared copy)

Edit your project's **`Packages/manifest.json`** and add a line under `"dependencies"`:

```jsonc
{
  "dependencies": {
    "com.vcore.client": "file:../relative/or/absolute/path/to/com.vcore.client"
  }
}
```

Save the file; Unity re-resolves packages when it regains focus.

### Option C — Add from disk via the UI

1. In Unity, open **Window ▸ Package Manager**.
2. Click the **+** button (top-left of the Package Manager window).
3. Choose **Add package from disk…**.
4. Navigate to the `com.vcore.client` folder and select its **`package.json`** file, then click
   **Open**.

> **What gets installed automatically:** Newtonsoft.Json (the JSON library V-CORE uses). You'll
> see it appear under Package Manager ▸ Packages: In Project. For video, you'll also add the
> LiveKit SDK later — see [§10](#10-video--spectator-mirror--recording-spectatorcamera--livekit).

When the import finishes, the package's scripts (e.g. `VCoreLauncher`, `ObjectStatus`) are
available as components you can add to GameObjects.

---

## 4. Point it at your backend (`BackendConfig`)

`BackendConfig` is a tiny settings asset that holds the address of your V-CORE backend (the
machine running the Python server). Every V-CORE component reads the address from this one asset,
so the backend location lives in exactly one place.

**Create it:**

1. In the **Project** window, open the folder you want it in (e.g. `Assets/Settings/` — create
   that folder first if you like: right-click ▸ **Create ▸ Folder**).
2. Right-click in the folder (or use the top menu **Assets**) ▸ **Create ▸ V-CORE ▸ Backend
   Config**.
3. A new asset called **BackendConfig** appears. Click it once to select it; its fields show in
   the **Inspector**.

**Set its fields in the Inspector:**

| Field | Default | Set it to |
|---|---|---|
| **Host** | `localhost` | The backend machine. If Unity and the backend run on the **same computer**, leave it `localhost`. If the backend is on **another machine** (the typical lab setup), enter that machine's **LAN IP address** (e.g. `192.168.1.42`). |
| **Port** | `8000` | The backend's port. Leave `8000` unless you changed it in the backend's `config.yaml`. |

That's the whole asset. You'll assign it to the launcher in the next step.

> **Note:** the components also have their own inline `host`/`port` fields, but those are only
> used as a fallback when **no** `BackendConfig` is assigned. Using the asset is the recommended
> way, so all components agree on one address.

---

## 5. Add the client to your scene (`VCoreLauncher`)

`VCoreLauncher` is the one component that boots the whole client. There are two ways to add it.

### Fastest path — the **V-CORE ▸ Add to Scene** menu

1. In the top menu bar, click **V-CORE ▸ Add to Scene**.
2. This creates a GameObject called **VCoreManager** in your scene, already carrying the launcher,
   the connection, and the reporters. It also **finds or creates** a `BackendConfig`
   (`Assets/Settings/BackendConfig.asset`) and assigns it for you. If the LiveKit SDK is
   installed, it also adds a spectator-camera rig and wires it up.
3. Select **VCoreManager** in the Hierarchy, make sure its **Backend Config** points at the asset
   from [§4](#4-point-it-at-your-backend-backendconfig) (open that asset and set Host/Port), and
   you're ready to press Play.

### By hand

1. In the **Hierarchy**, right-click ▸ **Create Empty**. Rename the new GameObject to
   **VCoreManager** (optional but tidy).
2. With it selected, in the **Inspector** click **Add Component**, type **"VCore Launcher"**, and
   press Enter to add it.
3. You don't need to add the other pieces yourself: when the scene plays, the launcher adds the
   core connection (which in turn pulls in the components that collect your objects and apply
   incoming requests) plus the reporters, according to its toggles. *(If you'd like to see them in
   the Editor before playing, also Add Component ▸ **"VCore Connection"** — it auto-adds the two
   helpers it requires.)*

> **No prefab is shipped, on purpose.** A prefab stored inside a package is read-only for the
> projects that use it and can't point at your project's own `BackendConfig`, so it would save
> almost nothing. Use **Add to Scene** above, or copy the POC's `Assets/Prefabs/VCore.prefab`
> into your own project as a starting point if you prefer a draggable object.

### The `VCoreLauncher` fields (Inspector)

This component is the single place you configure the stack. Select **VCoreManager** to see it:

| Field | Default | What it does |
|---|---|---|
| **Backend Config** | *(empty)* | The `BackendConfig` asset from [§4](#4-point-it-at-your-backend-backendconfig). The launcher pushes this address to the connection **and** the video publisher, so you only set it once. If you leave it empty, each component keeps whatever address it already has. |
| **Scene Name** | `scene` | A label for this scene, reported to the backend so you can tell scenes apart. Set it to anything meaningful (e.g. `calm_forest`). |
| **Runtime Id** | `unity` | A label identifying this runtime in the backend. Leave as `unity` unless you run several runtimes. |
| **Persist Across Scenes** | `true` (ticked) | Keep the V-CORE session alive when you load/unload Unity scenes, so one study session can span many scenes. See [§12](#12-multi-scene-sessions). |
| **Behaviour Metrics** | `true` | Turn the behaviour reporter on/off ([§8](#8-stream-behaviour-metrics-behaviourreporter--behaviourmetric)). |
| **Vr Context** | `true` | Turn the VR-context reporter on/off ([§9](#9-report-study-context-vrcontextreporter)). |
| **Video Publishing** | `true` | Turn the assigned video publisher on/off. Has no effect unless **Publisher** is set ([§10](#10-video--spectator-mirror--recording-spectatorcamera--livekit)). |
| **Publisher** | *(empty)* | A reference to the `LiveKitPublisher` on your spectator-camera GameObject. Video needs its own `Camera`, so it lives on a separate object — you drag that object here. |

> The launcher only overwrites a sub-component's shared settings when its own field is filled in,
> so it never wipes out values you set directly on the bundled components.

**After steps 3–5** your project already connects to the backend and streams synthetic
behaviour/context data (so you can see something on the dashboard immediately). Sections 6–10 add
the real, useful capabilities.

---

## 6. Make objects adaptable (`ObjectStatus`)

An `ObjectStatus` component tells the backend "this object has a setting you can change." When a
rule fires, the backend sends a value and the package calls a function you wired in the Inspector
— with **no code required** for the basic case.

### Worked example: a campfire light the backend can dim

We'll make a light whose brightness the backend can set from 0–100.

1. **Pick or create the object.** In the **Hierarchy**, select your light (or create one:
   right-click ▸ **Light ▸ Directional Light**). It must have a **Light** component.
2. **Add the status.** With the light selected, in the **Inspector** click **Add Component**, type
   **"Object Status"**, press Enter.
3. **Fill in the ObjectStatus fields:**

   | Field (Inspector) | Set it to | Meaning |
   |---|---|---|
   | **Object Id** | leave empty | A unique name for this object. Empty = the GameObject's name is used. |
   | **Tags** | click **+**, add `ambient_light` | Labels rules can address this object by. A rule targeting a **tag** affects **every** object with that tag — this is what makes one rule work across many scenes. |
   | **Status Name** | `brightness` | The name of the setting as it appears in rules. |
   | **Type** | **Continuous** | `Continuous` = a number between Range Min/Max. (`Discrete` = one of a fixed list of words — see below.) |
   | **Range Min** | `0` | Smallest allowed value (Continuous only). |
   | **Range Max** | `100` | Largest allowed value (Continuous only). |

4. **Wire the value to the light's brightness (the UnityEvent).** Still on the light, find the
   **On Continuous Value (Single)** box on the ObjectStatus component:
   1. Click the small **+** at the bottom-right of that box. An empty row appears.
   2. Drag the **light GameObject** from the Hierarchy into the object slot of that row (the box
      that says *None (Object)*).
   3. Click the function dropdown (it says **No Function**). Choose **Light ▸ intensity**.
   4. **Important:** pick `intensity` from the **Dynamic float** section at the *top* of the
      dropdown (not the "Static Parameters" section). "Dynamic" means the live value from the
      backend is passed straight through; "Static" would always send a fixed number you type.

Now, when a rule sends `brightness = 20` to anything tagged `ambient_light`, the package sets the
light's `intensity` to `20`.

### Discrete statuses (a fixed set of words)

For a status that is one of several named states (e.g. a fire's crackle being `off` / `low` /
`high`):

1. Add another **Object Status** component (you can have several on one GameObject — see below).
2. Set **Status Name** = `crackle`, **Type** = **Discrete**.
3. Under **Discrete Values**, click **+** for each allowed word and type `off`, `low`, `high`.
4. Wire **On Discrete Value (String)** the same way as step 4 above, but to a function that takes
   a **string** (choose it from the **Dynamic string** section) — e.g. a method on your own audio
   script that switches the crackle sound.

### Field reference

| Field | Purpose |
|---|---|
| **Object Id** | Unique id in the backend's manifest. Empty → the GameObject's name. |
| **Tags** | Tags rules can target this object by. Tag targets fan out to every matching object. |
| **Status Name** | The status name used in rules (e.g. `brightness`, `density`). |
| **Type** | `Continuous` (a float in `[Range Min, Range Max]`) or `Discrete` (one of `Discrete Values`). |
| **Range Min / Range Max** | Allowed numeric range (Continuous only). |
| **Discrete Values** | Allowed state words (Discrete only). |
| **On Continuous Value (Single)** | UnityEvent called with the incoming `float` (Continuous). Wire it to the real effect. |
| **On Discrete Value (String)** | UnityEvent called with the incoming `string` (Discrete). |

> **Multiple statuses, one object:** add several `ObjectStatus` components to the same GameObject
> (e.g. `brightness` + `crackle` on the campfire). They're grouped under one object id with
> multiple statuses, so they appear together in the rule builder.

> **Driving from code instead of the Inspector:** if you'd rather not use UnityEvents, leave them
> empty and read the value yourself — but for most cases the Inspector wiring is enough. The
> package auto-discovers every `ObjectStatus` in the scene; you don't register them anywhere.

---

## 7. Expose commands (`VCoreAction`)

A `VCoreAction` is the command counterpart to a status: a **named, parameterless action** the
backend can trigger. Use it when "do this thing" fits better than "set this value" — e.g.
`advance_scene`, `extinguish`, `play_alarm`.

### Worked example: an "advance to next scene step" command

1. In the **Hierarchy**, select the GameObject that should own the command (or your
   **VCoreManager** for a global one).
2. **Add Component ▸ "VCore Action"**.
3. Fill in the fields:

   | Field (Inspector) | Set it to | Meaning |
   |---|---|---|
   | **Action Name** | `advance_scene` | The command name rules invoke. |
   | **Scope** | **Scene** | **Scene** = a global command with no target (addressed by name only). **Object** = addressed by this object's `Object Id`/`Tags`, like a status (and tag targets fan out to all matching objects). |
   | **Object Id** | *(Object scope only)* | Unique id; empty → GameObject name. |
   | **Tags** | *(Object scope only)* | Tags rules can address it by. |

4. **Wire what it does.** In the **On Invoke** box, click **+**, drag in the GameObject that holds
   the code you want to run, and pick the method from the dropdown (e.g. your `StudyManager ▸
   NextStep`). `On Invoke` is a plain UnityEvent, so you can call any public method, start a
   coroutine, trigger a Timeline, flip a state machine — anything.

In the dashboard's rule builder, actions appear on the **THEN** side as **`action`** (instead of
**`set`**). A Scene-scoped action is offered by name; an Object-scoped action is offered against
its id/tags.

---

## 8. Stream behaviour metrics (`BehaviourReporter` / `BehaviourMetric`)

Behaviour metrics are per-second numbers about the participant (response latency, idle time, task
accuracy…). The package streams them to the backend, which **merges them into the live signal
feed** — so they chart on the dashboard's **Behavioural** panel, can be used in rules, and are
recorded, exactly like a hardware sensor signal.

`BehaviourReporter` is added automatically by the launcher (toggle **Behaviour Metrics**). **Out
of the box it sends synthetic (fake, smoothly-sweeping) values**, so you'll see the channels on
the dashboard with zero extra setup. You then replace the fakes with real values when ready.

You declare channels in **two interchangeable ways** — use either or both (they're merged, and
duplicates by name are removed):

### Way 1 — Centralised list (quickest)

1. Select **VCoreManager** and find the **Behaviour Reporter** component.
2. Expand **Channels**. It comes pre-filled with a demo set (response latency, accuracy, etc.).
3. Edit the list: set the **Size** number to add/remove rows, then fill each row:

   | Channel field | Meaning |
   |---|---|
   | **Name** | Channel id used on the dashboard and in rules (e.g. `response_latency`). |
   | **Label** | Human-readable title shown on the dashboard card. Empty → the name. |
   | **Unit** | Unit text shown on the card (e.g. `s`, `%`, `/task`). |
   | **Min / Max** | Expected value range (used for the synthetic sweep and the chart scale). |
   | **Precision** | Decimal places sent to the dashboard. |

### Way 2 — Per-object (`BehaviourMetric`)

Put the declaration on the object that actually produces the metric:

1. Select that GameObject (e.g. a `PlayerHand`), **Add Component ▸ "Behaviour Metric"**.
2. Fill its fields:

   | Field | Meaning |
   |---|---|
   | **Metric Name** | Channel id. Empty → the GameObject's name. |
   | **Label** | Dashboard title. Empty → the name. |
   | **Unit** | Unit text. |
   | **Min / Max** | Expected range. |
   | **Precision** | Decimal places (0–6). |

The reporter scene-scans for these automatically (the same way object statuses are discovered),
so you don't register them anywhere.

### Sending real values (from your own scripts)

Until you supply a real value, each channel just sweeps its range synthetically (if **Generate
Synthetic Data** is on). To send real data:

```csharp
using UnityEngine;
using VCore;

public class MyStudyLogic : MonoBehaviour
{
    void Update()
    {
        // (A) Centralised channels — call SetMetric on the reporter:
        var reporter = Object.FindFirstObjectByType<BehaviourReporter>();
        reporter.SetMetric("response_latency", 9.2f); // overrides the synthetic sweep for this channel
        // reporter.ClearMetric("response_latency");   // revert this channel to synthetic

        // (B) Per-object channels — call Report on the BehaviourMetric component:
        var metric = GetComponent<BehaviourMetric>();
        metric.Report(84f);  // overrides synthetic for this metric
        // metric.Clear();    // revert to synthetic
    }
}
```

> **Send only real values:** on the **Behaviour Reporter**, untick **Generate Synthetic Data**.
> Channels with no reported value are then simply not sent.

### Reporter settings

| Field (on `BehaviourReporter`) | Default | Meaning |
|---|---|---|
| **Connection** | auto | The `VCoreConnection` to send through. Auto-filled from the same GameObject. |
| **Sample Interval** | `1` | Seconds between value updates (clamped to ≥ 0.1). |
| **Generate Synthetic Data** | `true` | Sweep each channel's range when no real value has been reported. |
| **Channels** | demo set | The centralised channel list (Way 1). |

---

## 9. Report study context (`VrContextReporter`)

VR context is free-form text about where the participant is in the study — scene, step,
instruction, items left, etc. The dashboard shows it in a **VR Context** panel. Keys are
free-form: whatever keys you send are displayed (snake_case keys become Title-Cased labels), so
any study can describe itself however it likes.

`VrContextReporter` is added by the launcher (toggle **Vr Context**) and, out of the box, walks a
built-in demo script of supermarket "steps" on a timer — so the panel shows something with no
setup.

### Editing the scripted steps (Inspector)

1. Select **VCoreManager**, find the **Vr Context Reporter** component.
2. Set **Auto Play** (ticked = walk through the steps automatically) and **Step Interval** (seconds
   between steps).
3. Expand **Steps**. Each step has a **Fields** list, and each field is a **Key**/**Value** pair.
   Set **Size** to add steps/fields, then type keys (`scene`, `step`, `instruction`, …) and their
   values. The dashboard renders whatever keys you put here.

### Sending real context (from your own scripts)

Drive it from gameplay (a trigger volume, a study manager…). Turn **Auto Play** off first so the
demo walk-through stops:

```csharp
using System.Collections.Generic;
using UnityEngine;
using VCore;

public class AisleTrigger : MonoBehaviour
{
    void OnTriggerEnter(Collider other)
    {
        var ctx = Object.FindFirstObjectByType<VrContextReporter>();
        ctx.autoPlay = false;  // stop the scripted demo walk-through
        ctx.ReportContext(new Dictionary<string, object> {
            ["scene"]       = "Aisle 3 – Dairy",
            ["step"]        = "3 / 4",
            ["instruction"] = "Find the cheese",
            ["items_left"]  = 1,
        });
    }
}
```

`ReportContext(...)` takes any `{key: value}` map. There's also `ReportStep(step)` if you'd
rather pass one of the Inspector `Step` entries.

| Field (on `VrContextReporter`) | Default | Meaning |
|---|---|---|
| **Connection** | auto | The `VCoreConnection` to send through. |
| **Auto Play** | `true` | Walk through **Steps** automatically on a timer (synthetic). |
| **Step Interval** | `6` | Seconds between automatic steps (clamped to ≥ 0.5). |
| **Steps** | demo set | The scripted steps used while Auto Play is on. |

---

## 10. Video — spectator mirror + recording (`SpectatorCamera` + LiveKit)

This streams a "spectator" camera (what the participant sees) to the researcher's dashboard, and
lets the backend record it server-side, time-synced to the signals. It's **optional** — skip this
section if you don't need video.

### Step 1 — Install the LiveKit SDK

The publisher only compiles when the LiveKit Unity SDK is present, so add it first:

1. **Window ▸ Package Manager ▸ + ▸ Add package from git URL…**
2. Paste: `https://github.com/livekit/client-sdk-unity.git`
3. Click **Add** and wait for Unity to import it.

Installing the SDK switches on a compiler flag (`VCORE_LIVEKIT`) that enables the
`LiveKitPublisher` script. *(Without the SDK the package still compiles fine — video just isn't
available, and `LiveKitPublisher` won't exist as a component.)*

### Step 2 — Build the spectator-camera rig

Video needs its own `Camera`, so it lives on a separate GameObject from VCoreManager:

1. In the **Hierarchy**, right-click ▸ **Create Empty**, rename it **SpectatorCamera**.
2. **Add Component ▸ "Spectator Camera"**. This requires a `Camera`, so Unity adds one
   automatically. (It renders to an off-screen texture, not to the player's display.)
3. **Add Component ▸ "LiveKit Publisher"**. (It requires `SpectatorCamera`, already present.)

**`SpectatorCamera` fields:**

| Field | Default | Meaning |
|---|---|---|
| **Width / Height** | `1920` / `1080` | Resolution of the streamed image. |
| **Follow Target** | *(empty)* | In VR, drag your HMD/head camera here so the spectator view mirrors head movement. Leave empty for a fixed camera. |
| **Position Offset** | `0,0,0` | A world-space offset added on top of the followed pose. |

### Step 3 — Wire it to the launcher

1. **LiveKitPublisher** has a **Backend Config** field — drag your `BackendConfig` asset onto it
   (or rely on the launcher to push it).
2. Select **VCoreManager**, and on **VCoreLauncher** drag the **SpectatorCamera** GameObject into
   the **Publisher** field. Keep **Video Publishing** ticked.

**`LiveKitPublisher` fields:** **Backend Config** (token source), **Host**/**Port** (fallback only,
used when no Backend Config is set), and **Identity** (the name this publisher registers under in
the LiveKit room — default `unity`).

### Step 4 — Run

On Play, the publisher fetches an access token from the backend (`…/api/livekit/token`), connects
to the LiveKit server, and publishes the camera. The dashboard subscribes to show the live mirror;
recording is **server-side** (the backend starts/stops it automatically with the session).

> The LiveKit **server** (the SFU + the recorder, and the one `node_ip` value you must set per
> machine) is a backend/ops concern, covered in
> [`docs/LIVEKIT_SETUP.md`](../../../docs/LIVEKIT_SETUP.md). You don't call anything from Unity to
> record — it's fully automatic.

---

## 11. Author rules ahead of time — the project catalog

The backend normally only knows about objects/actions in the scene that's **currently loaded**. If
you want to write rules in the dashboard for objects that live in scenes you haven't opened yet,
bake a **project catalog**:

1. In the top menu, click **V-CORE ▸ Bake Project Catalog**.
2. This scans **every scene in your Build Settings** *and* **every prefab** for `ObjectStatus` and
   `VCoreAction` components, and writes the result to `Assets/Resources/VCoreCatalog.json`.
3. On the next connect, the client sends this catalog to the backend, so the rule builder can
   target everything your project *could* expose — not just what's loaded right now.

It also re-bakes **automatically every time you make a player build**, so a shipped build always
carries an up-to-date catalog. A rule that targets an object in an unloaded scene simply stays
dormant until that scene loads, then activates.

> Re-run **Bake Project Catalog** by hand whenever you add/rename objects or actions and want the
> rule builder to see them before loading their scene.

---

## 12. Multi-scene sessions

With **Persist Across Scenes** ticked on the launcher (the default), the **VCoreManager** survives
Unity scene loads (via `DontDestroyOnLoad`), with a guard that destroys any duplicate a freshly
loaded scene might bring in. So **one V-CORE session spans many Unity scenes**.

This gives you two natural scopes:

- **Session-scoped** (lives for the whole session): channels on the persistent reporter, or a
  `BehaviourMetric` on the manager itself.
- **Scene-scoped** (comes and goes with a scene): a `BehaviourMetric` or `ObjectStatus` on a scene
  object. On each scene load/unload the client re-scans, re-sends the object manifest, and rebuilds
  its dispatch index — so adaptations always resolve against whatever is actually loaded.

---

## 13. Verify it works

1. Start your V-CORE backend (and the dashboard).
2. Press **▶ Play** in Unity.
3. Open the **Console** (**Window ▸ General ▸ Console**). You should see, in order:

   ```
   [VCore] Connecting → ws://localhost:8000/ws/runtime
   [VCore] Connected to V-CORE
   [Dispatcher] Index built: N object(s), M tag(s), K action target(s)
   ```

   (With video, you'll also see `[LiveKit] connected → …` and `[LiveKit] publishing spectator
   camera`.)

4. Open the dashboard (default `http://localhost:5173`) → **Rule Manager ▸ New Rule**. Your objects
   and their statuses/actions appear on the **THEN** side, and your behaviour channels appear on
   the dashboard's panels.
5. Create a rule that targets one of your objects, trigger its condition, and watch the wired
   effect happen in the Unity scene (and the `[Dispatcher]` log line confirming it).

> The client sends its object manifest **before** it reports "connected", so the reporters always
> arrive after the handshake. It re-sends the manifest and rebuilds its dispatch index on every
> scene load/unload, so adaptations always resolve against the live scene.

---

## 14. Assemblies & how the package is structured

The package is split into three assemblies so the optional video dependency stays isolated:

- **`VCore.Client`** — the core: the connection, the object-status send/receive loop, the
  behaviour/context reporters, the spectator camera, the launcher, and the
  `VCoreVideoPublisher` base class. Depends only on Newtonsoft.Json.
- **`VCore.Client.LiveKit`** — just `LiveKitPublisher`, guarded so it compiles **only when the
  LiveKit SDK is installed**. The package builds with or without the SDK.
- **`VCore.Client.Editor`** — the **Add to Scene** menu, the catalog baker, and the build hook
  (Editor-only; not included in your game build).

The runtime scripts live in `Packages/com.vcore.client/Runtime/` (namespace `VCore`), **not** in
your `Assets/` folder — that's normal for a package.

---

## 15. Troubleshooting

| Symptom | What to check |
|---|---|
| Console shows `[VCore] Connect failed` (or it never connects) | Is the backend running? Is the `BackendConfig` **Host**/**Port** correct? For a backend on another machine, Host must be that machine's **LAN IP**, not `localhost`. |
| `[Dispatcher] No object with tag '…'` | The tag the rule targets isn't on any `ObjectStatus` in the loaded scene. Add the tag, or the rule will show as disabled in the dashboard. |
| Your objects don't appear in the rule builder | Is there a `VCoreLauncher` in the scene? Did the Console show the connect + `Index built` lines? For unloaded scenes, run **V-CORE ▸ Bake Project Catalog** ([§11](#11-author-rules-ahead-of-time--the-project-catalog)). |
| The wired effect doesn't happen when a rule fires | In the `ObjectStatus` UnityEvent, did you pick the function under **Dynamic float**/**Dynamic string** (top of the dropdown), not the Static section? Static sends a fixed value, ignoring the backend's. |
| Behaviour channels / VR context don't show on the dashboard | Are **Behaviour Metrics** / **Vr Context** ticked on the launcher? Are they enabled per `livekit`/dashboard config on the backend? Check the Console for connect logs. |
| Compiler error mentioning `LiveKit` or `Unity.WebRTC` types | The LiveKit SDK isn't installed/resolved. Add `io.livekit.livekit-sdk` ([§10](#10-video--spectator-mirror--recording-spectatorcamera--livekit)); the publisher is guarded by the `VCORE_LIVEKIT` flag. |
| Compiler error mentioning `Newtonsoft.Json` | Let the Package Manager finish resolving the auto-added dependency (watch the bottom status bar). |
| Scene opens with missing-script (yellow ⚠) references | Unity hasn't finished importing the package yet — wait for the Package Manager + asset reimport to complete. The scripts live in `Packages/com.vcore.client/Runtime/`, not `Assets/`. |

---

## 16. See also

- [`../../README.md`](../../README.md) — the **POC**: a ready-made Sample scene that wires all of
  the above (the campfire example, in a working project you can open and press Play).
- [`../../../docs/HOW_IT_WORKS.md`](../../../docs/HOW_IT_WORKS.md) — how the whole V-CORE system
  fits together (backend, dashboard, contracts).
- [`../../../docs/LIVEKIT_SETUP.md`](../../../docs/LIVEKIT_SETUP.md) — the video server (LiveKit +
  recording) setup.
- [`../../../contracts/`](../../../contracts) — the language-neutral JSON-Schema contracts this
  client speaks.
