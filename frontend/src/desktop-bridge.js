/*
 * A deliberately small boundary between the web UI and the Tauri shell.
 *
 * Importing this module in a normal browser must remain safe: the product is
 * still useful as a local Vite/FastAPI development app, and browser builds do
 * not have a Tauri IPC transport.  The bridge therefore exposes the same
 * shape in both environments and only imports the Tauri package after a
 * runtime check succeeds.
 */

const browserBridge = Object.freeze({
  isDesktop: false,
  runtimeConfig: null,
  async getRuntimeConfig() { return null; },
  async setCredential() { return null; },
  async getCredentialStatus() { return null; },
  async saveRuntimeSettings() { return null; },
  async saveProviderRuntimeSettings() { return null; },
});

function hasTauriRuntime() {
  return Boolean(window.__TAURI_INTERNALS__ || window.__TAURI__);
}

function applyRuntimeConfig(config) {
  const apiBaseUrl = String(config?.api_base_url || config?.apiBaseUrl || "").replace(/\/+$/, "");
  const current = window.WISHFORGE_RUNTIME_CONFIG || {};
  window.WISHFORGE_RUNTIME_CONFIG = Object.freeze({
    ...current,
    apiBaseUrl,
    appVersion: String(config?.version || current.appVersion || ""),
    desktop: true,
  });
  window.WISHFORGE_API_BASE_URL = apiBaseUrl;
}

async function createDesktopBridge() {
  if (!hasTauriRuntime()) {
    window.WishForgeDesktop = browserBridge;
    return browserBridge;
  }

  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const runtimeConfig = await invoke("get_runtime_config");
    applyRuntimeConfig(runtimeConfig);

    const desktopBridge = Object.freeze({
      isDesktop: true,
      runtimeConfig,
      getRuntimeConfig: async () => invoke("get_runtime_config"),
      setCredential: async (slot, value) => invoke("set_credential", { slot, value }),
      getCredentialStatus: async (slot) => invoke("get_credential_status", { slot }),
      saveRuntimeSettings: async ({ provider, model, baseUrl, demoMode = null }) => invoke(
        "save_desktop_runtime_settings",
        { provider, model, baseUrl, demoMode },
      ),
      saveProviderRuntimeSettings: async (slot, { provider, model, base_url: baseUrl, enabled }) => invoke(
        "save_desktop_provider_settings",
        { slot, provider, model, baseUrl, enabled },
      ),
    });
    window.WishForgeDesktop = desktopBridge;
    return desktopBridge;
  } catch (error) {
    // A partially initialized or unavailable desktop shell should leave the
    // browser-style app usable.  Deliberately omit secrets and IPC arguments
    // from this diagnostic.
    console.warn("WishForge desktop bridge is unavailable; using browser fallback.", error);
    window.WishForgeDesktop = browserBridge;
    return browserBridge;
  }
}

// Expose a synchronous, safe fallback immediately.  `main.js` awaits this
// promise before importing app.js, so normal page startup sees the final
// bridge and loopback sidecar address.
window.WishForgeDesktop = browserBridge;
export const desktopBridgeReady = createDesktopBridge();
