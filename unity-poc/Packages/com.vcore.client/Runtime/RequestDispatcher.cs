using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Dispatches incoming V-CORE Status-Change Requests (Contract 3a) to the
    /// matching <see cref="ObjectStatus"/> components in the scene.
    ///
    /// Called from <see cref="VCoreConnection.Update"/> on the Unity main thread,
    /// so all Unity API calls here are safe.
    ///
    /// Target resolution:
    /// - <c>{"tag": "ambient_light"}</c> → all ObjectStatus components that carry
    ///   that tag and declare the matching status name.
    /// - <c>{"id": "campfire_01"}</c> → the ObjectStatus component(s) whose
    ///   EffectiveId matches and whose statusName matches.
    ///
    /// Unresolved targets are logged as warnings and dropped — never a crash.
    /// </summary>
    public class RequestDispatcher : MonoBehaviour
    {
        // Rebuilt lazily on first dispatch; call RebuildIndex() after scene changes.
        private Dictionary<string, List<ObjectStatus>> _byId;
        private Dictionary<string, List<ObjectStatus>> _byTag;
        // Action indices (the free-form command counterpart to statuses).
        private Dictionary<string, List<VCoreAction>> _actionsById;
        private Dictionary<string, List<VCoreAction>> _actionsByTag;
        private List<VCoreAction> _sceneActions;

        void Start() => RebuildIndex();

        // ── public API ──────────────────────────────────────────────────────────────

        /// <summary>
        /// Process one raw JSON string from V-CORE. Called on the main thread by
        /// <see cref="VCoreConnection"/>.
        /// </summary>
        public void OnRequest(string json)
        {
            JObject o;
            try
            {
                o = JObject.Parse(json);
            }
            catch (Exception ex)
            {
                Debug.LogError($"[Dispatcher] Malformed request JSON — {ex.Message}\n{json}");
                return;
            }

            EnsureIndex();

            // Action requests carry an "action" field; status requests carry "status".
            if (o["action"] != null)
            {
                DispatchAction(o);
                return;
            }

            StatusRequest req;
            try
            {
                req = o.ToObject<StatusRequest>();
            }
            catch (Exception ex)
            {
                Debug.LogError($"[Dispatcher] Malformed status request — {ex.Message}\n{json}");
                return;
            }

            if (req?.Target == null || req.Status == null)
            {
                Debug.LogWarning($"[Dispatcher] Request missing target or status — dropped\n{json}");
                return;
            }

            Dispatch(req);
        }

        /// <summary>Rebuild the tag/id → ObjectStatus index after a scene change.</summary>
        public void RebuildIndex()
        {
            _byId = new Dictionary<string, List<ObjectStatus>>(StringComparer.Ordinal);
            _byTag = new Dictionary<string, List<ObjectStatus>>(StringComparer.Ordinal);

            foreach (var obj in FindObjectsByType<ObjectStatus>(FindObjectsSortMode.None))
            {
                var id = obj.EffectiveId;
                if (!_byId.ContainsKey(id)) _byId[id] = new List<ObjectStatus>();
                _byId[id].Add(obj);

                foreach (var tag in obj.tags ?? Array.Empty<string>())
                {
                    if (string.IsNullOrEmpty(tag)) continue;
                    if (!_byTag.ContainsKey(tag)) _byTag[tag] = new List<ObjectStatus>();
                    _byTag[tag].Add(obj);
                }
            }

            _actionsById = new Dictionary<string, List<VCoreAction>>(StringComparer.Ordinal);
            _actionsByTag = new Dictionary<string, List<VCoreAction>>(StringComparer.Ordinal);
            _sceneActions = new List<VCoreAction>();

            foreach (var act in FindObjectsByType<VCoreAction>(FindObjectsSortMode.None))
            {
                if (act.scope == VCoreAction.ActionScope.Scene)
                {
                    _sceneActions.Add(act);
                    continue;
                }
                var id = act.EffectiveId;
                if (!_actionsById.ContainsKey(id)) _actionsById[id] = new List<VCoreAction>();
                _actionsById[id].Add(act);

                foreach (var tag in act.tags ?? Array.Empty<string>())
                {
                    if (string.IsNullOrEmpty(tag)) continue;
                    if (!_actionsByTag.ContainsKey(tag)) _actionsByTag[tag] = new List<VCoreAction>();
                    _actionsByTag[tag].Add(act);
                }
            }

            Debug.Log(
                $"[Dispatcher] Index built: {_byId.Count} object(s), {_byTag.Count} tag(s), " +
                $"{_actionsById.Count + _sceneActions.Count} action target(s)");
        }

        // ── dispatch ────────────────────────────────────────────────────────────────

        private void Dispatch(StatusRequest req)
        {
            List<ObjectStatus> candidates;

            if (req.Target.Tag != null)
            {
                if (!_byTag.TryGetValue(req.Target.Tag, out candidates))
                {
                    Debug.LogWarning(
                        $"[Dispatcher] No object with tag '{req.Target.Tag}' — request dropped " +
                        $"(intent_id={req.IntentId})");
                    return;
                }
            }
            else if (req.Target.Id != null)
            {
                if (!_byId.TryGetValue(req.Target.Id, out candidates))
                {
                    Debug.LogWarning(
                        $"[Dispatcher] No object with id '{req.Target.Id}' — request dropped " +
                        $"(intent_id={req.IntentId})");
                    return;
                }
            }
            else return;

            var dispatched = 0;
            foreach (var obj in candidates)
            {
                if (!string.Equals(obj.statusName, req.Status, StringComparison.Ordinal))
                    continue;

                ApplyToObject(obj, req.Value);
                dispatched++;
                Debug.Log(
                    $"[Dispatcher] {req.Status}={req.Value} → {obj.EffectiveId} " +
                    $"[source={req.Source}]");
            }

            if (dispatched == 0)
            {
                Debug.LogWarning(
                    $"[Dispatcher] No component declared status '{req.Status}' on " +
                    $"{(req.Target.Tag != null ? $"tag:{req.Target.Tag}" : $"id:{req.Target.Id}")} " +
                    $"— request dropped");
            }
        }

        // Resolve an action request to VCoreAction components and invoke them. A request
        // with no target hits scene-scoped actions; a tag/id target fans out like statuses.
        private void DispatchAction(JObject o)
        {
            var action = (string)o["action"];
            if (string.IsNullOrEmpty(action))
            {
                Debug.LogWarning("[Dispatcher] Action request missing 'action' — dropped");
                return;
            }

            var target = o["target"] as JObject;
            List<VCoreAction> candidates;
            string label;
            if (target == null)
            {
                candidates = _sceneActions;
                label = "scene";
            }
            else if (target["tag"] != null)
            {
                var tag = (string)target["tag"];
                _actionsByTag.TryGetValue(tag, out candidates);
                label = $"tag:{tag}";
            }
            else if (target["id"] != null)
            {
                var id = (string)target["id"];
                _actionsById.TryGetValue(id, out candidates);
                label = $"id:{id}";
            }
            else
            {
                Debug.LogWarning("[Dispatcher] Action request has empty target — dropped");
                return;
            }

            var source = (string)o["source"];
            var invoked = 0;
            if (candidates != null)
            {
                foreach (var act in candidates)
                {
                    if (!string.Equals(act.actionName, action, StringComparison.Ordinal)) continue;
                    act.Invoke();
                    invoked++;
                    Debug.Log($"[Dispatcher] action {action}() → {act.EffectiveId} [source={source}]");
                }
            }

            if (invoked == 0)
                Debug.LogWarning($"[Dispatcher] No VCoreAction '{action}' on {label} — request dropped");
        }

        private static void ApplyToObject(ObjectStatus obj, JToken value)
        {
            try
            {
                if (obj.type == ObjectStatus.StatusType.Continuous)
                    obj.ApplyValue(value.ToObject<float>());
                else
                    obj.ApplyValue(value.ToObject<string>());
            }
            catch (Exception ex)
            {
                Debug.LogError(
                    $"[Dispatcher] Failed to apply value to '{obj.EffectiveId}.{obj.statusName}': " +
                    $"{ex.Message}");
            }
        }

        private void EnsureIndex()
        {
            if (_byId != null) return;
            RebuildIndex();
        }

        // ── request DTO ─────────────────────────────────────────────────────────────

        private class StatusRequest
        {
            [JsonProperty("schema_version")] public string SchemaVersion { get; set; }
            [JsonProperty("intent_id")]      public string IntentId      { get; set; }
            [JsonProperty("timestamp")]      public string Timestamp     { get; set; }
            [JsonProperty("target")]         public TargetDto Target     { get; set; }
            [JsonProperty("status")]         public string Status        { get; set; }
            [JsonProperty("value")]          public JToken Value         { get; set; }
            [JsonProperty("source_rule")]    public string SourceRule    { get; set; }
            [JsonProperty("source")]         public string Source        { get; set; }
        }

        private class TargetDto
        {
            [JsonProperty("tag")] public string Tag { get; set; }
            [JsonProperty("id")]  public string Id  { get; set; }
        }
    }
}
