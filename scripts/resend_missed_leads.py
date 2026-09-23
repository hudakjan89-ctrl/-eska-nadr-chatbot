#!/usr/bin/env python3
"""
Doposlanie leadov z analytics.db na e-mailové adresy klienta.

Použitie na produkčnom serveri (kde je DB na /data/analytics.db):
  cd /path/to/repo
  DATA_DIR=/var/lib/ceskanadrz-chatbot/data python scripts/resend_missed_leads.py --dry-run
  DATA_DIR=/var/lib/ceskanadrz-chatbot/data python scripts/resend_missed_leads.py --since 2025-06-01

V Docker kontajneri:
  docker compose exec chatbot python scripts/resend_missed_leads.py --since 2025-06-01
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from logger import DB_PATH, fetch_lead_messages, load_session_transcript
from mailer import _target_emails, resend_configured, send_lead_email, smtp_configured


def _pick_leads_per_session(rows: list[dict]) -> list[dict]:
    """Jeden lead na session — preferuje plný formulár pred pasívnym záchytom."""
    by_session: dict[str, dict] = {}
    for row in rows:
        session_id = row["session_id"]
        is_full = "[KONTAKTNÍ FORMULÁŘ]" in row["content"]
        existing = by_session.get(session_id)
        if existing is None:
            by_session[session_id] = row
            continue
        existing_is_full = "[KONTAKTNÍ FORMULÁŘ]" in existing["content"]
        if is_full and not existing_is_full:
            by_session[session_id] = row
        elif is_full == existing_is_full and row["id"] > existing["id"]:
            by_session[session_id] = row
    return sorted(by_session.values(), key=lambda item: item["id"])


async def _resend_leads(
    *,
    since: str | None,
    until: str | None,
    dry_run: bool,
    delay_seconds: float,
    subject_prefix: str,
) -> int:
    rows = fetch_lead_messages(since=since, until=until)
    leads = _pick_leads_per_session(rows)
    targets = _target_emails()

    print(f"DB: {DB_PATH}")
    print(f"Cieľové e-maily: {', '.join(targets) if targets else '(žiadne)'}")
    print(f"Nájdených lead správ: {len(rows)} → unikátnych session: {len(leads)}")
    if since:
        print(f"Filter od: {since}")
    if until:
        print(f"Filter do: {until}")

    if not leads:
        print("Žiadne leady na doposlanie.")
        return 0

    if dry_run:
        print("\n--dry-run: e-maily sa neodosielajú\n")
        for lead in leads:
            print(
                f"- id={lead['id']} session={lead['session_id']} "
                f"time={lead['timestamp']} {lead['content'][:120]}..."
            )
        return 0

    if not (resend_configured() or smtp_configured()):
        print(
            "CHYBA: Nie je nakonfigurovaný RESEND_API_KEY ani SMTP — "
            "nastavte env premenné pred doposlaním.",
            file=sys.stderr,
        )
        return 1

    sent = 0
    failed = 0
    for index, lead in enumerate(leads, start=1):
        session_id = lead["session_id"]
        history = load_session_transcript(session_id, include_lead_messages=True)
        print(
            f"[{index}/{len(leads)}] Odosielam lead id={lead['id']} "
            f"session={session_id} ({lead['timestamp']})..."
        )
        ok = await send_lead_email(
            lead["content"],
            history,
            subject_prefix=subject_prefix,
            session_id=session_id,
        )
        if ok:
            sent += 1
            print("  OK")
        else:
            failed += 1
            print("  ZLYHALO", file=sys.stderr)
        if delay_seconds > 0 and index < len(leads):
            await asyncio.sleep(delay_seconds)

    print(f"\nHotovo: odoslané={sent}, zlyhané={failed}")
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Doposlanie leadov z analytics.db")
    parser.add_argument(
        "--since",
        help="Dátum od (YYYY-MM-DD), napr. 2025-06-01",
    )
    parser.add_argument(
        "--until",
        help="Dátum do (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Len vypísať leady bez odoslania",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Pauza medzi e-mailmi v sekundách (default 1.5)",
    )
    parser.add_argument(
        "--subject-prefix",
        default="[DOPLNĚNÍ] ",
        help="Predpona predmetu e-mailu (default: [DOPLNĚNÍ] )",
    )
    args = parser.parse_args()

    return asyncio.run(
        _resend_leads(
            since=args.since,
            until=args.until,
            dry_run=args.dry_run,
            delay_seconds=max(0.0, args.delay),
            subject_prefix=args.subject_prefix,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
