"""
Produkčná konfigurácia chatbota — natvrdo v kóde (Coolify / Contabo).
.env už nie je potrebné pre beh aplikácie.
"""

from __future__ import annotations

# --- LLM (EUrouter) ---
EUROUTER_API_KEY = "eur_hkTu1zNKkXV8.HUDJVhe2mynrYzBoBjXLRTSQWwmUZW3Q"
LLM_API_BASE_URL = "https://api.eurouter.ai/api/v1"
LLM_MODEL = "claude-opus-4-7"
LLM_FALLBACK_MODEL = ""
LLM_RETRY_ATTEMPTS = 4

# --- Admin dashboard ---
DASHBOARD_API_KEY = "90c788538880216ddfe06aee50bd1d2258d0dc450047a5b79b94f7bb5d10c3f0"
DASHBOARD_CACHE_TTL_SECONDS = 7200

# --- Discord (interné alerty) ---
# V UI bolo skrátené „…“ — ak alerty na Discord prestali chodiť, vložte celú URL sem.
DISCORD_WEBHOOK_URL = ""
ALERT_COOLDOWN_SECONDS = 900

# --- GitHub knowledge base ---
# Token bol na screenshote prekrytý notifikáciou — doplňte celý github_pat_… ak sync zlyhá.
GITHUB_TOKEN = ""
GITHUB_OWNER = "hudakjan89-ctrl"
GITHUB_REPO = "ceskanadrz-knowledge"
GITHUB_BRANCH = "main"

# --- Cesty (Docker volume) ---
DATA_DIR = "/data"
ANALYTICS_DB_PATH = "/data/analytics.db"
KNOWLEDGE_LOCAL_PATH = "/data/knowledge_base.md"
KNOWLEDGE_SEED_PATH = "knowledge_seed.md"

# --- Widget / CORS ---
WIDGET_PUBLIC_BASE = "https://nadrz.eniq.eu"
ALLOWED_ORIGINS = "*"

# --- Cloudflare (voliteľné) ---
CLOUDFLARE_ZONE_ID = ""
CLOUDFLARE_API_TOKEN = ""

# --- Lead e-maily ---
LEAD_TARGET_EMAILS: list[str] = [
    "obchod@ceskanadrz.cz",
    "info@ceskanadrz.cz",
    "janhudak748@gmail.com",
]

FROM_EMAIL = "eniqagency@gmail.com"
FROM_DISPLAY = "Ceska Nadrz Chatbot"
RESEND_FROM_EMAIL = f"{FROM_DISPLAY} <{FROM_EMAIL}>"
RESEND_API_KEY = ""

SMTP_ENABLED = True
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "eniqagency@gmail.com"
# Google App Password (4×4 znakov — medzery sa pri odosielaní odstránia)
SMTP_PASS = "xofp ckyb twpt ttdl"

LEAD_WEBHOOK_URL = ""

LEAD_EMAIL_RETRY_INTERVAL_MIN = 3
LEAD_EMAIL_RETRY_BATCH = 15
LEAD_EMAIL_HTTP_RETRIES = 4
LEAD_EMAIL_SMTP_RETRIES = 3
SMTP_TIMEOUT = 45


def normalize_app_password(raw: str) -> str:
    return (raw or "").replace(" ", "").strip()


def effective_resend_api_key() -> str:
    return (RESEND_API_KEY or "").strip()


def effective_smtp_pass() -> str:
    return normalize_app_password(SMTP_PASS)


def effective_discord_webhook_url() -> str:
    return (DISCORD_WEBHOOK_URL or "").strip()


def effective_lead_webhook_url() -> str:
    return (LEAD_WEBHOOK_URL or "").strip()


def effective_target_emails() -> list[str]:
    return list(LEAD_TARGET_EMAILS)


def effective_github_token() -> str:
    return (GITHUB_TOKEN or "").strip()


def allowed_origins_list() -> list[str]:
    return [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()] or ["*"]
