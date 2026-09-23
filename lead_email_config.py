"""
Natvrdo zabudovaná konfigurácia odosielania lead e-mailov.
Nepotrebujete .env pre host, port, príjemcov ani odosielateľa — len voliteľne
heslo/API kľúč ak ich doplníte priamo sem (inak sa na serveri použije existujúci .env).
"""

from __future__ import annotations

import os

# --- Príjemcovia leadov ---
LEAD_TARGET_EMAILS: list[str] = [
    "obchod@ceskanadrz.cz",
    "info@ceskanadrz.cz",
    "janhudak748@gmail.com",
]

# --- Odosielateľ (musí sedieť s overenou doménou v Resend / Shoptet schránkou) ---
FROM_DISPLAY = "Ceska Nadrz Chatbot"
FROM_ADDRESS = "obchod@ceskanadrz.cz"
RESEND_FROM_EMAIL = f"{FROM_DISPLAY} <{FROM_ADDRESS}>"
FROM_EMAIL = RESEND_FROM_EMAIL

# --- Resend (HTTPS — funguje z Dockeru na Contabo) ---
# Doplňte kľúč sem alebo nechajte prázdne a použije sa RESEND_API_KEY z .env na serveri.
RESEND_API_KEY = ""

# --- Shoptet SMTP (schánka obchod@ceskanadrz.cz) ---
SMTP_ENABLED = True
SMTP_HOST = "mbox.myshoptet.com"
SMTP_PORT = 587
SMTP_USER = "obchod@ceskanadrz.cz"
# Heslo k schránke v Shoptet admin → Nastavení → Emaily → E-mailové schránky
SMTP_PASS = ""

# --- Discord (interné upozornenia — nie doručenie klientovi) ---
DISCORD_WEBHOOK_URL = ""

# --- Voliteľná HTTP záloha (Make / Zapier) ---
LEAD_WEBHOOK_URL = ""

# --- Fronta opakovaného odoslania ---
LEAD_EMAIL_RETRY_INTERVAL_MIN = 3
LEAD_EMAIL_RETRY_BATCH = 15
LEAD_EMAIL_HTTP_RETRIES = 4
LEAD_EMAIL_SMTP_RETRIES = 2
SMTP_TIMEOUT = 45


def _from_env(name: str) -> str:
    return os.getenv(name, "").strip()


def effective_resend_api_key() -> str:
    return (RESEND_API_KEY or _from_env("RESEND_API_KEY")).strip()


def effective_smtp_pass() -> str:
    return (SMTP_PASS or _from_env("SMTP_PASS")).strip()


def effective_discord_webhook_url() -> str:
    return (DISCORD_WEBHOOK_URL or _from_env("DISCORD_WEBHOOK_URL")).strip()


def effective_lead_webhook_url() -> str:
    return (LEAD_WEBHOOK_URL or _from_env("LEAD_WEBHOOK_URL")).strip()


def effective_target_emails() -> list[str]:
    raw = _from_env("LEAD_TARGET_EMAILS")
    if raw:
        return [e.strip() for e in raw.split(",") if e.strip()]
    return list(LEAD_TARGET_EMAILS)
