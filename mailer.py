import os
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
import logging
import asyncio
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger("ceska_nadrz.mailer")

DEFAULT_TARGET_EMAILS = [
    "obchod@ceskanadrz.cz",
    "info@ceskanadrz.cz",
    "janhudak748@gmail.com",
]

RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
HTTP_MAX_ATTEMPTS = int(os.getenv("LEAD_EMAIL_HTTP_RETRIES", "4"))
SMTP_MAX_ATTEMPTS = int(os.getenv("LEAD_EMAIL_SMTP_RETRIES", "2"))

OUTBOX_RETRY_DELAYS_SEC = [
    60,
    120,
    300,
    600,
    1800,
    3600,
    7200,
    14400,
    28800,
    43200,
]


@dataclass
class DeliveryResult:
    ok: bool
    channel: str = ""
    delivered_to: list[str] = field(default_factory=list)
    failed_to: list[str] = field(default_factory=list)
    last_error: str = ""


def _target_emails() -> list:
    targets_raw = os.getenv("LEAD_TARGET_EMAILS", "").strip()
    if targets_raw:
        raw = [e.strip() for e in targets_raw.split(",") if e.strip()]
    else:
        raw = list(DEFAULT_TARGET_EMAILS)

    seen: set[str] = set()
    deduped: list[str] = []
    for email in raw:
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(email)
    return deduped


def _from_email() -> str:
    return (
        os.getenv("RESEND_FROM_EMAIL", "").strip()
        or os.getenv("FROM_EMAIL", "").strip()
        or os.getenv("SMTP_USER", "").strip()
        or "Ceska Nadrz Chatbot <onboarding@resend.dev>"
    )


def _extract_email_address(from_header: str) -> str:
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1).strip().lower()
    return from_header.strip().lower()


def resend_configured() -> bool:
    return bool(os.getenv("RESEND_API_KEY", "").strip())


def smtp_configured() -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    return bool(host and user and password)


def discord_configured() -> bool:
    return bool(os.getenv("DISCORD_WEBHOOK_URL", "").strip())


def webhook_configured() -> bool:
    return bool(os.getenv("LEAD_WEBHOOK_URL", "").strip())


def email_delivery_configured() -> bool:
    return resend_configured() or smtp_configured() or webhook_configured()


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


