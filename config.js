window.PORTFOLIO_EDITOR_API_BASE =
  ['127.0.0.1', 'localhost'].includes(window.location.hostname)
    ? "http://127.0.0.1:8787"
    : "https://richiechc.workers.dev";

window.PORTFOLIO_CONTENT_URL = "data/site-content.json";
window.FACTORY_AGENT_API_BASE = "http://127.0.0.1:8000";
