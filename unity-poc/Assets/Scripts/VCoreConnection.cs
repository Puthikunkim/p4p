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

    [Header("Lifetime")]
    [Tooltip("Keep this manager (connection + reporters) alive across scene loads so a " +
             "session can span multiple scenes. A singleton guard destroys duplicates.")]
    public bool persistAcrossScenes = true;

    // ── state ───────────────────────────────────────────────────────────────────
    private static VCoreConnection _instance;
    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private StatusCollector _collector;
    private RequestDispatcher _dispatcher;

    private readonly Queue<string> _inbound = new();
    private readonly object _inboundLock = new();
    private readonly SemaphoreSlim _sendLock = new(1, 1);

    /// <summary>True while the WebSocket connection to V-CORE is open.</summary>
    public bool IsConnected { get; private set; }

    // ── lifecycle ───────────────────────────────────────────────────────────────

    void Awake()
    {
        if (persistAcrossScenes)
        {
            if (_instance != null && _instance != this)
            {
                Debug.LogWarning("[VCore] Duplicate VCoreConnection in a new scene — destroying it; " +
                                 "the persistent one keeps the session alive.");
                Destroy(gameObject);
                return;
            }
            _instance = this;
            DontDestroyOnLoad(gameObject);
        }

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
        if (_instance == this) _instance = null;
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

        Debug.Log("[VCore] Connected to V-CORE");

        // The backend treats the first message on this socket as the Object-Status
        // Manifest handshake, so flush it before marking the link ready. Reporter
        // components gate their messages on IsConnected, so this guarantees the
        // manifest is always the first frame on the wire.
        var manifestTask = SendRawAsync(_collector.BuildManifestJson());
        yield return new WaitUntil(() => manifestTask.IsCompleted);
        IsConnected = true;

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

    /// <summary>
    /// Send a raw JSON message to V-CORE. Safe to call from the main thread by
    /// reporter components (e.g. VrContextReporter, BehaviourReporter); sends are
    /// serialised so concurrent callers never overlap on the socket.
    /// </summary>
    public void Send(string json) => _ = SendRawAsync(json);

    private async Task SendRawAsync(string json)
    {
        var ws = _ws;
        if (ws == null || ws.State != WebSocketState.Open) return;

        // ClientWebSocket permits only one outstanding SendAsync at a time, so
        // serialise the manifest send and every reporter send through a lock.
        await _sendLock.WaitAsync();
        try
        {
            if (ws.State != WebSocketState.Open) return;
            var bytes = Encoding.UTF8.GetBytes(json);
            await ws.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                endOfMessage: true,
                _cts.Token);
        }
        catch (Exception ex) when (ex is OperationCanceledException or WebSocketException)
        {
            // Connection is closing — swallow; the coroutine loop will reconnect.
        }
        finally
        {
            _sendLock.Release();
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
