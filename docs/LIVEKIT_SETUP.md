# LiveKit Video Setup & Runbook

How to run the participant-video plane (live mirror + server-side recording) and
**what to change for your network**. The signal/rule plane is unaffected by all of this.

> **Architecture in one line:** Unity publishes its spectator camera to a **LiveKit**
> server (the SFU); the browser dashboard subscribes for the live mirror; **LiveKit Track
> Egress** records the published camera track to a **`.webm`** on disk; **V-CORE** only mints
> access tokens and starts/stops the recording (it never touches the media bytes). Recording is
> anchored to the LSL clock at egress start and stop, so the `.webm` lines up with the signal data.

---

## 1. The one value you must set: your LAN IP

LiveKit advertises an IP for the actual media (WebRTC/UDP). It must be reachable by **both**
the host-side clients (Unity, browser) **and** the in-container Egress. The only address that
satisfies both is your **machine's LAN IP** — not `localhost` (breaks Egress) and not the
container IP (breaks host clients).

**Find your LAN IP (Windows PowerShell):**

```powershell
Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null } |
  Select-Object InterfaceAlias, @{n='LAN_IP';e={$_.IPv4Address.IPAddress}}
```

Pick the entry for your real adapter (Wi-Fi / Ethernet), **not** a `vEthernet`/WSL/Docker one.

**Set it** in [`livekit/livekit.yaml`](../livekit/livekit.yaml) under `rtc.node_ip`:

```yaml
rtc:
  node_ip: 192.168.68.113   # ← your LAN IP (currently set to this dev machine's)
```

> Change this whenever your machine or network changes (DHCP can reassign Wi-Fi IPs).

---

## 2. Enable LiveKit

LiveKit is **off by default** so the rest of the system runs without it. Turn it on with either:

- `backend/config.yaml` → `livekit.enabled: true`, **or**
- env `LIVEKIT_ENABLED=true` on the backend.

When disabled, the dashboard simply shows no mirror (the token endpoint returns `409`) and the
app otherwise works normally.

---

## 3. Run it (all-in-Docker)

```powershell
docker compose build backend     # picks up the livekit-api dependency
docker compose up                # backend, frontend, livekit, egress, redis
```

Then open the dashboard at **http://localhost:5173**.

Ports the host exposes (open these in the firewall for cross-machine use):

| Port | Service |
|------|---------|
| 8000 | backend (REST + WebSockets) |
| 5173 | frontend (Vite dev server) |
| 7880 | LiveKit signaling + server API |
| 7881 | LiveKit RTC over TCP (fallback) |
| 7882/udp | LiveKit RTC media (single port; avoids the Windows-reserved 50000+ range) |

Recordings land in `backend/data/video/<session_id>.webm` (Egress writes via a shared volume).

---

## 4. What to change per topology

The golden rule: **use the Docker host's LAN IP everywhere** and the same config works in both
layouts. `localhost` only works for same-machine signaling — never for cross-machine, never for
Egress media.

### A. Unity on the **same machine** as Docker (current dev setup)
- `livekit/livekit.yaml` → `rtc.node_ip: <your-LAN-IP>` (required, because of Egress).
- Unity `BackendConfig` → `host = localhost`, `port = 8000`.
- Nothing else to change; the token URL `ws://localhost:7880` works for host clients.

### B. Unity on a **different machine** (Docker host = Machine 1)
- `livekit/livekit.yaml` → `rtc.node_ip: <Machine-1-LAN-IP>`.
- Backend env (docker-compose) → `LIVEKIT_URL=ws://<Machine-1-LAN-IP>:7880` (so the token tells
  Unity/browser where to connect).
- Unity `BackendConfig` → `host = <Machine-1-LAN-IP>`, `port = 8000`.
- Browser → open `http://<Machine-1-LAN-IP>:5173`.
- Open the firewall ports above on Machine 1; Unity and Machine 1 must be on the **same subnet**
  (also required for the LSL sensor stream).

---

## 5. Secrets

Dev key/secret (`devkey` / `devsecret…`) live in `livekit/livekit.yaml`, `livekit/egress.yaml`,
and the backend env. **Change them for any real/shared deployment** and override the backend via
env (`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`) rather than committing real secrets.

---

## 6. Verify

```powershell
# LiveKit + Egress came up clean:
docker compose logs livekit egress
# Token endpoint works (requires livekit.enabled = true):
curl "http://localhost:8000/api/livekit/token?identity=test&role=subscriber"   # → {token,url,room}
```

Then start a session in the dashboard and confirm: the **Video Mirror** shows the Unity view,
and on stop, `backend/data/video/<session_id>.webm` exists.

---

## 7. Unity POC publisher (LiveKit)

The POC publishes its spectator camera to LiveKit via
[`LiveKitPublisher.cs`](../unity-poc/Packages/com.vcore.client/Runtime/LiveKit/LiveKitPublisher.cs)
(in the `com.vcore.client` package; the `VCore` prefab / `VCoreLauncher` wires it for you). In the editor:

1. **Install the LiveKit Unity SDK.** It's referenced in
   [`Packages/manifest.json`](../unity-poc/Packages/manifest.json) as
   `"io.livekit.livekit-sdk": "https://github.com/livekit/client-sdk-unity.git"`. If Unity still
   reports a package-name mismatch (the SDK's package name can change between versions), use the
   exact name from the error, or add it from the UI — **Window → Package Manager → + → Add
   package from git URL →** `https://github.com/livekit/client-sdk-unity.git` (Unity then writes
   the correct package key automatically).
2. **Reconcile WebRTC.** The SDK brings its own WebRTC dependency; if it conflicts with the
   existing `com.unity.webrtc` (3.0.0-pre.8), let the LiveKit SDK's required version win.
3. **Wire the component.** The `VCore` prefab already carries **LiveKitPublisher** on the
   `SpectatorCamera` object — just assign the **Backend Config** asset. (The old `WebRtcSender`
   has been removed from the project.)
4. **Enable + run.** Set `livekit.enabled: true`, `docker compose up`, press Play. The token is
   fetched from `/api/livekit/token`; video should appear in the dashboard's Video Mirror.
5. **Cross-machine:** also set the publisher's `BackendConfig.host` to the Docker host's LAN IP
   (see §4B) so Unity can reach both the token endpoint and LiveKit.

> The publisher has been verified publishing end-to-end against the LiveKit Unity SDK
> (continuous frames to the SFU). If you bump the SDK version, re-check its API surface against
> the file.

## 8. Status

- [x] Backend: token endpoint + Track-Egress orchestration (LSL-anchored), gated by `livekit.enabled`.
- [x] docker-compose: LiveKit + Egress + Redis.
- [x] Frontend: `livekit-client` subscriber (live mirror).
- [x] Unity POC: `LiveKitPublisher.cs` (in the `com.vcore.client` package) + SDK manifest entry —
      verified publishing end-to-end.
- [x] Legacy path removed: the old `WebRtcSender` / `VideoRecorder`, the backend `SignalingBroker`
      / `/ws/signaling`, and the browser-upload video endpoints are gone.
