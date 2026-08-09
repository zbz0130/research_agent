/*
 * Browser-only runtime configuration.
 *
 * This file deliberately contains no credentials.  The GitHub Pages workflow
 * replaces `apiBaseUrl` in its published copy from the repository Variable
 * `WISHFORGE_API_BASE_URL`; a local checkout can leave it empty to use the
 * same-origin FastAPI server at http://localhost:8000.
 */
window.WISHFORGE_RUNTIME_CONFIG = Object.freeze({
  apiBaseUrl: "",
});

// Keep the concise alias for integrations that only need the API root.
window.WISHFORGE_API_BASE_URL = window.WISHFORGE_RUNTIME_CONFIG.apiBaseUrl;
