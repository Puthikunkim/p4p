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

    [Tooltip("Scripted steps sent while autoPlay is on. Keys render as-is on the dashboard.")]
    public Step[] steps =
    {
        new() { scene = "Aisle 1 – Produce", step = "1 / 4", instruction = "Pick up the apples", itemsLeft = 3 },
        new() { scene = "Aisle 2 – Bakery",  step = "2 / 4", instruction = "Select the milk",     itemsLeft = 2 },
        new() { scene = "Aisle 3 – Dairy",   step = "3 / 4", instruction = "Find the cheese",      itemsLeft = 1 },
        new() { scene = "Checkout",          step = "4 / 4", instruction = "Pay for your items",   itemsLeft = 0 },
    };

    [Serializable]
    public class Step
    {
        public string scene;
        public string step;
        public string instruction;
        public int itemsLeft;
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

    /// <summary>Report one scripted step as VR context.</summary>
    public void ReportStep(Step step)
    {
        if (step == null) return;
        ReportContext(new Dictionary<string, object>
        {
            ["scene"] = step.scene,
            ["step"] = step.step,
            ["instruction"] = step.instruction,
            ["items_left"] = step.itemsLeft,
        });
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
