using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Base type for a component that publishes the spectator camera to V-CORE's media
    /// plane. It lives in the core assembly so <see cref="VCoreLauncher"/> can reference and
    /// toggle a publisher without the core taking a hard dependency on any specific media
    /// SDK. Concrete publishers (e.g. <c>LiveKitPublisher</c>) live in their own optional
    /// assembly and subclass this — keeping the SDK an opt-in module.
    /// </summary>
    public abstract class VCoreVideoPublisher : MonoBehaviour
    {
        [Tooltip("Shared backend address (the token source). The VCoreLauncher forwards its " +
                 "own Backend Config here when set, so the address can live in one place.")]
        public BackendConfig backendConfig;
    }
}
