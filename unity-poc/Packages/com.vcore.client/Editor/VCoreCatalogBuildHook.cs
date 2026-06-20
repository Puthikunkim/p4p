using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace VCore.Editor
{
    /// <summary>
    /// Re-bakes the project-wide catalog automatically at the start of every player build,
    /// so a shipped build always carries an up-to-date <c>Assets/Resources/VCoreCatalog.json</c>
    /// without anyone remembering to run <b>V-CORE ▸ Bake Project Catalog</b> by hand.
    ///
    /// Failures are logged but do not abort the build — a stale/absent catalog only affects
    /// authoring against not-yet-loaded scenes, never the live adaptation loop.
    /// </summary>
    public class VCoreCatalogBuildHook : IPreprocessBuildWithReport
    {
        public int callbackOrder => 0;

        public void OnPreprocessBuild(BuildReport report)
        {
            try
            {
                VCoreCatalogBaker.BakeToFile();
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[VCore] Catalog auto-bake skipped (build continues): {ex.Message}");
            }
        }
    }
}
