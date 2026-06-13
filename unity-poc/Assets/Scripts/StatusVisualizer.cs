using UnityEngine;

/// <summary>
/// Makes a rule-driven status obvious in the camera feed by mapping its value to
/// this object's scale. Put it on a visible mesh (e.g. a Cube) alongside an
/// <see cref="ObjectStatus"/>, then wire in the Inspector:
///   ObjectStatus → On Continuous Value → StatusVisualizer.SetContinuous
/// </summary>
public class StatusVisualizer : MonoBehaviour
{
    [Header("Continuous mapping (e.g. brightness 0–100)")]
    [Tooltip("Value that maps to minScale.")]
    public float min = 0f;

    [Tooltip("Value that maps to maxScale.")]
    public float max = 100f;

    public float minScale = 0.6f;
    public float maxScale = 2.2f;

    /// <summary>Wire ObjectStatus.OnContinuousValue here (passes the rule's value).</summary>
    public void SetContinuous(float value)
    {
        float t = Mathf.Clamp01(Mathf.InverseLerp(min, max, value));
        transform.localScale = Vector3.one * Mathf.Lerp(minScale, maxScale, t);
    }
}
