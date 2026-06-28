using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace VCore.Editor
{
    /// <summary>
    /// One-click scene setup: <b>V-CORE ▸ Add to Scene</b>. Creates a ready-to-run V-CORE
    /// client in the open scene so you never have to wire the components by hand — the
    /// menu-driven counterpart to dropping in a prefab (this package deliberately ships none,
    /// see the README).
    ///
    /// It adds a <c>VCoreManager</c> GameObject with <see cref="VCoreLauncher"/> plus the core
    /// link (<see cref="VCoreConnection"/>, which pulls in <see cref="StatusCollector"/> +
    /// <see cref="RequestDispatcher"/> via <c>[RequireComponent]</c>) and both reporters,
    /// finds-or-creates a single <see cref="BackendConfig"/> asset and assigns it, and — only
    /// when the LiveKit SDK is installed (the <c>VCORE_LIVEKIT</c> define) — adds a
    /// spectator-camera rig and wires it to the launcher. Without the SDK it leaves video off so
    /// there's no missing-publisher warning; re-run the menu after installing it to add the rig.
    /// </summary>
    public static class VCoreSceneSetup
    {
        private const string SettingsFolder = "Assets/Settings";
        private const string BackendConfigPath = SettingsFolder + "/BackendConfig.asset";

        [MenuItem("V-CORE/Add to Scene", priority = 0)]
        public static void AddToScene()
        {
            // Don't add a second manager if the scene already has one.
            var existing = Object.FindFirstObjectByType<VCoreLauncher>();
            if (existing != null)
            {
                Debug.LogWarning(
                    "[VCore] A VCoreLauncher is already in this scene — selecting it instead of adding another.");
                Selection.activeGameObject = existing.gameObject;
                EditorGUIUtility.PingObject(existing);
                return;
            }

            var config = FindOrCreateBackendConfig();

            // ── Manager: launcher + core link + reporters ────────────────────────────
            var manager = new GameObject("VCoreManager");
            Undo.RegisterCreatedObjectUndo(manager, "Add V-CORE to Scene");

            var launcher = manager.AddComponent<VCoreLauncher>();
            launcher.backendConfig = config;

            // Materialise the stack in the editor (the launcher would add these on play anyway).
            // Adding VCoreConnection pulls StatusCollector + RequestDispatcher via [RequireComponent].
            var conn = manager.AddComponent<VCoreConnection>();
            conn.backendConfig = config;
            manager.AddComponent<BehaviourReporter>();
            manager.AddComponent<VrContextReporter>();

            // ── Video rig (only when the LiveKit SDK is present) ─────────────────────
#if VCORE_LIVEKIT
            var rig = new GameObject("VCoreSpectatorCamera");
            Undo.RegisterCreatedObjectUndo(rig, "Add V-CORE to Scene");
            // LiveKitPublisher requires SpectatorCamera requires Camera — both auto-added.
            var publisher = rig.AddComponent<LiveKitPublisher>();
            publisher.backendConfig = config;
            launcher.publisher = publisher;
            launcher.videoPublishing = true;
            Debug.Log("[VCore] Added a LiveKit spectator-camera rig (VCORE_LIVEKIT is defined).");
#else
            // No video SDK installed — keep video off so the launcher doesn't warn about a missing publisher.
            launcher.videoPublishing = false;
            Debug.Log("[VCore] Added V-CORE without video. Install the LiveKit SDK (io.livekit.livekit-sdk) " +
                      "and re-run 'V-CORE ▸ Add to Scene' to add the spectator-camera rig.");
#endif

            Selection.activeGameObject = manager;
            EditorGUIUtility.PingObject(manager);
            EditorSceneManager.MarkSceneDirty(manager.scene);

            Debug.Log("[VCore] Added V-CORE to the scene. Point the BackendConfig host/port at your backend, " +
                      "then press Play.");
        }

        /// <summary>Reuse the project's existing BackendConfig if it has one; otherwise create
        /// a default at <c>Assets/Settings/BackendConfig.asset</c>.</summary>
        private static BackendConfig FindOrCreateBackendConfig()
        {
            foreach (var guid in AssetDatabase.FindAssets("t:BackendConfig"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var found = AssetDatabase.LoadAssetAtPath<BackendConfig>(path);
                if (found != null) return found;
            }

            if (!AssetDatabase.IsValidFolder(SettingsFolder))
                AssetDatabase.CreateFolder("Assets", "Settings");

            var config = ScriptableObject.CreateInstance<BackendConfig>();
            AssetDatabase.CreateAsset(config, BackendConfigPath);
            AssetDatabase.SaveAssets();
            Debug.Log(
                $"[VCore] Created {BackendConfigPath} (host=localhost, port=8000) — edit it to point at your backend.");
            return config;
        }
    }
}
