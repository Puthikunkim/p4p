using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Shared V-CORE backend address (host + port), referenced by every component
    /// that talks to Machine A: <see cref="VCoreConnection"/> (<c>/ws/runtime</c>) and
    /// <see cref="WebRtcSender"/> (<c>/ws/signaling</c>).
    ///
    /// Create one via <b>Assets ▸ Create ▸ V-CORE ▸ Backend Config</b> and assign it
    /// on each of those components so the backend address lives in exactly one place
    /// instead of being duplicated per component.
    ///
    /// Each component owns its own <i>endpoint path</i> (that is its concern); only
    /// the shared <i>address</i> lives here.
    /// </summary>
    [CreateAssetMenu(menuName = "V-CORE/Backend Config", fileName = "BackendConfig")]
    public class BackendConfig : ScriptableObject
    {
        [Tooltip("Hostname or IP of the V-CORE backend (Machine A).")]
        public string host = "localhost";

        [Tooltip("Port the V-CORE backend listens on.")]
        public int port = 8000;

        /// <summary>WebSocket base, e.g. <c>ws://localhost:8000</c> — append an endpoint path.</summary>
        public string WsBaseUrl => $"ws://{host}:{port}";

        /// <summary>HTTP base, e.g. <c>http://localhost:8000</c> — append an endpoint path.</summary>
        public string HttpBaseUrl => $"http://{host}:{port}";
    }
}
