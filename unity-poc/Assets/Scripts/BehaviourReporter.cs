using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.SceneManagement;

/// <summary>
/// Declares the behavioural channels Unity tracks and streams their values to
/// V-CORE as Contract 5 <c>behaviour_manifest</c> (once per connection) and
/// <c>behaviour_sample</c> (continuous) messages. The backend merges the
/// channels into the active signal manifest, so they render on the dashboard's
/// Behavioural panel, feed the rule engine, and are recorded like any signal.
///
/// Channels come from two places, merged (deduped by name):
/// - the <see cref="channels"/> list on this component (centralised), and
/// - every <see cref="BehaviourMetric"/> component in the scene (per-object,
///   scene-scanned like <see cref="ObjectStatus"/>).
///
/// Hybrid by design: each channel is swept across its declared range
/// (synthetic) until a real value is supplied — via <see cref="SetMetric"/> for
/// centralised channels or <see cref="BehaviourMetric.Report"/> for per-object
/// ones. Set <see cref="generateSyntheticData"/> = false to send only real
/// values.
///
/// Attach to the same GameObject as <see cref="VCoreConnection"/> (or assign the
/// connection explicitly).
/// </summary>
public class BehaviourReporter : MonoBehaviour
{
    [Tooltip("Connection to V-CORE. Defaults to a VCoreConnection on this GameObject.")]
    public VCoreConnection connection;

    [Header("Streaming")]
    [Tooltip("Seconds between behaviour_sample frames.")]
    public float sampleInterval = 1f;

    [Tooltip("Sweep each channel across its range when no real value has been set.")]
    public bool generateSyntheticData = true;

    [Header("Centralised channels (optional)")]
    [Tooltip("Channels declared here are merged with any BehaviourMetric components found in the scene.")]
    public BehaviourChannel[] channels =
    {
        new() { name = "response_latency",    label = "Response Latency",    unit = "s",     min = 0, max = 15,  precision = 1 },
        new() { name = "response_accuracy",   label = "Response Accuracy",   unit = "%",     min = 0, max = 100, precision = 0 },
        new() { name = "task_accuracy",       label = "Task Accuracy",       unit = "%",     min = 0, max = 100, precision = 0 },
        new() { name = "idle_time",           label = "Idle Time",           unit = "s",     min = 0, max = 30,  precision = 1 },
        new() { name = "clarification_reqs",  label = "Clarification Reqs",  unit = "/task", min = 0, max = 10,  precision = 1 },
        new() { name = "gaze_switching_rate", label = "Gaze Switching Rate", unit = "/s",    min = 0, max = 2,   precision = 2 },
    };

    [Serializable]
    public class BehaviourChannel
    {
        public string name;
        public string label;
        public string unit;
        public float min;
        public float max = 1f;
        public int precision = 1;
    }

    // One resolved channel from either source, with a provider for its real value.
    private struct Chan
    {
        public string name, unit, label;
        public float min, max;
        public int precision, index;
        public Func<float?> real;  // returns a reported value, or null for synthetic
    }

    private readonly Dictionary<string, float> _overrides = new();
    private readonly List<Chan> _active = new();
    private float _t0;

    void Awake()
    {
        if (connection == null) connection = GetComponent<VCoreConnection>();
    }

    void OnEnable()
    {
        // Scene-local BehaviourMetric components come and go with scenes, so
        // re-scan and re-declare whenever the loaded scene set changes.
        SceneManager.sceneLoaded += OnSceneLoaded;
        SceneManager.sceneUnloaded += OnSceneUnloaded;
        StartCoroutine(StreamLoop());
    }

