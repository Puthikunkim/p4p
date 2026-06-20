using System;
using UnityEngine;
using UnityEngine.Events;

namespace VCore
{
    /// <summary>
    /// Declares one settable status on this GameObject for V-CORE (Contract 3b).
    ///
    /// Attach multiple ObjectStatus components to the same GameObject to expose
    /// multiple statuses (e.g. brightness + crackle on a campfire).
    ///
    /// Wire <see cref="OnContinuousValue"/> / <see cref="OnDiscreteValue"/> in the
    /// Inspector to the actual property setters — e.g. a Light's intensity field.
    /// </summary>
    public class ObjectStatus : MonoBehaviour
    {
        [Header("Object Identity")]
        [Tooltip("Unique ID for this object in the manifest. Leave empty to use the GameObject name.")]
        public string objectId = "";

        [Tooltip("Tags V-CORE rules can address this object by (e.g. ambient_light, fire).")]
        public string[] tags = Array.Empty<string>();

        [Header("Status Declaration")]
        [Tooltip("Name of this status as it appears in rules (e.g. brightness, crackle).")]
        public string statusName = "brightness";

        public enum StatusType { Continuous, Discrete }

        [Tooltip("Continuous: a float in [rangeMin, rangeMax]. Discrete: one of the listed string values.")]
        public StatusType type = StatusType.Continuous;

        [Header("Continuous Settings")]
        [Tooltip("Minimum allowed value (continuous type only).")]
        public float rangeMin = 0f;

        [Tooltip("Maximum allowed value (continuous type only).")]
        public float rangeMax = 100f;

        [Tooltip("Invoked on the main thread when V-CORE sets a continuous value on this status.")]
        public UnityEvent<float> OnContinuousValue = new();

        [Header("Discrete Settings")]
        [Tooltip("Allowed state names (discrete type only, e.g. off / low / high).")]
        public string[] discreteValues = Array.Empty<string>();

        [Tooltip("Invoked on the main thread when V-CORE sets a discrete value on this status.")]
        public UnityEvent<string> OnDiscreteValue = new();

        // ── public API ──────────────────────────────────────────────────────────────

        /// <summary>Effective object ID: explicit field or the GameObject name.</summary>
        public string EffectiveId => string.IsNullOrEmpty(objectId) ? gameObject.name : objectId;

        /// <summary>
        /// Called by <see cref="RequestDispatcher"/> when a matching status-change
        /// request arrives from V-CORE. Invokes the appropriate UnityEvent.
        /// </summary>
        public void ApplyValue(object value)
        {
            if (type == StatusType.Continuous)
            {
                if (value is float f)
                {
                    OnContinuousValue.Invoke(f);
                }
                else if (value is double d)
                {
                    OnContinuousValue.Invoke((float)d);
                }
                else if (float.TryParse(value?.ToString(), out float parsed))
                {
                    OnContinuousValue.Invoke(parsed);
                }
                else
                {
                    Debug.LogWarning($"[ObjectStatus] Cannot convert value '{value}' to float for status '{statusName}'");
                }
            }
            else
            {
                var s = value?.ToString();
                if (s != null)
                    OnDiscreteValue.Invoke(s);
            }
        }
    }
}
