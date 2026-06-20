using System;
using UnityEngine;
using UnityEngine.Events;

namespace VCore
{
    /// <summary>
    /// Declares a parameterless <b>action</b> (command) Unity exposes to V-CORE — the
    /// free-form counterpart to <see cref="ObjectStatus"/>. Where a status sets a value,
    /// an action fires <see cref="OnInvoke"/> and the developer wires that to anything in
    /// the Inspector (a method, coroutine, Timeline, state-machine transition, …).
    ///
    /// Declared in the Object-Status Manifest's <c>abstract_actions</c> by
    /// <see cref="StatusCollector"/>, so the rule builder can target it on the THEN side.
    ///
    /// Scope:
    /// - <see cref="ActionScope.Object"/> — addressed by <see cref="objectId"/> / <see cref="tags"/>,
    ///   exactly like a status. A tag-addressed action fans out to every matching component.
    /// - <see cref="ActionScope.Scene"/> — a global command addressed by <see cref="actionName"/>
    ///   only (no target).
    /// </summary>
    public class VCoreAction : MonoBehaviour
    {
        public enum ActionScope { Object, Scene }

        [Header("Action Declaration")]
        [Tooltip("Name of this action as it appears in rules (e.g. advance_scene, extinguish).")]
        public string actionName = "action";

        [Tooltip("Object: addressed by id/tag like a status. Scene: a global command addressed by name only.")]
        public ActionScope scope = ActionScope.Object;

        [Header("Object Identity (scope = Object)")]
        [Tooltip("Unique ID for this object in the manifest. Leave empty to use the GameObject name.")]
        public string objectId = "";

        [Tooltip("Tags V-CORE rules can address this action by (e.g. ambient_light, fire).")]
        public string[] tags = Array.Empty<string>();

        [Tooltip("Invoked on the main thread when V-CORE fires this action. Wire it to anything.")]
        public UnityEvent OnInvoke = new();

        /// <summary>Effective object ID: explicit field or the GameObject name.</summary>
        public string EffectiveId => string.IsNullOrEmpty(objectId) ? gameObject.name : objectId;

        /// <summary>Called by <see cref="RequestDispatcher"/> when a matching action request arrives.</summary>
        public void Invoke() => OnInvoke.Invoke();
    }
}
