using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Unity.WebRTC;
using UnityEngine;

/// <summary>
/// Streams the <see cref="SpectatorCamera"/> view to the researcher's dashboard
/// via WebRTC (Amendment 2).
///
/// Protocol
/// --------
/// 1. Connects to V-CORE <c>/ws/signaling</c> as the publisher peer.
/// 2. V-CORE brokers SDP offer/answer + ICE candidates with the browser.
/// 3. Video flows peer-to-peer Unity → browser; V-CORE never relays media.
///
/// Requires: <c>com.unity.webrtc</c> package (add via Package Manager or
/// <c>Packages/manifest.json</c>).
/// </summary>
[RequireComponent(typeof(SpectatorCamera))]
public class WebRtcSender : MonoBehaviour
{
    [Header("Signaling")]
    [Tooltip("Hostname or IP of the V-CORE backend (same as VCoreConnection.host).")]
    public string host = "localhost";
    public int port = 8000;

    [Header("ICE")]
    [Tooltip("STUN/TURN servers. Default works on a LAN without NAT traversal.")]
    public string[] iceServerUrls = { "stun:stun.l.google.com:19302" };

    // ── private ──────────────────────────────────────────────────────────────────
    private SpectatorCamera _cam;
    private RTCPeerConnection _pc;
    private VideoStreamTrack _videoTrack;

    private ClientWebSocket _sigWs;
    private CancellationTokenSource _cts;

    // Thread-safe queues bridging the async receive loop ↔ coroutine dispatch.
    private readonly Queue<string> _sigInbound = new();
    private readonly object _sigLock = new();

    // Outbound signaling messages are written from coroutines (main thread) and
    // sent by the background send task.
    private readonly Queue<string> _sigOutbound = new();
    private readonly object _sigOutLock = new();

    // ── lifecycle ────────────────────────────────────────────────────────────────

    void Awake() => _cam = GetComponent<SpectatorCamera>();

    void Start()
    {
        // com.unity.webrtc requires this coroutine to be running.
        StartCoroutine(WebRTC.Update());
        StartCoroutine(ConnectSignaling());
    }

    void Update()
    {
        lock (_sigLock)
        {
            while (_sigInbound.Count > 0)
                HandleSignalingMessage(_sigInbound.Dequeue());
        }
    }

    void OnDestroy()
    {
        _cts?.Cancel();
        _videoTrack?.Dispose();
        _pc?.Dispose();
        _sigWs?.Dispose();
    }

    // ── signaling connection ──────────────────────────────────────────────────────

    private IEnumerator ConnectSignaling()
    {
        _cts = new CancellationTokenSource();
        _sigWs = new ClientWebSocket();

        var uri = new Uri($"ws://{host}:{port}/ws/signaling");
        Debug.Log($"[WebRTC] Connecting signaling → {uri}");

        var connectTask = _sigWs.ConnectAsync(uri, _cts.Token);
        yield return new WaitUntil(() => connectTask.IsCompleted);

        if (connectTask.IsFaulted || _sigWs.State != WebSocketState.Open)
        {
            Debug.LogError("[WebRTC] Signaling connect failed — video unavailable");
            yield break;
        }

        Debug.Log("[WebRTC] Signaling connected");

        // Register as publisher (first message; broker replies with registered).
        QueueSignaling(new { role = "publisher" });

        // Background send + receive loops.
        _ = Task.Run(SignalingReceiveLoop, _cts.Token);
        _ = Task.Run(SignalingSendLoop, _cts.Token);

        // Set up the peer connection and add the video track.
        CreatePeerConnection();
    }

    // ── peer connection ───────────────────────────────────────────────────────────

    private void CreatePeerConnection()
    {
        var servers = new RTCIceServer[iceServerUrls.Length];
        for (var i = 0; i < iceServerUrls.Length; i++)
            servers[i] = new RTCIceServer { urls = new[] { iceServerUrls[i] } };

        var config = new RTCConfiguration { iceServers = servers };
        _pc = new RTCPeerConnection(ref config);

        _pc.OnIceCandidate = candidate =>
        {
            if (candidate == null) return;
            QueueSignaling(new
            {
                type = "ice",
                candidate = candidate.Candidate,
                sdpMid = candidate.SdpMid,
                sdpMLineIndex = candidate.SdpMLineIndex,
            });
        };

        _pc.OnIceConnectionChange = state =>
            Debug.Log($"[WebRTC] ICE state → {state}");

        _pc.OnConnectionStateChange = state =>
            Debug.Log($"[WebRTC] Connection state → {state}");

        // Add the spectator-camera render texture as a video track.
        _videoTrack = new VideoStreamTrack(_cam.RT);
        _pc.AddTrack(_videoTrack);

        StartCoroutine(CreateAndSendOffer());
    }

