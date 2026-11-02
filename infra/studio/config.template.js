// Baked into SPA for docker-compose. Helm/K8s ConfigMap overrides these in cluster.
window.API_ENDPOINT = "__STUDIO_URL__/api";
window.MS_API_URL = "http://localhost:8000";
window.COPILOT_API_URL = "http://localhost:5050";

// Feature flags — defaults overridden by K8s ConfigMap when labels are active on a PR.
// Added automatically by scripts/make-feature-flag.sh — do not edit by hand.
// window.FEATURE_FLAG_<NAME> = "false";

window.FEATURE_FLAG_SECRETS_MANAGEMENT = "false";
window.FEATURE_FLAG_EVALUATIONS = "false";
window.CURRENT_VERSION_NUMBER = "dev";