def _build_lead_body(lead_data: str, chat_history: list) -> str:
    return f"""Dobrý den,

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


async def _sleep_backoff(attempt: int, base: float = 1.0, cap: float = 30.0):
    delay = min(cap, base * (2 ** attempt))
    await asyncio.sleep(delay)


async def _http_post_json(url: str, *, headers: dict, json_payload: dict, timeout: float) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(HTTP_MAX_ATTEMPTS):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=json_payload,
                    timeout=timeout,
                )
            if response.status_code in RETRYABLE_HTTP_STATUS and attempt < HTTP_MAX_ATTEMPTS - 1:
                logger.warning(
                    "HTTP %s %s — pokus %d/%d, opakujem…",
                    response.status_code,
                    url,
                    attempt + 1,
                    HTTP_MAX_ATTEMPTS,
                )
                await _sleep_backoff(attempt)
                continue
            return response
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_exc = exc
            if attempt < HTTP_MAX_ATTEMPTS - 1:
                logger.warning(
                    "HTTP sieťová chyba (%s) — pokus %d/%d, opakujem…",
                    exc,
                    attempt + 1,
                    HTTP_MAX_ATTEMPTS,
                )
                await _sleep_backoff(attempt)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("HTTP POST zlyhal bez odpovede")


async def _send_via_resend_one(subject: str, body: str, to_address: str) -> tuple[bool, str]:
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False, "RESEND_API_KEY nie je nastavený"

    payload = {
        "from": _from_email(),
        "to": [to_address],
        "subject": subject,
        "text": body,
    }
    try:
        response = await _http_post_json(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json_payload=payload,
            timeout=45.0,
        )
    except Exception as exc:
        logger.exception("Resend výnimka pri odosielaní na %s", to_address)
        return False, str(exc)

    if response.status_code in (200, 201):
        logger.info("E-mail [%s] odoslaný cez Resend na: %s", subject, to_address)
        return True, ""

    error_text = response.text[:500]
    logger.error("Resend odmietol %s (%s): %s", to_address, response.status_code, error_text)
    return False, f"HTTP {response.status_code}: {error_text}"


async def _send_via_resend(subject: str, body: str, to_addresses: list) -> DeliveryResult:
    delivered: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    for address in to_addresses:
        ok, err = await _send_via_resend_one(subject, body, address)
        if ok:
            delivered.append(address)
        else:
            failed.append(address)
            if err:
                errors.append(f"{address}: {err}")

    return DeliveryResult(
        ok=len(failed) == 0 and bool(delivered),
        channel="resend",
        delivered_to=delivered,
        failed_to=failed,
        last_error=" | ".join(errors),
    )


async def _send_discord_lead(subject: str, body: str) -> bool:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return False

    text = body if len(body) <= 1800 else body[:1800] + "\n…(skrátené)"
    content = f"📩 **{subject}**\n```\n{text}\n```"
    try:
        response = await _http_post_json(
            webhook_url,
            headers={},
            json_payload={"content": content},
            timeout=20.0,
        )
        if response.status_code in (200, 204):
            logger.info("Lead notifikácia odoslaná na Discord webhook.")
            return True
        logger.error("Discord webhook zlyhal (%s): %s", response.status_code, response.text[:300])
        return False
    except Exception:
        logger.exception("Chyba pri odosielaní leadu na Discord")
        return False


async def _send_via_webhook(subject: str, body: str, to_addresses: list, lead_data: str) -> DeliveryResult:
    webhook_url = os.getenv("LEAD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        return DeliveryResult(ok=False, channel="webhook", last_error="LEAD_WEBHOOK_URL nie je nastavený")

    payload = {
        "subject": subject,
        "body": body,
        "lead": format_lead_for_email(lead_data),
        "targets": to_addresses,
        "source": "ceskanadrz-chatbot",
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    try:
        response = await _http_post_json(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json_payload=payload,
            timeout=30.0,
        )
        if response.status_code in (200, 201, 202, 204):
            logger.info("Lead odoslaný cez LEAD_WEBHOOK_URL.")
            return DeliveryResult(ok=True, channel="webhook", delivered_to=list(to_addresses))
        err = f"HTTP {response.status_code}: {response.text[:300]}"
        logger.error("LEAD_WEBHOOK_URL zlyhal: %s", err)
        return DeliveryResult(ok=False, channel="webhook", last_error=err)
    except Exception as exc:
        logger.exception("LEAD_WEBHOOK_URL výnimka")
        return DeliveryResult(ok=False, channel="webhook", last_error=str(exc))


def _smtp_send_one_sync(
    smtp_host: str,
    port: int,
    smtp_user: str,
    smtp_pass: str,
    from_email: str,
    to_address: str,
    subject: str,
    body: str,
):
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_address

    context = ssl.create_default_context()
    timeout = int(os.getenv("SMTP_TIMEOUT", "45"))
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


async def _send_smtp_one(subject: str, body: str, to_address: str) -> tuple[bool, str]:
    smtp_host, smtp_port, smtp_user, smtp_pass, from_email = _smtp_settings()
    if not smtp_host or not smtp_user or not smtp_pass:
        return False, "SMTP nie je kompletne nakonfigurovaný"

    configured_ports = [smtp_port]
    for fallback in (587, 465, 2525):
        if fallback not in configured_ports:
            configured_ports.append(fallback)

    loop = asyncio.get_running_loop()
    last_error = ""

    for port in configured_ports:
        for attempt in range(SMTP_MAX_ATTEMPTS):
            try:
                await loop.run_in_executor(
                    None,
                    lambda p=port: _smtp_send_one_sync(
                        smtp_host, p, smtp_user, smtp_pass, from_email, to_address, subject, body
                    ),
                )
                logger.info(
                    "E-mail [%s] odoslaný cez SMTP %s:%s na: %s",
                    subject,
                    smtp_host,
                    port,
                    to_address,
                )
                return True, ""
            except (ConnectionRefusedError, OSError) as exc:
                last_error = str(exc)
                if getattr(exc, "errno", None) == 111 or isinstance(exc, ConnectionRefusedError):
                    logger.warning("SMTP %s:%s — connection refused", smtp_host, port)
                    break
                if attempt < SMTP_MAX_ATTEMPTS - 1:
                    await _sleep_backoff(attempt, base=2.0)
                    continue
                logger.exception("Chyba pri odosielaní emailu cez SMTP (%s:%s)", smtp_host, port)
                return False, last_error
            except Exception as exc:
                last_error = str(exc)
                if attempt < SMTP_MAX_ATTEMPTS - 1:
                    await _sleep_backoff(attempt, base=2.0)
                    continue
                logger.exception("Chyba pri odosielaní emailu cez SMTP (%s:%s)", smtp_host, port)
                return False, last_error

    return False, last_error or f"SMTP {smtp_host} nefunguje (skúšané porty: {configured_ports})"


async def _send_smtp_email(subject: str, body: str, to_addresses: list) -> DeliveryResult:
    delivered: list[str] = []
    failed: list[str] = []
    errors: list[str] = []

    for address in to_addresses:
        ok, err = await _send_smtp_one(subject, body, address)
        if ok:
            delivered.append(address)
        else:
            failed.append(address)
            if err:
                errors.append(f"{address}: {err}")

    if failed and not delivered:
        logger.error(
            "SMTP nefunguje pre žiadneho príjemcu — hosting často blokuje outbound 465/587. "
            "Nastavte overenú doménu v Resend (RESEND_API_KEY + RESEND_FROM_EMAIL)."
        )

    return DeliveryResult(
        ok=len(failed) == 0 and bool(delivered),
        channel="smtp",
        delivered_to=delivered,
        failed_to=failed,
        last_error=" | ".join(errors),
    )


async def _deliver_lead_email(subject: str, body: str, lead_data: str, to_addresses: list) -> DeliveryResult:
    """Skúsi doručiť lead na všetkých príjemcov — per-adresa, s fallback kanálmi."""
    remaining = list(to_addresses)
    all_delivered: list[str] = []
    errors: list[str] = []
    channel_used = ""

    if resend_configured():
        result = await _send_via_resend(subject, body, remaining)
        all_delivered.extend(result.delivered_to)
        remaining = result.failed_to
        if result.delivered_to:
            channel_used = "resend"
        if result.last_error:
            errors.append(result.last_error)
        if not remaining:
            return DeliveryResult(ok=True, channel=channel_used, delivered_to=all_delivered)

    if remaining and smtp_configured():
        result = await _send_smtp_email(subject, body, remaining)
        all_delivered.extend(result.delivered_to)
        remaining = result.failed_to
        if result.delivered_to:
            channel_used = channel_used or "smtp"
        if result.last_error:
            errors.append(result.last_error)
        if not remaining:
            return DeliveryResult(ok=True, channel=channel_used, delivered_to=all_delivered)

    if remaining and webhook_configured():
        result = await _send_via_webhook(subject, body, to_addresses, lead_data)
        if result.ok:
            return DeliveryResult(
                ok=True,
                channel="webhook",
                delivered_to=list(to_addresses),
            )
        errors.append(result.last_error)

    return DeliveryResult(
        ok=False,
        channel=channel_used,
        delivered_to=all_delivered,
        failed_to=remaining or list(to_addresses),
        last_error=" | ".join(errors) if errors else "Neznáma chyba doručenia",
    )


async def audit_email_configuration() -> list[str]:
    """Pri štarte vypíše varovania — neúspešné doručenie leadov."""
    warnings: list[str] = []
    targets = _target_emails()
    if not targets:
        warnings.append("LEAD_TARGET_EMAILS je prázdne — leady nemajú kam ísť.")

    from_header = _from_email()
    from_addr = _extract_email_address(from_header)
    if resend_configured() and "resend.dev" in from_addr:
        warnings.append(
            "RESEND_FROM_EMAIL používa testovaciu doménu @resend.dev — "
            "Resend doručí e-maily LEN na adresu vlastníka účtu, NIE na obchod@/info@. "
            "Nastavte RESEND_FROM_EMAIL z overenej domény (napr. obchod@ceskanadrz.cz)."
        )

    if resend_configured():
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.resend.com/domains",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=20.0,
                )
            if response.status_code == 401:
                warnings.append("RESEND_API_KEY je neplatný (401 Unauthorized).")
            elif response.status_code == 200:
                data = response.json().get("data") or []
                verified_domains = {
                    (item.get("name") or "").lower()
                    for item in data
                    if (item.get("status") or "").lower() == "verified"
                }
                from_domain = from_addr.split("@")[-1] if "@" in from_addr else ""
                if from_domain and from_domain not in verified_domains and "resend.dev" not in from_domain:
                    warnings.append(
                        f"Doména odosielateľa '{from_domain}' nie je v Resend overená "
                        f"(overené: {', '.join(sorted(verified_domains)) or 'žiadne'}). "
                        "E-maily budú padať, kým doménu neoveríte v Resend dashboarde."
                    )
        except Exception as exc:
            warnings.append(f"Nepodarilo sa overiť Resend domény: {exc}")

    if not (resend_configured() or smtp_configured() or webhook_configured()):
        warnings.append(
            "Lead e-maily nie sú nakonfigurované — nastavte aspoň RESEND_API_KEY "
            "(odporúčané) alebo funkčné SMTP / LEAD_WEBHOOK_URL."
        )
    elif smtp_configured() and not resend_configured():
        warnings.append(
            "Používate len SMTP — na Docker/Contabo hostingu býva outbound port 587/465 zablokovaný. "
            "Odporúčame RESEND_API_KEY + overenú doménu."
        )

    return warnings


def outbox_retry_delay(attempts: int) -> int:
    if attempts < len(OUTBOX_RETRY_DELAYS_SEC):
        return OUTBOX_RETRY_DELAYS_SEC[attempts]
    return OUTBOX_RETRY_DELAYS_SEC[-1]


async def process_lead_email_outbox(limit: int = 15) -> int:
    """
    Spracuje čakajúce leady z outboxu (SQLite). Vráti počet úspešne doručených.
    """
    from logger import (
        fetch_outbox_ready_for_retry,
        mark_lead_outbox_delivered,
        load_session_transcript,
        session_lead_email_delivered,
    )

    rows = fetch_outbox_ready_for_retry(limit=limit)
    if not rows:
        return 0

    sent_count = 0
    for row in rows:
        session_id = row["session_id"]
        if session_lead_email_delivered(session_id):
            mark_lead_outbox_delivered(session_id)
            continue

        history = load_session_transcript(session_id, include_lead_messages=True)
        prefix = row.get("subject_prefix") or ""
        if row.get("attempts", 0) > 0 and not prefix.startswith("[OPAKOVANIE]"):
            prefix = f"[OPAKOVANIE] {prefix}".strip()

        ok = await send_lead_email(
            row["lead_content"],
            history,
            subject_prefix=prefix,
            session_id=session_id,
            skip_outbox_enqueue=True,
        )
        if ok:
            sent_count += 1
    return sent_count


async def send_lead_email(
    lead_data: str,
    chat_history: list,
    *,
    subject_prefix: str = "",
    session_id: str | None = None,
    skip_outbox_enqueue: bool = False,
) -> bool:
    """
    Odošle lead e-mailom na LEAD_TARGET_EMAILS / predvolené adresy.
    Priorita doručenia: Resend (HTTP, per príjemca) → SMTP → LEAD_WEBHOOK_URL.
    Discord webhook je len interná záloha pre ops — NIE je považovaný za doručenie klientovi.
    """
    from logger import (
        upsert_lead_email_outbox,
        mark_lead_outbox_delivered,
        session_lead_email_delivered,
        emit_event,
        record_lead_outbox_failure,
    )

    target_emails = _target_emails()
    if not target_emails:
        logger.error("Lead sa nepodarilo odoslať — chýba zoznam LEAD_TARGET_EMAILS.")
        return False

    if session_id and session_lead_email_delivered(session_id):
        logger.info("Lead pre session %s už bol doručený — preskakujem.", session_id)
        mark_lead_outbox_delivered(session_id)
        return True

    subject = f"{subject_prefix}NOVÝ KONTAKT z Chatbota!"
    body = _build_lead_body(lead_data, chat_history)

    result = await _deliver_lead_email(subject, body, lead_data, target_emails)
    email_sent = result.ok

    if email_sent:
        if session_id:
            emit_event(
                "lead_email_delivered",
                session_id=session_id,
                metadata={
                    "targets": target_emails,
                    "channel": result.channel,
                },
            )
            mark_lead_outbox_delivered(session_id)
        if discord_configured():
            await _send_discord_lead(subject, body)
        return True

    logger.error(
        "Lead sa nepodarilo doručiť e-mailom na %s — %s",
        ", ".join(target_emails),
        result.last_error or "skontrolujte RESEND_API_KEY / SMTP / overenú doménu.",
    )

    if session_id:
        if skip_outbox_enqueue:
            record_lead_outbox_failure(session_id, result.last_error or "doručenie zlyhalo")
        else:
            upsert_lead_email_outbox(
                session_id,
                lead_data,
                subject_prefix=subject_prefix,
                last_error=result.last_error,
            )

    if discord_configured():
        await _send_discord_lead(
            f"⚠️ E-MAIL LEADU ZLYHAL — {subject}",
            f"Lead sa nepodarilo doručiť e-mailom na: {', '.join(target_emails)}\n\n{body}",
        )
    return False


async def bootstrap_lead_delivery() -> None:
    """Synchronizuje zmeškané leady do outboxu a hneď skúsi doručiť."""
    from logger import sync_undelivered_leads_to_outbox

    added = sync_undelivered_leads_to_outbox()
    if added:
        logger.info("Do fronty lead e-mailov pridaných %d zmeškaných session.", added)
    delivered = await process_lead_email_outbox(limit=25)
    if delivered:
        logger.info("Z fronty lead e-mailov doručených %d leadov.", delivered)
