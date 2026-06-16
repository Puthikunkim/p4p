using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Declares one behavioural channel that this scene object tracks, for V-CORE
    /// (Contract 5). <see cref="BehaviourReporter"/> scene-scans these — the same
    /// way <see cref="StatusCollector"/> scans <see cref="ObjectStatus"/> — and
    /// streams their values alongside any channels declared centrally on the
    /// reporter, so behavioural declaration can live per-object.
    ///
    /// Call <see cref="Report"/> from gameplay to push a real value. If you never
    /// do, the reporter sweeps the [min, max] range synthetically (while its
    /// generateSyntheticData is on), so the metric still demos out of the box.
    /// </summary>
    public class BehaviourMetric : MonoBehaviour
    {
        [Header("Channel Declaration")]
        [Tooltip("Channel name as it appears on the dashboard and in rules. Empty = GameObject name.")]
        public string metricName = "";

        [Tooltip("Human-readable label for the dashboard StatCard. Empty = the channel name.")]
        public string label = "";

        [Tooltip("Unit shown on the dashboard (e.g. s, %, /task).")]
        public string unit = "";

        [Tooltip("Minimum expected value.")]
        public float min = 0f;

        [Tooltip("Maximum expected value.")]
        public float max = 100f;

        [Range(0, 6)]
        [Tooltip("Decimal places sent to the dashboard.")]
        public int precision = 1;

        private float _value;
        private bool _hasValue;

        /// <summary>Channel name, defaulting to the GameObject name when left blank.</summary>
        public string EffectiveName => string.IsNullOrEmpty(metricName) ? gameObject.name : metricName;

        /// <summary>True once a real value has been reported via <see cref="Report"/>.</summary>
        public bool HasValue => _hasValue;

        /// <summary>The last reported real value.</summary>
        public float Value => _value;

        /// <summary>Report a real value for this metric (overrides synthetic generation).</summary>
        public void Report(float value)
        {
            _value = value;
            _hasValue = true;
        }

        /// <summary>Revert to synthetic generation (if the reporter has it enabled).</summary>
        public void Clear() => _hasValue = false;
    }
}
