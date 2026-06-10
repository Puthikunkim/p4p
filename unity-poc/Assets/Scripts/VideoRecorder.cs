using System;
using System.Collections;
using System.IO;
using System.Text;
using Newtonsoft.Json;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// Records the <see cref="SpectatorCamera"/> view to a PNG-frame sequence
/// during a V-CORE session, stamps it with the session's LSL start time for
/// post-session alignment with the XDF signal data, and uploads the recording
/// folder to V-CORE on session end (Amendment 2).
///
/// POC trade-offs
/// --------------
/// - PNG frames are the simplest no-dependency approach. For production, swap
///   the capture loop for an FFmpeg plugin (e.g. AVPro Movie Capture) that
///   encodes directly to H.264 without filling disk with individual frames.
/// - The upload POC POSTs the metadata JSON; a full implementation would zip
///   and POST the frames or stream them via multipart upload.
/// - Call <see cref="StartRecording"/> / <see cref="StopRecording"/> from a
///   session lifecycle manager (e.g. wired to the V-CORE "Start/End Session"
///   WebSocket message).
/// </summary>
[RequireComponent(typeof(SpectatorCamera))]
public class VideoRecorder : MonoBehaviour
{
    [Header("Recording")]
    [Tooltip("Root directory for session recordings (relative to Application.persistentDataPath).")]
    public string outputDir = "Recordings";

    [Tooltip("Frames captured per second.")]
    [Range(1, 60)]
    public int fps = 30;

    [Header("Upload")]
    [Tooltip("V-CORE backend base URL for the upload endpoint.")]
    public string vcoreBaseUrl = "http://localhost:8000";

    // ── state ────────────────────────────────────────────────────────────────────
    private SpectatorCamera _cam;
    private bool _recording;
    private string _sessionDir;
    private string _sessionId;
    private float _captureInterval;
    private float _nextCapture;
    private int _frameIndex;

    // ── lifecycle ────────────────────────────────────────────────────────────────

    void Awake()
    {
        _cam = GetComponent<SpectatorCamera>();
        _captureInterval = 1f / fps;
    }

    void Update()
    {
        if (!_recording || Time.time < _nextCapture) return;
        _nextCapture = Time.time + _captureInterval;
        StartCoroutine(CaptureFrame());
    }

    // ── public API ───────────────────────────────────────────────────────────────

    /// <summary>
    /// Begin recording a new session.
    /// </summary>
    /// <param name="sessionId">V-CORE session ID (used as the folder name and in the metadata).</param>
    /// <param name="lslStartTime">
    /// ISO-8601 string of the session's LSL start time so the recording can be
    /// aligned with the XDF signal data during review. Pass <c>null</c> to use
    /// the current wall-clock time (useful when LSL is not running).
    /// </param>
    public void StartRecording(string sessionId, string lslStartTime = null)
    {
        if (_recording)
        {
            Debug.LogWarning("[VideoRecorder] Already recording — call StopRecording first");
            return;
        }

        _sessionId = sessionId;
        _sessionDir = Path.Combine(Application.persistentDataPath, outputDir, sessionId);
        Directory.CreateDirectory(_sessionDir);

        var meta = new SessionMeta
        {
            SessionId = sessionId,
            LslStartTime = lslStartTime ?? DateTimeOffset.UtcNow.ToString("o"),
            Fps = fps,
            Width = _cam.width,
            Height = _cam.height,
            StartedAt = DateTimeOffset.UtcNow.ToString("o"),
        };

        File.WriteAllText(
            Path.Combine(_sessionDir, "meta.json"),
            JsonConvert.SerializeObject(meta, Formatting.Indented));

        _frameIndex = 0;
        _nextCapture = Time.time;
        _recording = true;
        Debug.Log($"[VideoRecorder] Recording started → {_sessionDir}  (fps={fps})");
    }

    /// <summary>
    /// Stop recording and optionally upload the session metadata to V-CORE.
    /// </summary>
    public void StopRecording(bool upload = true)
    {
        if (!_recording)
        {
            Debug.LogWarning("[VideoRecorder] Not recording");
            return;
        }

        _recording = false;
        Debug.Log($"[VideoRecorder] Recording stopped ({_frameIndex} frames captured)");

        if (upload)
            StartCoroutine(UploadMetadata());
    }

    // ── frame capture ────────────────────────────────────────────────────────────

    private IEnumerator CaptureFrame()
    {
        yield return new WaitForEndOfFrame();

        var rt = _cam.RT;
        var prevActive = RenderTexture.active;
        RenderTexture.active = rt;

        var tex = new Texture2D(rt.width, rt.height, TextureFormat.RGBA32, mipChain: false);
        tex.ReadPixels(new Rect(0, 0, rt.width, rt.height), 0, 0);
        tex.Apply();

        RenderTexture.active = prevActive;

        var path = Path.Combine(_sessionDir, $"frame_{_frameIndex:D6}.png");

        // Encode on the main thread is fine for POC fps; for high fps, offload
        // the PNG encode to Task.Run and write asynchronously.
        File.WriteAllBytes(path, tex.EncodeToPNG());
        Destroy(tex);

        _frameIndex++;
    }

    // ── upload ───────────────────────────────────────────────────────────────────

    private IEnumerator UploadMetadata()
    {
        var metaPath = Path.Combine(_sessionDir, "meta.json");
        var json = File.ReadAllText(metaPath);
        var endpoint = $"{vcoreBaseUrl.TrimEnd('/')}/api/sessions/{_sessionId}/recording";

        Debug.Log($"[VideoRecorder] POST {endpoint}");

        using var req = new UnityWebRequest(endpoint, "POST")
        {
            uploadHandler   = new UploadHandlerRaw(Encoding.UTF8.GetBytes(json)),
            downloadHandler = new DownloadHandlerBuffer(),
        };
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();

        if (req.result == UnityWebRequest.Result.Success)
            Debug.Log($"[VideoRecorder] Upload complete (frames in {_sessionDir})");
        else
            Debug.LogWarning(
                $"[VideoRecorder] Upload failed ({req.responseCode}): {req.error}\n" +
                $"Frames saved locally at {_sessionDir}");
    }

    // ── meta DTO ─────────────────────────────────────────────────────────────────

    private class SessionMeta
    {
        [JsonProperty("session_id")]    public string SessionId    { get; set; }
        [JsonProperty("lsl_start_time")] public string LslStartTime { get; set; }
        [JsonProperty("fps")]           public int    Fps          { get; set; }
        [JsonProperty("width")]         public int    Width        { get; set; }
        [JsonProperty("height")]        public int    Height       { get; set; }
        [JsonProperty("started_at")]    public string StartedAt    { get; set; }
    }
}