    void OnDisable()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;
        SceneManager.sceneUnloaded -= OnSceneUnloaded;
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode) => Redeclare();
    private void OnSceneUnloaded(Scene scene) => Redeclare();

    // Re-scan the scene and re-send the manifest (replacing the backend's channel
    // set). Centralised channels persist; scene-local ones join/leave as scenes swap.
    private void Redeclare()
    {
        if (connection != null && connection.IsConnected)
        {
            Rebuild();
            SendManifest();
        }
    }

    private IEnumerator StreamLoop()
    {
        var announced = false;
        while (true)
        {
            if (connection != null && connection.IsConnected)
            {
                if (!announced)
                {
                    Rebuild();        // re-scan the scene on every fresh connection
                    SendManifest();
                    _t0 = Time.time;
                    announced = true;
                }
                SendSample(Time.time - _t0);
                yield return new WaitForSeconds(Mathf.Max(0.1f, sampleInterval));
            }
            else
            {
                announced = false;
                yield return new WaitForSeconds(0.5f);  // poll while waiting to connect
            }
        }
    }

    // ── public API (centralised channels) ─────────────────────────────────────────

    /// <summary>Push a real value for a centralised channel; overrides synthetic generation.</summary>
    public void SetMetric(string channelName, float value) => _overrides[channelName] = value;

    /// <summary>Clear a real value so the channel reverts to synthetic (if enabled).</summary>
    public void ClearMetric(string channelName) => _overrides.Remove(channelName);

    // ── channel aggregation ───────────────────────────────────────────────────────

    private void Rebuild()
    {
        _active.Clear();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        if (channels != null)
        {
            foreach (var ch in channels)
            {
                if (ch == null || string.IsNullOrEmpty(ch.name) || !seen.Add(ch.name)) continue;
                var key = ch.name;
                _active.Add(new Chan
                {
                    name = key,
                    unit = ch.unit ?? "",
                    label = string.IsNullOrEmpty(ch.label) ? key : ch.label,
                    min = ch.min, max = ch.max, precision = ch.precision, index = _active.Count,
                    real = () => _overrides.TryGetValue(key, out var v) ? v : (float?)null,
                });
            }
        }

        foreach (var m in FindObjectsByType<BehaviourMetric>(FindObjectsSortMode.None))
        {
            var key = m.EffectiveName;
            if (string.IsNullOrEmpty(key) || !seen.Add(key)) continue;
            var metric = m;
            _active.Add(new Chan
            {
                name = key,
                unit = m.unit ?? "",
                label = string.IsNullOrEmpty(m.label) ? key : m.label,
                min = m.min, max = m.max, precision = m.precision, index = _active.Count,
                // metric != null guards against a component destroyed on scene unload
                // (Unity overrides == for destroyed objects).
                real = () => metric != null && metric.HasValue ? metric.Value : (float?)null,
            });
        }
    }

    // ── send ──────────────────────────────────────────────────────────────────────

    private void SendManifest()
    {
        if (_active.Count == 0) return;
        var chList = new List<object>();
        foreach (var c in _active)
        {
            chList.Add(new Dictionary<string, object>
            {
                ["name"] = c.name,
                ["unit"] = c.unit,
                ["type"] = "scalar",
                ["range"] = new Dictionary<string, object> { ["min"] = c.min, ["max"] = c.max },
                ["display"] = new Dictionary<string, object>
                {
                    ["hint"] = "stat_card",
                    ["label"] = c.label,
                    ["precision"] = c.precision,
                    ["group"] = "behavioural",
                },
            });
        }
        var msg = new Dictionary<string, object>
        {
            ["type"] = "behaviour_manifest",
            ["payload"] = new Dictionary<string, object> { ["channels"] = chList },
        };
        connection.Send(JsonConvert.SerializeObject(msg));
    }

    private void SendSample(float t)
    {
        if (_active.Count == 0) return;
        var payload = new Dictionary<string, object>();
        foreach (var c in _active)
        {
            var r = c.real();
            float v;
            if (r.HasValue) v = r.Value;
            else if (generateSyntheticData) v = Sweep(c.min, c.max, c.index, t);
            else continue;
            payload[c.name] = Math.Round(v, Mathf.Clamp(c.precision, 0, 6));
        }
        if (payload.Count == 0) return;
        var msg = new Dictionary<string, object> { ["type"] = "behaviour_sample", ["payload"] = payload };
        connection.Send(JsonConvert.SerializeObject(msg));
    }

    // Each channel sweeps its own [min, max] with a per-channel phase offset, so
    // the demo data stays independent of whatever rules happen to be loaded.
    private static float Sweep(float min, float max, int index, float t)
    {
        var frac = 0.5f + 0.5f * Mathf.Sin(t / 7f + index * 1.7f);
        return min + (max - min) * frac;
    }
}
