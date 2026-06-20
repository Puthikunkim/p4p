using UnityEngine;

namespace VCore
{
    /// <summary>
    /// One-stop launcher that brings up the whole V-CORE Unity client from a single
    /// component, with Inspector toggles for the optional features — the "plug into any
    /// scene" entry point (drop the <c>VCore</c> prefab in, or add this one component to
    /// an empty GameObject, assign a <see cref="BackendConfig"/>, tick what you need).
    ///
    /// On <c>Awake</c> (runs early via <see cref="DefaultExecutionOrder"/>) it:
    /// - ensures the core link exists — <see cref="VCoreConnection"/>, which pulls in
    ///   <see cref="StatusCollector"/> + <see cref="RequestDispatcher"/> via
    ///   <c>[RequireComponent]</c> — and pushes the shared config onto it;
    /// - adds-or-enables the optional producers (<see cref="BehaviourReporter"/>,
    ///   <see cref="VrContextReporter"/>) per the toggles, or disables them when off
    ///   (disabled, not destroyed, so a prefab keeps their Inspector config);
    /// - enables/disables the assigned <see cref="LiveKitPublisher"/>. Video lives on its
    ///   own camera rig (it needs a <see cref="Camera"/> via <see cref="SpectatorCamera"/>),
    ///   so it is referenced, not created here.
    ///
    /// The launcher only overwrites a component's shared config when its own field is set
    /// (e.g. a null <see cref="backendConfig"/> is left alone), so it never clobbers config
    /// you authored directly on the bundled components.
    /// </summary>
    [DefaultExecutionOrder(-100)]
    [DisallowMultipleComponent]
    public class VCoreLauncher : MonoBehaviour
    {
        [Header("Backend")]
        [Tooltip("Shared backend address, pushed to the connection and the video publisher. " +
                 "Leave empty to keep whatever is already set on those components.")]
        public BackendConfig backendConfig;

        [Header("Scene identity (Object-Status Manifest)")]
        [Tooltip("Scene name reported in the manifest. Leave blank to keep the StatusCollector's own value.")]
        public string sceneName = "scene";

        [Tooltip("Runtime identifier reported in the manifest. Leave blank to keep the StatusCollector's own value.")]
        public string runtimeId = "unity";

        [Header("Lifetime")]
        [Tooltip("Keep the connection (and reporters) alive across scene loads so a session can span scenes.")]
        public bool persistAcrossScenes = true;

        [Header("Optional features")]
        [Tooltip("Stream behavioural channels to V-CORE (BehaviourReporter).")]
        public bool behaviourMetrics = true;

        [Tooltip("Report study step / scene context to V-CORE (VrContextReporter).")]
        public bool vrContext = true;

        [Tooltip("Publish the spectator camera. Requires a video publisher assigned below.")]
        public bool videoPublishing = true;

        [Header("Video (lives on its own camera rig)")]
        [Tooltip("The video publisher (e.g. LiveKitPublisher) on the spectator-camera GameObject. It needs " +
                 "its own Camera, so it cannot live on this object; assign it here and 'videoPublishing' toggles it.")]
        public VCoreVideoPublisher publisher;

        void Awake()
        {
            // ── Core link (always on) ────────────────────────────────────────────────
            // Adding VCoreConnection auto-adds StatusCollector + RequestDispatcher via
            // its [RequireComponent], so the receive + manifest path is always wired.
            var conn = GetOrAdd<VCoreConnection>();
            if (backendConfig != null) conn.backendConfig = backendConfig;
            conn.persistAcrossScenes = persistAcrossScenes;

            var collector = GetOrAdd<StatusCollector>();
            if (!string.IsNullOrWhiteSpace(sceneName)) collector.sceneName = sceneName;
            if (!string.IsNullOrWhiteSpace(runtimeId)) collector.runtimeId = runtimeId;

            // ── Optional producers ───────────────────────────────────────────────────
            Toggle<BehaviourReporter>(behaviourMetrics);
            Toggle<VrContextReporter>(vrContext);

            // ── Video (referenced, not created) ──────────────────────────────────────
            if (publisher != null)
            {
                if (backendConfig != null) publisher.backendConfig = backendConfig;
                publisher.enabled = videoPublishing;
            }
            else if (videoPublishing)
            {
                Debug.LogWarning(
                    "[VCore] videoPublishing is on but no LiveKitPublisher is assigned — assign the " +
                    "spectator-camera rig's publisher on the VCoreLauncher, or turn the toggle off.");
            }
        }

        private T GetOrAdd<T>() where T : Component
        {
            var c = GetComponent<T>();
            return c != null ? c : gameObject.AddComponent<T>();
        }

        // Add-and-enable when on; disable (keep) when off so bundled config survives.
        private void Toggle<T>(bool on) where T : MonoBehaviour
        {
            var c = GetComponent<T>();
            if (on)
            {
                if (c == null) c = gameObject.AddComponent<T>();
                c.enabled = true;
            }
            else if (c != null)
            {
                c.enabled = false;
            }
        }
    }
}