    private IEnumerator CreateAndSendOffer()
    {
        var offerOp = _pc.CreateOffer();
        yield return offerOp;

        if (offerOp.IsError)
        {
            Debug.LogError($"[WebRTC] CreateOffer failed: {offerOp.Error.message}");
            yield break;
        }

        var desc = offerOp.Desc;
        var setLocalOp = _pc.SetLocalDescription(ref desc);
        yield return setLocalOp;

        if (setLocalOp.IsError)
        {
            Debug.LogError($"[WebRTC] SetLocalDescription failed: {setLocalOp.Error.message}");
            yield break;
        }

        QueueSignaling(new { type = "offer", sdp = desc.sdp });
        Debug.Log("[WebRTC] SDP offer sent");
    }

    // ── signaling message handling (main thread) ──────────────────────────────────

    private void HandleSignalingMessage(string json)
    {
        JObject msg;
        try { msg = JObject.Parse(json); }
        catch { Debug.LogWarning($"[WebRTC] Bad signaling JSON: {json}"); return; }

        var type = msg["type"]?.ToString();
        switch (type)
        {
            case "registered":
                Debug.Log($"[WebRTC] Registered as publisher (peer_id={msg["peer_id"]})");
                break;

            case "answer":
                var sdp = msg["sdp"]?.ToString();
                if (sdp != null)
                {
                    var desc = new RTCSessionDescription { type = RTCSdpType.Answer, sdp = sdp };
                    StartCoroutine(SetRemoteDescription(desc));
                }
                break;

            case "ice":
                var init = new RTCIceCandidateInit
                {
                    candidate      = msg["candidate"]?.ToString(),
                    sdpMid         = msg["sdpMid"]?.ToString(),
                    sdpMLineIndex  = msg["sdpMLineIndex"]?.ToObject<int?>(),
                };
                _pc?.AddIceCandidate(new RTCIceCandidate(init));
                break;

            case "publisher-gone":
            case "subscriber-gone":
                break; // no action needed — broker just informs us

            default:
                Debug.Log($"[WebRTC] Unhandled signaling type: {type}");
                break;
        }
    }

    private IEnumerator SetRemoteDescription(RTCSessionDescription desc)
    {
        var op = _pc.SetRemoteDescription(ref desc);
        yield return op;
        if (op.IsError)
            Debug.LogError($"[WebRTC] SetRemoteDescription failed: {op.Error.message}");
        else
            Debug.Log("[WebRTC] Remote description set — video stream active");
    }

    // ── signaling send / receive (background threads) ─────────────────────────────

    private void QueueSignaling(object payload)
    {
        var json = JsonConvert.SerializeObject(payload);
        lock (_sigOutLock)
            _sigOutbound.Enqueue(json);
    }

    private async Task SignalingSendLoop()
    {
        while (_sigWs.State == WebSocketState.Open && !_cts.IsCancellationRequested)
        {
            string[] batch;
            lock (_sigOutLock)
            {
                batch = _sigOutbound.Count > 0 ? _sigOutbound.ToArray() : Array.Empty<string>();
                _sigOutbound.Clear();
            }

            foreach (var json in batch)
            {
                try
                {
                    var bytes = Encoding.UTF8.GetBytes(json);
                    await _sigWs.SendAsync(
                        new ArraySegment<byte>(bytes),
                        WebSocketMessageType.Text,
                        endOfMessage: true,
                        _cts.Token);
                }
                catch (Exception ex) when (ex is OperationCanceledException or WebSocketException)
                {
                    return;
                }
            }

            await Task.Delay(16, _cts.Token); // ~60 Hz drain
        }
    }

    private async Task SignalingReceiveLoop()
    {
        var buffer = new byte[16384];
        while (_sigWs.State == WebSocketState.Open && !_cts.IsCancellationRequested)
        {
            try
            {
                var sb = new StringBuilder();
                WebSocketReceiveResult result;
                do
                {
                    result = await _sigWs.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                    if (result.MessageType == WebSocketMessageType.Close) return;
                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                }
                while (!result.EndOfMessage);

                lock (_sigLock)
                    _sigInbound.Enqueue(sb.ToString());
            }
            catch (OperationCanceledException) { break; }
            catch (WebSocketException) { break; }
            catch (Exception ex)
            {
                Debug.LogError($"[WebRTC] Signaling receive error: {ex.Message}");
                break;
            }
        }
    }
}
