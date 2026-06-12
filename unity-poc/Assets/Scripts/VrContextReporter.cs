using System;
using System.Collections;
using System.Collections.Generic;
using Newtonsoft.Json;
using UnityEngine;

/// <summary>
/// Reports the participant's current study step / scene context to V-CORE as
/// Contract 4 <c>vr_context</c> messages, which the dashboard renders in its
/// VR Context panel.
///
/// Hybrid by design:
/// - Out of the box it walks the <see cref="steps"/> list on a timer, so the POC
///   behaves like the headless mock with no extra wiring.
/// - Call <see cref="ReportContext"/> / <see cref="ReportStep"/> from your own
///   gameplay (trigger volumes, a study manager, …) to push real context.
///   Set <see cref="autoPlay"/> = false to stop the synthetic walk-through.
///
/// Attach to the same GameObject as <see cref="VCoreConnection"/> (or assign the
/// connection explicitly).
/// </summary>
public class VrContextReporter : MonoBehaviour
{
    [Tooltip("Connection to V-CORE. Defaults to a VCoreConnection on this GameObject.")]
    public VCoreConnection connection;

    [Header("Demo walk-through")]
    [Tooltip("Advance through the steps automatically on a timer (synthetic data).")]
    public bool autoPlay = true;

    [Tooltip("Seconds between automatic step changes.")]
    public float stepInterval = 6f;

    [Tooltip("Scripted steps sent while autoPlay is on. Each step is a free-form set of " +
             "key/value fields; keys render as-is on the dashboard, so any scene can author its own.")]
    public Step[] steps =
    {
        new() { fields = new[] {
            new ContextField { key = "scene", value = "Aisle 1 – Produce" },
            new ContextField { key = "step", value = "1 / 4" },
            new ContextField { key = "instruction", value = "Pick up the apples" },
            new ContextField { key = "items_left", value = "3" },
        }},
        new() { fields = new[] {
            new ContextField { key = "scene", value = "Aisle 2 – Bakery" },
            new ContextField { key = "step", value = "2 / 4" },
            new ContextField { key = "instruction", value = "Select the milk" },
            new ContextField { key = "items_left", value = "2" },
        }},
        new() { fields = new[] {
            new ContextField { key = "scene", value = "Aisle 3 – Dairy" },
            new ContextField { key = "step", value = "3 / 4" },
            new ContextField { key = "instruction", value = "Find the cheese" },
            new ContextField { key = "items_left", value = "1" },
        }},
        new() { fields = new[] {
            new ContextField { key = "scene", value = "Checkout" },
            new ContextField { key = "step", value = "4 / 4" },
            new ContextField { key = "instruction", value = "Pay for your items" },
            new ContextField { key = "items_left", value = "0" },
        }},
    };

    [Serializable]
    public class ContextField
    {
        public string key;
        public string value;
    }

    [Serializable]
    public class Step
    {
        public ContextField[] fields = Array.Empty<ContextField>();
    }

    void Awake()
    {
        if (connection == null) connection = GetComponent<VCoreConnection>();
    }

    void OnEnable() => StartCoroutine(WalkLoop());

    private IEnumerator WalkLoop()
    {
        var i = 0;
        var announced = false;
        while (true)
        {
            if (connection != null && connection.IsConnected)
            {
                if (!announced) { i = 0; announced = true; }  // fresh (re)connection
                if (autoPlay && steps != null && steps.Length > 0)
                {
                    ReportStep(steps[i % steps.Length]);
                    i++;
                }
                yield return new WaitForSeconds(Mathf.Max(0.5f, stepInterval));
            }
            else
            {
                announced = false;
                yield return new WaitForSeconds(0.5f);  // poll while waiting to connect
            }
        }
    }

    // ── public API (call from gameplay to push real context) ─────────────────────

    /// <summary>Report one scripted step (its free-form fields) as VR context.</summary>
    public void ReportStep(Step step)
    {
        if (step?.fields == null) return;
        var fields = new Dictionary<string, object>();
        foreach (var f in step.fields)
            if (f != null && !string.IsNullOrEmpty(f.key)) fields[f.key] = f.value;
        ReportContext(fields);
    }

    /// <summary>
    /// Report arbitrary context fields. The dashboard renders whatever keys are
    /// present (snake_case keys become title-cased labels), so any scene can
    /// describe its own context.
    /// </summary>
    public void ReportContext(Dictionary<string, object> fields)
    {
        if (connection == null || !connection.IsConnected || fields == null || fields.Count == 0)
            return;
        var msg = new Dictionary<string, object> { ["type"] = "vr_context", ["payload"] = fields };
        connection.Send(JsonConvert.SerializeObject(msg));
    }
}
