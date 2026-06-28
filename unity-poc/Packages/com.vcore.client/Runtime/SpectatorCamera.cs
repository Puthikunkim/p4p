using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Provides a mono spectator camera that renders the participant's view into a
    /// <see cref="RenderTexture"/> for streaming to the dashboard via LiveKit.
    ///
    /// In a VR project, assign the participant's HMD camera to
    /// <see cref="followTarget"/> so the spectator view mirrors head pose.
    /// In a flat-screen scene, the spectator camera is the sole scene camera.
    ///
    /// The Camera component writes exclusively to <see cref="RT"/> — it does NOT
    /// output to the display. Attach a second Camera (tagged MainCamera) or use
    /// the VR SDK's own display camera for the player view.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    public class SpectatorCamera : MonoBehaviour
    {
        [Header("Render Texture")]
        [Tooltip("Render texture width in pixels (1920 = 1080p source for the spectator feed).")]
        public int width = 1920;

        [Tooltip("Render texture height in pixels (1080 = 1080p).")]
        public int height = 1080;

        [Header("VR Mirror (optional)")]
        [Tooltip("Transform to mirror (e.g. the HMD camera). Leave null for a fixed spectator.")]
        public Transform followTarget;

        [Tooltip("World-space offset applied on top of the followed pose.")]
        public Vector3 positionOffset = Vector3.zero;

        // ── public ──────────────────────────────────────────────────────────────────

        /// <summary>RenderTexture the spectator view is drawn into. Valid after Awake.</summary>
        public RenderTexture RT { get; private set; }

        /// <summary>The underlying Camera component.</summary>
        public Camera Cam { get; private set; }

        // ── lifecycle ────────────────────────────────────────────────────────────────

        void Awake()
        {
            Cam = GetComponent<Camera>();

            RT = new RenderTexture(width, height, depth: 24, RenderTextureFormat.BGRA32)
            {
                name = "SpectatorRT",
                antiAliasing = 1,
            };
            RT.Create();
            Cam.targetTexture = RT;
        }

        void LateUpdate()
        {
            if (followTarget == null) return;
            transform.SetPositionAndRotation(
                followTarget.position + positionOffset,
                followTarget.rotation);
        }

        void OnDestroy()
        {
            if (RT != null)
            {
                RT.Release();
                Destroy(RT);
            }
        }
    }
}
