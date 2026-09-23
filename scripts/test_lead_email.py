#!/usr/bin/env python3
"""
Surový test doručenia lead e-mailu (SMTP / Resend z app_config.py).

Príklady:
  python scripts/test_lead_email.py
  python scripts/test_lead_email.py --to janhudak748@gmail.com
  python scripts/test_lead_email.py --all-targets
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_config
from mailer import (
    _deliver_lead_email,
    _send_smtp_one,
    audit_email_configuration,
    resend_configured,
    smtp_configured,
)


async def run_test(*, to: str | None, all_targets: bool) -> int:
    print("=== Test lead e-mailu ===")
    print(f"SMTP: {app_config.SMTP_HOST}:{app_config.SMTP_PORT} user={app_config.SMTP_USER}")
    print(f"From: {app_config.FROM_EMAIL}")
    print(f"Resend configured: {resend_configured()}")
    print(f"SMTP configured: {smtp_configured()}")
    for w in await audit_email_configuration():
        print(f"  WARN: {w}")

    if all_targets:
        recipients = app_config.effective_target_emails()
    elif to:
        recipients = [to.strip()]
    else:
        recipients = ["janhudak748@gmail.com"]

    subject = f"[TEST CHATBOT] Lead e-mail {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    body = (
        "Toto je automatický test odosielania leadov z Česká Nádrž chatbota.\n\n"
        "Ak tento e-mail vidíte, SMTP/Resend funguje.\n"
    )
    lead_data = "[KONTAKTNÍ FORMULÁŘ] E-mail: test@test.cz, Jméno: Test Bot"

    print(f"\nOdosielam na: {', '.join(recipients)}")

    # Najprv priamy SMTP test na prvého príjemcu (rýchla diagnostika)
    smtp_ok, smtp_err = await _send_smtp_one(subject, body, recipients[0])
    print(f"SMTP priamy test → {recipients[0]}: {'OK' if smtp_ok else 'ZLYHALO'}")
    if smtp_err:
        print(f"  Chyba: {smtp_err}")

    result = await _deliver_lead_email(subject, body, lead_data, recipients)
    print(f"\nCelkové doručenie ({result.channel or '—'}): {'OK' if result.ok else 'ZLYHALO'}")
    if result.delivered_to:
        print(f"  Doručené: {', '.join(result.delivered_to)}")
    if result.failed_to:
        print(f"  Zlyhané: {', '.join(result.failed_to)}")
    if result.last_error:
        print(f"  Detail: {result.last_error[:500]}")

    return 0 if result.ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test odoslania lead e-mailu")
    parser.add_argument(
        "--to",
        help="Jeden príjemca (predvolene janhudak748@gmail.com)",
    )
    parser.add_argument(
        "--all-targets",
        action="store_true",
        help="Odoslať na všetkých z app_config.LEAD_TARGET_EMAILS",
    )
    args = parser.parse_args()
    return asyncio.run(run_test(to=args.to, all_targets=args.all_targets))


if __name__ == "__main__":
    raise SystemExit(main())
