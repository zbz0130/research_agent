/*
 * Browser-only runtime configuration.
 *
 * This file deliberately contains no credentials. WishForge no longer ships
 * the product through GitHub Pages: a normal checkout leaves `apiBaseUrl`
 * empty and uses the same-origin local FastAPI server. The desktop shell can
 * later inject a loopback sidecar address at runtime without storing keys here.
 */
window.WISHFORGE_RUNTIME_CONFIG = Object.freeze({
  apiBaseUrl: "",
  desktop: false,
});

// Keep the concise alias for integrations that only need the API root.
window.WISHFORGE_API_BASE_URL = window.WISHFORGE_RUNTIME_CONFIG.apiBaseUrl;
