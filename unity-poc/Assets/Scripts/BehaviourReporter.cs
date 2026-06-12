using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;

/// <summary>
/// Declares the behavioural channels Unity tracks and streams their values to
/// V-CORE as Contract 5 <c>behaviour_manifest</c> (once per connection) and
/// <c>behaviour_sample</c> (continuous) messages. The backend merges the
/// channels into the active signal manifest, so they render on the dashboard's
/// Behavioural panel, feed the rule engine, and are recorded like any signal.
///
/// Hybrid by design:
/// - Out of the box each channel is swept across its declared range (synthetic,
///   like the mock), so the POC streams plausible data with no extra wiring.
/// - Call <see cref="SetMetric"/> from your own tracking code to push a real
///   value for a channel; that value takes precedence over the synthetic one.
///   Set <see cref="generateSyntheticData"/> = false to send only real values.
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

    [Tooltip("Behavioural channels Unity tracks. Merged into the signal manifest on connect.")]
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

    private readonly Dictionary<string, float> _overrides = new();
    private float _t0;

    void Awake()
    {
        if (connection == null) connection = GetComponent<VCoreConnection>();
    }

    void OnEnable() => StartCoroutine(StreamLoop());

    private IEnumerator StreamLoop()
    {
        var announced = false;
        while (true)
        {
            if (connection != null && connection.IsConnected)
            {
                if (!announced)
                {
                    SendManifest();   // (re)declare channels on every fresh connection
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

    // ── public API (call from tracking code to push real values) ─────────────────

    /// <summary>Push a real value for a channel; overrides synthetic generation.</summary>
    public void SetMetric(string channelName, float value) => _overrides[channelName] = value;

    /// <summary>Clear a real value so the channel reverts to synthetic (if enabled).</summary>
    public void ClearMetric(string channelName) => _overrides.Remove(channelName);

    // ── send ──────────────────────────────────────────────────────────────────────

    private void SendManifest()
    {
        if (channels == null || channels.Length == 0) return;
        var chList = new List<object>();
        foreach (var ch in channels)
        {
            if (string.IsNullOrEmpty(ch.name)) continue;
            chList.Add(new Dictionary<string, object>
            {
                ["name"] = ch.name,
                ["unit"] = ch.unit ?? "",
                ["type"] = "scalar",
                ["range"] = new Dictionary<string, object> { ["min"] = ch.min, ["max"] = ch.max },
                ["display"] = new Dictionary<string, object>
                {
                    ["hint"] = "stat_card",
                    ["label"] = string.IsNullOrEmpty(ch.label) ? ch.name : ch.label,
                    ["precision"] = ch.precision,
                    ["group"] = "behavioural",
                },
            });
        }
        if (chList.Count == 0) return;
        var msg = new Dictionary<string, object>
        {
            ["type"] = "behaviour_manifest",
            ["payload"] = new Dictionary<string, object> { ["channels"] = chList },
        };
        connection.Send(JsonConvert.SerializeObject(msg));
    }

    private void SendSample(float t)
    {
        if (channels == null || channels.Length == 0) return;
        var payload = new Dictionary<string, object>();
        for (var i = 0; i < channels.Length; i++)
        {
            var ch = channels[i];
            if (string.IsNullOrEmpty(ch.name)) continue;

            float v;
            if (_overrides.TryGetValue(ch.name, out var real)) v = real;
            else if (generateSyntheticData) v = Sweep(ch, t, i);
            else continue;

            payload[ch.name] = Math.Round(v, Mathf.Clamp(ch.precision, 0, 6));
        }
        if (payload.Count == 0) return;
        var msg = new Dictionary<string, object> { ["type"] = "behaviour_sample", ["payload"] = payload };
        connection.Send(JsonConvert.SerializeObject(msg));
    }

    // Each channel sweeps its own [min, max] with a per-channel phase offset, so
    // the demo data stays independent of whatever rules happen to be loaded.
    private static float Sweep(BehaviourChannel ch, float t, int index)
    {
        var frac = 0.5f + 0.5f * Mathf.Sin(t / 7f + index * 1.7f);
        return ch.min + (ch.max - ch.min) * frac;
    }
}
