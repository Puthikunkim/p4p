using System;
using System.Collections.Generic;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

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

    void Start() => RebuildIndex();

    // ── public API ──────────────────────────────────────────────────────────────

    /// <summary>
    /// Process one raw JSON string from V-CORE. Called on the main thread by
    /// <see cref="VCoreConnection"/>.
    /// </summary>
    public void OnRequest(string json)
    {
        StatusRequest req;
        try
        {
            req = JsonConvert.DeserializeObject<StatusRequest>(json);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[Dispatcher] Malformed request JSON — {ex.Message}\n{json}");
            return;
        }

        if (req?.Target == null || req.Status == null)
        {
            Debug.LogWarning($"[Dispatcher] Request missing target or status — dropped\n{json}");
            return;
        }

        EnsureIndex();
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

        Debug.Log($"[Dispatcher] Index built: {_byId.Count} object(s), {_byTag.Count} tag(s)");
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
