using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace VCore.Editor
{
    /// <summary>
    /// Bakes a <b>project-wide catalog</b> of every <see cref="ObjectStatus"/> and
    /// <see cref="VCoreAction"/> across all Build-Settings scenes <i>and</i> all prefab
    /// assets into <c>Assets/Resources/VCoreCatalog.json</c> (the same shape as the
    /// Object-Status Manifest).
    ///
    /// At runtime <see cref="VCoreConnection"/> sends this file to V-CORE on connect as an
    /// <c>object_status_catalog</c>, so the dashboard's rule builder can author rules against
    /// objects/actions that live in scenes which aren't loaded yet. The live per-scene
    /// manifest still drives dispatch + degradation, so a rule targeting an unloaded object
    /// is simply dormant until its scene loads.
    ///
    /// Runs automatically at the start of every player build (see <c>VCoreCatalogBuildHook</c>);
    /// run it by hand to refresh during editing: <b>V-CORE ▸ Bake Project Catalog</b>.
    /// </summary>
    public static class VCoreCatalogBaker
    {
        [MenuItem("V-CORE/Bake Project Catalog")]
        public static void Bake()
        {
            if (!EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            BakeToFile();
        }

        /// <summary>Scan the project and write the catalog without prompting — safe to call
        /// from the build preprocessor (see <c>VCoreCatalogBuildHook</c>).</summary>
        public static void BakeToFile()
        {
            // id → (tags, statusName → status declaration). Grouping mirrors StatusCollector.
            var objects = new Dictionary<string, (HashSet<string> tags, Dictionary<string, object> statuses)>();
            var actions = new Dictionary<string, Dictionary<string, object>>();

            void AddStatus(ObjectStatus s)
            {
                if (s == null) return;
                var id = s.EffectiveId;
                if (!objects.TryGetValue(id, out var entry))
                {
                    entry = (new HashSet<string>(), new Dictionary<string, object>());
                    objects[id] = entry;
                }
                foreach (var t in s.tags ?? System.Array.Empty<string>())
                    if (!string.IsNullOrEmpty(t)) entry.tags.Add(t);

                var decl = new Dictionary<string, object> { ["name"] = s.statusName };
                if (s.type == ObjectStatus.StatusType.Continuous)
                {
                    decl["type"] = "continuous";
                    decl["range"] = new Dictionary<string, object> { ["min"] = s.rangeMin, ["max"] = s.rangeMax };
                }
                else
                {
                    decl["type"] = "discrete";
                    decl["values"] = s.discreteValues ?? System.Array.Empty<string>();
                }
                entry.statuses[s.statusName] = decl;
            }

            void AddAction(VCoreAction a)
            {
                if (a == null || string.IsNullOrEmpty(a.actionName)) return;
                var decl = new Dictionary<string, object> { ["name"] = a.actionName };
                string key;
                if (a.scope == VCoreAction.ActionScope.Scene)
                {
                    decl["scope"] = "scene";
                    key = $"{a.actionName}|scene|";
                }
                else
                {
                    decl["scope"] = "object";
                    decl["id"] = a.EffectiveId;
                    decl["tags"] = a.tags ?? System.Array.Empty<string>();
                    key = $"{a.actionName}|object|{a.EffectiveId}";
                }
                actions[key] = decl;
            }

            // ── Scenes in Build Settings ─────────────────────────────────────────────
            var setup = EditorSceneManager.GetSceneManagerSetup();
            try
            {
                foreach (var bs in EditorBuildSettings.scenes)
                {
                    if (!bs.enabled) continue;
                    var scene = EditorSceneManager.OpenScene(bs.path, OpenSceneMode.Additive);
                    foreach (var root in scene.GetRootGameObjects())
                    {
                        foreach (var s in root.GetComponentsInChildren<ObjectStatus>(true)) AddStatus(s);
                        foreach (var a in root.GetComponentsInChildren<VCoreAction>(true)) AddAction(a);
                    }
                    EditorSceneManager.CloseScene(scene, true);
                }
            }
            finally
            {
                if (setup != null && setup.Length > 0) EditorSceneManager.RestoreSceneManagerSetup(setup);
            }

            // ── Prefab assets ────────────────────────────────────────────────────────
            foreach (var guid in AssetDatabase.FindAssets("t:Prefab"))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var go = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                if (go == null) continue;
                foreach (var s in go.GetComponentsInChildren<ObjectStatus>(true)) AddStatus(s);
                foreach (var a in go.GetComponentsInChildren<VCoreAction>(true)) AddAction(a);
            }

            // ── Assemble manifest-shaped payload ─────────────────────────────────────
            var objectList = objects.Select(kvp => (object)new Dictionary<string, object>
            {
                ["id"] = kvp.Key,
                ["tags"] = kvp.Value.tags.ToList(),
                ["statuses"] = kvp.Value.statuses.Values.ToList(),
            }).ToList();

            var payload = new Dictionary<string, object>
            {
                ["schema_version"] = "1.0.0",
                ["scene"] = "(project catalog)",
                ["runtime"] = "catalog",
                ["objects"] = objectList,
                ["abstract_actions"] = actions.Values.ToList(),
            };

            var json = JsonConvert.SerializeObject(payload, Formatting.Indented);
            var dir = Path.Combine(Application.dataPath, "Resources");
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "VCoreCatalog.json"), json);
            AssetDatabase.Refresh();

            Debug.Log(
                $"[VCore] Baked project catalog: {objectList.Count} object(s), {actions.Count} action(s) " +
                "→ Assets/Resources/VCoreCatalog.json");
        }
    }
}
