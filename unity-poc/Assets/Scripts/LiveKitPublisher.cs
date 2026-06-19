using System.Collections;
using LiveKit;
using LiveKit.Proto;
using Newtonsoft.Json.Linq;
using UnityEngine;
using UnityEngine.Networking;

namespace VCore
{
    /// <summary>
    /// Publishes the <see cref="SpectatorCamera"/> view to a LiveKit room (the media
    /// plane), replacing the old custom-WebRTC <c>WebRtcSender</c>. V-CORE only mints
    /// the access token; the browser dashboard subscribes for the live mirror and
    /// LiveKit Egress records the room server-side.
    ///
    /// Flow: GET a publisher token from V-CORE (<c>/api/livekit/token</c>) → connect to
    /// the LiveKit room at the URL the token carries → publish the spectator render
    /// texture as a video track.
    ///
    /// ── Note ───────────────────────────────────────────────────────────────────────
    /// API matched to the LiveKit Unity SDK package <c>io.livekit.livekit-sdk</c>
    /// (github.com/livekit/client-sdk-unity); it compiles against that SDK. Not yet
    /// runtime-verified end-to-end — see docs/LIVEKIT_SETUP.md for setup and wiring.
    /// </summary>
    [RequireComponent(typeof(SpectatorCamera))]
    public class LiveKitPublisher : MonoBehaviour
    {
        [Header("Backend (token source)")]
        [Tooltip("Shared backend address. When assigned it overrides the host/port below.")]
        public BackendConfig backendConfig;

        [Tooltip("Fallback host, used only when no Backend Config asset is assigned.")]
        public string host = "localhost";
        [Tooltip("Fallback port, used only when no Backend Config asset is assigned.")]
        public int port = 8000;

        [Tooltip("Participant identity this publisher registers under in the LiveKit room.")]
        public string identity = "unity";

        private string ResolvedHost => backendConfig != null ? backendConfig.host : host;
        private int ResolvedPort => backendConfig != null ? backendConfig.port : port;

        private SpectatorCamera _cam;
        private Room _room;
        private TextureVideoSource _source;
        private LocalVideoTrack _track;

        void Awake() => _cam = GetComponent<SpectatorCamera>();

        IEnumerator Start()
        {
            // 1. Fetch a publisher token from V-CORE (carries the LiveKit URL + room).
            var tokenUrl =
                $"http://{ResolvedHost}:{ResolvedPort}/api/livekit/token?identity={identity}&role=publisher";
            using var req = UnityWebRequest.Get(tokenUrl);
            yield return req.SendWebRequest();
            if (req.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"[LiveKit] token fetch failed ({req.responseCode}): {req.error}");
                yield break;
            }

            var json = JObject.Parse(req.downloadHandler.text);
            var lkToken = (string)json["token"];
            var lkUrl = (string)json["url"];

            // 2. Connect to the LiveKit room.
            _room = new Room();
            var connect = _room.Connect(lkUrl, lkToken, new RoomOptions());
            yield return connect;
            if (connect.IsError)
            {
                Debug.LogError("[LiveKit] connect failed");
                yield break;
            }
            Debug.Log($"[LiveKit] connected → {lkUrl}");

            // 3. Publish the spectator camera render texture as a video track.
            _source = new TextureVideoSource(_cam.RT);
            _track = LocalVideoTrack.CreateVideoTrack("spectator", _source, _room);

            var options = new TrackPublishOptions
            {
                Source = TrackSource.SourceCamera,
                VideoCodec = VideoCodec.Vp8,
            };
            var publish = _room.LocalParticipant.PublishTrack(_track, options);
            yield return publish;
            if (publish.IsError)
            {
                Debug.LogError("[LiveKit] publish failed");
                yield break;
            }

            // The texture source must be started, then pumped each update so frames encode.
            _source.Start();
            StartCoroutine(_source.Update());
            Debug.Log("[LiveKit] publishing spectator camera");
        }

        void OnDestroy()
        {
            _source?.Stop();
            _room?.Disconnect();
        }
    }
}
