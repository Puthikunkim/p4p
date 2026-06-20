using System;
using System.Collections;
using System.Collections.Generic;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace VCore
{
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
        [Tooltip("Shared backend address. When assigned it overrides the host/port below, so every " +
                 "V-CORE component points at the same backend.")]
        public BackendConfig backendConfig;

        [Tooltip("Fallback hostname or IP, used only when no Backend Config asset is assigned.")]
        public string host = "localhost";
        [Tooltip("Fallback port, used only when no Backend Config asset is assigned.")]
        public int port = 8000;

        private string ResolvedHost => backendConfig != null ? backendConfig.host : host;
        private int ResolvedPort => backendConfig != null ? backendConfig.port : port;

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

        void Start()
        {
            // Re-handshake on scene changes so adaptation targets track the live scene.
            SceneManager.sceneLoaded += OnSceneLoaded;
            SceneManager.sceneUnloaded += OnSceneUnloaded;
            StartCoroutine(ConnectLoop());
        }

        private void OnSceneLoaded(Scene scene, LoadSceneMode mode) => ResyncScene();
        private void OnSceneUnloaded(Scene scene) => ResyncScene();

        // Re-index the dispatcher for the new scene's objects and re-send the typed
        // object-status manifest so the backend re-resolves targets against it too.
        private void ResyncScene()
        {
            if (!IsConnected) return;
            _dispatcher.RebuildIndex();
            Send(_collector.BuildManifestEnvelopeJson());
        }

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
            SceneManager.sceneLoaded -= OnSceneLoaded;
            SceneManager.sceneUnloaded -= OnSceneUnloaded;
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

            var uri = new Uri($"ws://{ResolvedHost}:{ResolvedPort}/ws/runtime");
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
            var manifestTask = SendRawAsync(_collector.BuildManifestEnvelopeJson());
            yield return new WaitUntil(() => manifestTask.IsCompleted);
            IsConnected = true;

            // After the manifest handshake, send the project-wide catalog (if it was baked
            // via "V-CORE ▸ Bake Project Catalog") so the dashboard can author rules against
            // objects/actions in scenes that aren't loaded yet.
            var catalogEnvelope = BuildCatalogEnvelope();
            if (catalogEnvelope != null)
            {
                var catalogTask = SendRawAsync(catalogEnvelope);
                yield return new WaitUntil(() => catalogTask.IsCompleted);
            }

            // Receive loop runs on a thread pool thread; results are queued back to
            // the main thread via _inbound.
            _ = Task.Run(ReceiveLoop, _cts.Token);

            yield return new WaitUntil(
                () => _ws.State != WebSocketState.Open || _cts.IsCancellationRequested);

            _cts.Cancel();
            _ws.Dispose();
            Debug.Log("[VCore] Connection closed");
        }

        // Wrap the baked catalog (Resources/VCoreCatalog.json, the manifest-shaped payload)
        // in its typed envelope, or null if no catalog has been baked.
        private static string BuildCatalogEnvelope()
        {
            var asset = Resources.Load<TextAsset>("VCoreCatalog");
            if (asset == null || string.IsNullOrEmpty(asset.text)) return null;
            return "{\"type\":\"object_status_catalog\",\"payload\":" + asset.text + "}";
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
}
