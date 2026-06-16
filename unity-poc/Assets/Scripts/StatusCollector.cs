using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;
using UnityEngine;

namespace VCore
{
    /// <summary>
    /// Scans the scene for all <see cref="ObjectStatus"/> components and builds the
    /// Object-Status Manifest (Contract 3b) that is sent to V-CORE on connect.
    ///
    /// Attach to the same GameObject as <see cref="VCoreConnection"/>.
    /// </summary>
    [RequireComponent(typeof(VCoreConnection))]
    public class StatusCollector : MonoBehaviour
    {
        [Tooltip("Scene name included in the manifest (e.g. calm_forest).")]
        public string sceneName = "sample_scene";

        [Tooltip("Runtime identifier included in the manifest.")]
        public string runtimeId = "jerry-unity";

        // ── public API ──────────────────────────────────────────────────────────────

        /// <summary>
        /// The manifest wrapped in its typed envelope
        /// (<c>{"type":"object_status_manifest","payload":…}</c>) — the wire format
        /// V-CORE expects for the initial handshake and any mid-session re-send
        /// (e.g. on a scene change).
        /// </summary>
        public string BuildManifestEnvelopeJson()
        {
            var envelope = new Dictionary<string, object>
            {
                ["type"] = "object_status_manifest",
                ["payload"] = BuildManifest(),
            };
            return JsonConvert.SerializeObject(envelope, _settings);
        }

        // ── internal ────────────────────────────────────────────────────────────────

        private static readonly JsonSerializerSettings _settings = new()
        {
            ContractResolver = new DefaultContractResolver
            {
                NamingStrategy = new SnakeCaseNamingStrategy(),
            },
            NullValueHandling = NullValueHandling.Ignore,
        };

        internal ManifestPayload BuildManifest()
        {
            var all = FindObjectsByType<ObjectStatus>(FindObjectsSortMode.None);

            // Group components by EffectiveId so multiple statuses on the same
            // GameObject collapse into one object declaration.
            var groups = all
                .GroupBy(s => s.EffectiveId)
                .ToDictionary(g => g.Key, g => g.ToList());

            var objects = new List<ObjectDeclaration>();
            foreach (var kvp in groups)
            {
                var representative = kvp.Value[0];
                objects.Add(new ObjectDeclaration
                {
                    Id = kvp.Key,
                    Tags = representative.tags ?? Array.Empty<string>(),
                    Statuses = kvp.Value.Select(ToStatusDecl).ToList(),
                });
            }

            return new ManifestPayload
            {
                SchemaVersion = "1.0.0",
                Scene = sceneName,
                Runtime = runtimeId,
                Objects = objects,
                AbstractActions = new List<object>(),
            };
        }

        private static StatusDeclaration ToStatusDecl(ObjectStatus s)
        {
            if (s.type == ObjectStatus.StatusType.Continuous)
            {
                return new StatusDeclaration
                {
                    Name = s.statusName,
                    Type = "continuous",
                    Range = new StatusRange { Min = s.rangeMin, Max = s.rangeMax },
                };
            }
            else
            {
                return new StatusDeclaration
                {
                    Name = s.statusName,
                    Type = "discrete",
                    Values = s.discreteValues,
                };
            }
        }

        // ── payload types (serialised to JSON) ─────────────────────────────────────

        internal class ManifestPayload
        {
            public string SchemaVersion { get; set; }
            public string Scene { get; set; }
            public string Runtime { get; set; }
            public List<ObjectDeclaration> Objects { get; set; }
            public List<object> AbstractActions { get; set; }
        }

        internal class ObjectDeclaration
        {
            public string Id { get; set; }
            public string[] Tags { get; set; }
            public List<StatusDeclaration> Statuses { get; set; }
        }

        internal class StatusDeclaration
        {
            public string Name { get; set; }
            public string Type { get; set; }
            [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
            public string[] Values { get; set; }
            [JsonProperty(NullValueHandling = NullValueHandling.Ignore)]
            public StatusRange Range { get; set; }
        }

        internal class StatusRange
        {
            public float Min { get; set; }
            public float Max { get; set; }
        }
    }
}
