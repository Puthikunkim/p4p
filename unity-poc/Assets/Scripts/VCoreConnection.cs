using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;

/// <summary>
/// WebSocket client that connects to V-CORE <c>/ws/runtime</c>.
///
/// On connect it sends the Object-Status Manifest (Contract 3b) built by
/// <see cref="StatusCollector"/>, then listens for Status-Change Requests
/// (Contract 3a) and hands them to <see cref="RequestDispatcher"/> on the
/// Unity main thread.
///
/// Reconnects automatically with exponential back-off.
/// </summary>
[RequireComponent(typeof(StatusCollector))]
[RequireComponent(typeof(RequestDispatcher))]
public class VCoreConnection : MonoBehaviour
{
    [Header("Connection")]
    [Tooltip("Hostname or IP of the V-CORE backend (Machine A).")]
    public string host = "localhost";
    public int port = 8000;

    [Header("Reconnect")]
    [Tooltip("Seconds to wait before the first reconnect attempt.")]
    public float initialReconnectDelay = 1f;
    [Tooltip("Upper bound on reconnect delay (seconds).")]
    public float maxReconnectDelay = 30f;

    // ── state ───────────────────────────────────────────────────────────────────
    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private StatusCollector _collector;
    private RequestDispatcher _dispatcher;

    private readonly Queue<string> _inbound = new();
    private readonly object _inboundLock = new();

    /// <summary>True while the WebSocket connection to V-CORE is open.</summary>
    public bool IsConnected { get; private set; }

    // ── lifecycle ───────────────────────────────────────────────────────────────

    void Awake()
    {
        _collector = GetComponent<StatusCollector>();
        _dispatcher = GetComponent<RequestDispatcher>();
    }

    void Start() => StartCoroutine(ConnectLoop());

    void Update()
    {
        // Drain the thread-safe inbound queue on the main thread so
        // RequestDispatcher can safely call Unity API.
        lock (_inboundLock)
        {
            while (_inbound.Count > 0)
                _dispatcher.OnRequest(_inbound.Dequeue());
        }
    }

    void OnDestroy()
    {
        _cts?.Cancel();
        _ws?.Dispose();
    }

    // ── connection loop ─────────────────────────────────────────────────────────

    private IEnumerator ConnectLoop()
    {
        float delay = initialReconnectDelay;
        while (true)
        {
            yield return StartCoroutine(RunConnection());
            IsConnected = false;
            Debug.LogWarning($"[VCore] Disconnected. Reconnecting in {delay:F1} s…");
            yield return new WaitForSeconds(delay);
            delay = Mathf.Min(delay * 2f, maxReconnectDelay);
        }
    }

    private IEnumerator RunConnection()
    {
        _cts = new CancellationTokenSource();
        _ws = new ClientWebSocket();

        var uri = new Uri($"ws://{host}:{port}/ws/runtime");
        Debug.Log($"[VCore] Connecting → {uri}");

        var connectTask = _ws.ConnectAsync(uri, _cts.Token);
        yield return new WaitUntil(() => connectTask.IsCompleted);

        if (connectTask.IsFaulted || _ws.State != WebSocketState.Open)
        {
            Debug.LogError($"[VCore] Connect failed: {connectTask.Exception?.GetBaseException().Message}");
            _ws.Dispose();
            yield break;
        }

        IsConnected = true;
        Debug.Log("[VCore] Connected to V-CORE");

        // Send the manifest on the background thread; fire-and-forget is fine
        // here because the send path serialises through the WS protocol.
        _ = SendRawAsync(_collector.BuildManifestJson());

        // Receive loop runs on a thread pool thread; results are queued back to
        // the main thread via _inbound.
        _ = Task.Run(ReceiveLoop, _cts.Token);

        yield return new WaitUntil(
            () => _ws.State != WebSocketState.Open || _cts.IsCancellationRequested);

        _cts.Cancel();
        _ws.Dispose();
        Debug.Log("[VCore] Connection closed");
    }

    // ── send / receive ──────────────────────────────────────────────────────────

    private async Task SendRawAsync(string json)
    {
        if (_ws == null || _ws.State != WebSocketState.Open) return;
        try
        {
            var bytes = Encoding.UTF8.GetBytes(json);
            await _ws.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                endOfMessage: true,
                _cts.Token);
        }
        catch (Exception ex) when (ex is OperationCanceledException or WebSocketException)
        {
            // Connection is closing — swallow; the coroutine loop will reconnect.
        }
    }

    private async Task ReceiveLoop()
    {
        var buffer = new byte[65536];
        while (_ws.State == WebSocketState.Open && !_cts.IsCancellationRequested)
        {
            try
            {
                var sb = new StringBuilder();
                WebSocketReceiveResult result;
                do
                {
                    result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                    if (result.MessageType == WebSocketMessageType.Close) return;
                    sb.Append(Encoding.UTF8.GetString(buffer, 0, result.Count));
                }
                while (!result.EndOfMessage);

                lock (_inboundLock)
                    _inbound.Enqueue(sb.ToString());
            }
            catch (OperationCanceledException) { break; }
            catch (WebSocketException) { break; }
            catch (Exception ex)
            {
                Debug.LogError($"[VCore] Receive error: {ex.Message}");
                break;
            }
        }
    }
}
