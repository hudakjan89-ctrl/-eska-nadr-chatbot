import os
import re
import smtplib
import ssl
from email.message import EmailMessage
import logging
import asyncio

import httpx

logger = logging.getLogger("ceska_nadrz.mailer")

DEFAULT_TARGET_EMAILS = [
    "obchod@ceskanadrz.cz",
    "info@ceskanadrz.cz",
    "janhudak748@gmail.com",
]


def _target_emails() -> list:
    targets_raw = os.getenv("LEAD_TARGET_EMAILS", "").strip()
    if targets_raw:
        return [e.strip() for e in targets_raw.split(",") if e.strip()]
    return list(DEFAULT_TARGET_EMAILS)


def _from_email() -> str:
    return (
        os.getenv("RESEND_FROM_EMAIL", "").strip()
        or os.getenv("FROM_EMAIL", "").strip()
        or os.getenv("SMTP_USER", "").strip()
        or "Chatbot Česká Nádrž <onboarding@resend.dev>"
    )


def resend_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY", "").strip())


def smtp_configured() -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    return bool(host and user and password)


def discord_configured() -> bool:
    return bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip())


def email_delivery_configured() -> bool:
    return resend_configured() or smtp_configured() or discord_configured()


def _smtp_settings():
    """Načíta SMTP nastavenia pri každom odoslaní."""
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "587").strip() or "587"
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    from_email = os.getenv("FROM_EMAIL", user).strip() or user
    try:
        port = int(port_raw)
    except ValueError:
        logger.error("Neplatný SMTP_PORT=%r, používam 587", port_raw)
        port = 587
    return host, port, user, password, from_email


def _strip_bot_instructions(text: str) -> str:
    """Odstráni interné inštrukcie pre AI z hidden správ formulára."""
    text = re.sub(
        r"\.\s*Zákazník právě vyplnil formulář\..*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"\.\s*Toto je tiše odchycený nedokončený lead.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return text.strip()


def format_lead_for_email(lead_data: str) -> str:
    """Čistý text leadu pre email/Discord bez bot inštrukcií."""
    text = _strip_bot_instructions(lead_data)
    if text.startswith("[KONTAKTNÍ FORMULÁŘ]"):
        return "Typ: Kontaktní formulář\n" + text.replace("[KONTAKTNÍ FORMULÁŘ] ", "", 1)
    if text.startswith("[PASIVNÍ ZÁCHYT KONTAKTU]"):
        return "Typ: Pasivní záchyt (nedokončený formulář)\n" + text.replace(
            "[PASIVNÍ ZÁCHYT KONTAKTU] ", "", 1
        )
    return text


def format_history_to_text(chat_history: list) -> str:
    """Prevedie historiu konverzácie do čitateľného plain-text pre email."""
    if not chat_history:
        return "Historie konverzace je prázdná."

    lines = []
    for msg in chat_history:
        role = "Zákazník" if msg["role"] == "user" else "Asistent"
        content = _strip_bot_instructions(msg["content"]).replace("\n", " ")
        if content.startswith("[KONTAKTNÍ FORMULÁŘ]"):
            content = format_lead_for_email(content)
        elif content.startswith("[PASIVNÍ ZÁCHYT KONTAKTU]"):
            content = format_lead_for_email(content)
        lines.append(f"[{role}]: {content}")

    return "\n".join(lines)


async def _send_via_resend(subject: str, body: str, to_addresses: list) -> bool:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False

    payload = {
        "from": _from_email(),
        "to": to_addresses,
        "subject": subject,
        "text": body,
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30.0,
            )
        if response.status_code in (200, 201):
            logger.info("E-mail [%s] odoslaný cez Resend na: %s", subject, ", ".join(to_addresses))
            return True
        logger.error("Resend API odmietlo odoslanie (%s): %s", response.status_code, response.text)
        return False
    except Exception:
        logger.exception("Chyba pri odosielaní emailu cez Resend API")
        return False


async def _send_discord_lead(subject: str, body: str) -> bool:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    text = body if len(body) <= 1800 else body[:1800] + "\n…(skrátené)"
    content = f"📩 **{subject}**\n```\n{text}\n```"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                webhook_url,
                json={"content": content},
                timeout=15.0,
            )
        if response.status_code in (200, 204):
            logger.info("Lead notifikácia odoslaná na Discord webhook.")
            return True
        logger.error("Discord webhook zlyhal (%s): %s", response.status_code, response.text)
        return False
    except Exception:
        logger.exception("Chyba pri odosielaní leadu na Discord")
        return False


async def _send_smtp_email(subject: str, body: str, to_addresses: list) -> bool:
    """SMTP — na mnohých Docker hostoch je outbound port 465/587 zablokovaný."""
    smtp_host, smtp_port, smtp_user, smtp_pass, from_email = _smtp_settings()
    if not smtp_host or not smtp_user or not smtp_pass:
        return False

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_addresses)

    def send_on_port(port: int):
        context = ssl.create_default_context()
        timeout = int(os.getenv("SMTP_TIMEOUT", "30"))
        if port == 465:
            with smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=timeout) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, port, timeout=timeout) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

    alternate_port = 587 if smtp_port == 465 else 465
    loop = asyncio.get_running_loop()
    for port in (smtp_port, alternate_port):
        try:
            await loop.run_in_executor(None, lambda p=port: send_on_port(p))
            logger.info("E-mail [%s] odoslaný cez SMTP %s:%s na: %s", subject, smtp_host, port, msg["To"])
            return True
        except (ConnectionRefusedError, OSError) as e:
            if getattr(e, "errno", None) == 111 or isinstance(e, ConnectionRefusedError):
                logger.warning("SMTP %s:%s — connection refused", smtp_host, port)
                continue
            logger.exception("Chyba pri odosielaní emailu cez SMTP (%s:%s)", smtp_host, port)
            return False
        except Exception:
            logger.exception("Chyba pri odosielaní emailu cez SMTP (%s:%s)", smtp_host, port)
            return False

    logger.error(
        "SMTP %s nefunguje (porty %s/%s). Hosting blokuje odchádzajúci SMTP — "
        "nastavte RESEND_API_KEY (odporúčané) alebo DISCORD_WEBHOOK_URL.",
        smtp_host, smtp_port, alternate_port,
    )
    return False


async def send_lead_email(lead_data: str, chat_history: list) -> bool:
    """
    Odošle lead. Priorita: Resend (HTTP) → SMTP → Discord webhook.
    """
    target_emails = _target_emails()
    subject = "NOVÝ KONTAKT z Chatbota!"
    body = f"""Dobrý den,

chatbot na webu zaznamenal nový kontakt.

DETAILY KONTAKTU / POŽADAVEK:
-----------------------------------------
{format_lead_for_email(lead_data)}
-----------------------------------------

TRANSKRIPT CELÉ KONVERZACE:
-----------------------------------------
{format_history_to_text(chat_history)}
-----------------------------------------

(Tato zpráva je generována automaticky Česká Nádrž Botem.)
"""

    if resend_configured():
        if await _send_via_resend(subject, body, target_emails):
            return True
        logger.warning("Resend zlyhal, skúšam záložné kanály…")

    if smtp_configured():
        if await _send_smtp_email(subject, body, target_emails):
            return True
        logger.warning("SMTP zlyhal, skúšam Discord…")

    if discord_configured():
        return await _send_discord_lead(subject, body)

    logger.error(
        "Lead sa nepodarilo odoslať — nastavte RESEND_API_KEY (email cez HTTPS) "
        "alebo DISCORD_WEBHOOK_URL (okamžitá záloha)."
    )
    return False
