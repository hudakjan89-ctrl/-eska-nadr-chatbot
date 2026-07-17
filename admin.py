from fastapi import APIRouter, HTTPException, Request
import sqlite3
from logger import DB_PATH
import json
import os
import re
import time
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List, Union
from logger import emit_event
from logger import log_message
from knowledge_github import KNOWLEDGE_LOCAL_PATH, is_github_configured, sync_knowledge_base

router = APIRouter(prefix="/admin", tags=["admin"])

DASHBOARD_CACHE_KEY = "dashboard_snapshot_v1"
DASHBOARD_CACHE_TTL_SECONDS = int(os.getenv("DASHBOARD_CACHE_TTL_SECONDS", "7200"))
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

class EventIn(BaseModel):
    event_name: str
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id_hash: Optional[str] = None
    language: Optional[str] = None
    metadata: Optional[dict] = None
    timestamp: Optional[str] = None
    sync_status: Optional[str] = "synced"

class ClientMessageIn(BaseModel):
    session_id: str
    role: str
    content: str
    language: Optional[str] = None
    metadata: Optional[dict] = None
    event_name: Optional[str] = None

def _period_modifier(period: str) -> str:
    period_map = {
        "today": "start of day",
        "week": "-7 day",
        "month": "-30 day"
    }
    return period_map.get(period, "-7 day")

def _category_from_query(query: str) -> str:
    text = (query or "").lower()
    if any(x in text for x in ["cena", "koupit", "objednat", "produkt", "nadrz", "jímk", "jimk", "septik", "čov", "cov"]):
        return "Produkty & Nákup"
    if any(x in text for x in ["jak", "instal", "mont", "pomoc", "porad", "reklam", "servis"]):
        return "Podpora & Pomoc"
    return "Informace"

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _safe_json(value):
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}

def _require_dashboard_api_key(request: Request):
    if not DASHBOARD_API_KEY:
        raise HTTPException(status_code=503, detail="Dashboard API key is not configured.")

    auth_header = request.headers.get("authorization", "")
    bearer_token = auth_header.replace("Bearer ", "", 1).strip() if auth_header.startswith("Bearer ") else ""
    header_token = request.headers.get("x-dashboard-api-key", "").strip()

    if bearer_token != DASHBOARD_API_KEY and header_token != DASHBOARD_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid dashboard API key.")


def _init_dashboard_storage():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS dashboard_cache
           (cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, generated_at DATETIME NOT NULL)"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_timestamp ON messages(session_id, timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_messages_role_timestamp ON messages(role, timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_name_timestamp ON events(event_name, timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_events_session_timestamp ON events(session_id, timestamp)")
    conn.commit()
    conn.close()

def _scalar(c, query, params=()):
    c.execute(query, params)
    row = c.fetchone()
    if row is None:
        return 0
    return row[0] or 0

def _rows(c, query, params=()):
    c.execute(query, params)
    return c.fetchall()

def _extract_lead_data(content: str):
    email_match = re.search(r'E-mail:\s*([^,\s]+)', content or "", re.IGNORECASE)
    name_match = re.search(r'Jméno:\s*([^,.]+)', content or "", re.IGNORECASE)
    phone_match = re.search(r'Telefon:\s*([^,.]+)', content or "", re.IGNORECASE)
    note_match = re.search(r'Poznámka:\s*([^.]*)', content or "", re.IGNORECASE)
    return {
        "email": email_match.group(1).strip() if email_match else None,
        "name": name_match.group(1).strip() if name_match else None,
        "phone": phone_match.group(1).strip() if phone_match else None,
        "note": note_match.group(1).strip() if note_match else None,
        "capture_type": "submitted" if "[KONTAKTNÍ FORMULÁŘ]" in (content or "") else "passive"
    }

def _percent(part, total):
    return round((part / total) * 100, 2) if total else 0.0

def _extract_entry_page_from_metadata(metadata):
    meta = metadata if isinstance(metadata, dict) else _safe_json(metadata)
    if not isinstance(meta, dict):
        return {
            "entry_page_url": None,
            "entry_page_path": None,
            "entry_page_title": None,
            "entry_referrer": None,
            "entry_trigger": None,
        }
    return {
        "entry_page_url": meta.get("page_url"),
        "entry_page_path": meta.get("page_path"),
        "entry_page_title": meta.get("page_title"),
        "entry_referrer": meta.get("referrer"),
        "entry_trigger": meta.get("trigger"),
    }

def _extract_entry_page_from_events(event_rows):
    for row in event_rows:
        if row["event_name"] == "chat_started":
            return _extract_entry_page_from_metadata(row["metadata"])
    return _extract_entry_page_from_metadata({})

_ENTRY_PAGE_SELECT = """
    (SELECT json_extract(e.metadata, '$.page_url')
     FROM events e
     WHERE e.session_id = m.session_id AND e.event_name = 'chat_started'
     ORDER BY e.id ASC LIMIT 1) as entry_page_url,
    (SELECT json_extract(e.metadata, '$.page_path')
     FROM events e
     WHERE e.session_id = m.session_id AND e.event_name = 'chat_started'
     ORDER BY e.id ASC LIMIT 1) as entry_page_path,
    (SELECT json_extract(e.metadata, '$.page_title')
     FROM events e
     WHERE e.session_id = m.session_id AND e.event_name = 'chat_started'
     ORDER BY e.id ASC LIMIT 1) as entry_page_title,
    (SELECT json_extract(e.metadata, '$.referrer')
     FROM events e
     WHERE e.session_id = m.session_id AND e.event_name = 'chat_started'
     ORDER BY e.id ASC LIMIT 1) as entry_referrer,
    (SELECT json_extract(e.metadata, '$.trigger')
     FROM events e
     WHERE e.session_id = m.session_id AND e.event_name = 'chat_started'
     ORDER BY e.id ASC LIMIT 1) as entry_trigger
"""

def _conversation_payload(row):
    return {
        "session_id": row["session_id"],
        "started_at": row["started_at"],
        "last_message_at": row["last_message_at"],
        "message_count": row["message_count"],
        "user_messages": row["user_messages"],
        "bot_messages": row["bot_messages"],
        "has_lead": bool(row["has_lead"]),
        "entry_page_url": row["entry_page_url"],
        "entry_page_path": row["entry_page_path"],
        "entry_page_title": row["entry_page_title"],
        "entry_referrer": row["entry_referrer"],
        "entry_trigger": row["entry_trigger"],
    }

def _build_dashboard_snapshot():
    conn = _connect()
    c = conn.cursor()

    total_conversations = _scalar(c, "SELECT COUNT(DISTINCT session_id) FROM messages")
    total_messages = _scalar(c, "SELECT COUNT(*) FROM messages")
    user_messages = _scalar(c, "SELECT COUNT(*) FROM messages WHERE role='user'")
    bot_messages = _scalar(c, "SELECT COUNT(*) FROM messages WHERE role='bot'")
    events_total = _scalar(c, "SELECT COUNT(*) FROM events")

    today_conversations = _scalar(
        c,
        """SELECT COUNT(DISTINCT session_id) FROM messages
           WHERE datetime(timestamp) >= datetime('now', 'start of day')"""
    )
    week_conversations = _scalar(
        c,
        """SELECT COUNT(DISTINCT session_id) FROM messages
           WHERE datetime(timestamp) >= datetime('now', '-7 day')"""
    )
    month_conversations = _scalar(
        c,
        """SELECT COUNT(DISTINCT session_id) FROM messages
           WHERE datetime(timestamp) >= datetime('now', '-30 day')"""
    )

    event_counts_rows = _rows(
        c,
        """SELECT event_name, COUNT(*) as cnt
           FROM events
           GROUP BY event_name
           ORDER BY cnt DESC"""
    )
    event_counts = {row["event_name"]: row["cnt"] for row in event_counts_rows}

    form_shown = event_counts.get("contact_form_shown", 0)
    contact_submitted = event_counts.get("contact_submitted", 0)
    contact_passive = event_counts.get("contact_captured_passive", 0)
    product_recommended = event_counts.get("product_recommended", 0)
    page_link_shown = event_counts.get("page_link_prompt_shown", 0)
    page_link_yes = event_counts.get("page_link_clicked_yes", 0)
    quick_actions = event_counts.get("quick_actions_shown", 0)

    daily_rows = _rows(
        c,
        """SELECT date(timestamp) as day,
                  COUNT(DISTINCT CASE WHEN event_name='chat_started' THEN session_id END) as conversations,
                  SUM(CASE WHEN event_name IN ('message_user', 'message_bot') THEN 1 ELSE 0 END) as messages,
                  SUM(CASE WHEN event_name IN ('contact_submitted', 'contact_captured_passive') THEN 1 ELSE 0 END) as leads,
                  SUM(CASE WHEN event_name='product_recommended' THEN 1 ELSE 0 END) as product_recommendations,
                  SUM(CASE WHEN event_name='contact_form_shown' THEN 1 ELSE 0 END) as forms_shown
           FROM events
           WHERE datetime(timestamp) >= datetime('now', '-30 day')
           GROUP BY date(timestamp)
           ORDER BY day ASC"""
    )

    top_query_rows = _rows(
        c,
        """SELECT json_extract(metadata, '$.query_text') as query_text, COUNT(*) as cnt
           FROM events
           WHERE event_name='message_user'
             AND json_extract(metadata, '$.query_text') IS NOT NULL
             AND json_extract(metadata, '$.query_text') != ''
           GROUP BY query_text
           ORDER BY cnt DESC
           LIMIT 30"""
    )
    top_queries = [{"query": row["query_text"], "count": row["cnt"], "category": _category_from_query(row["query_text"])} for row in top_query_rows]

    category_counts = {"Informace": 0, "Produkty & Nákup": 0, "Podpora & Pomoc": 0}
    for item in top_queries:
        category_counts[item["category"]] += item["count"]

    product_rows = _rows(
        c,
        """SELECT json_extract(metadata, '$.url') as url,
                  json_extract(metadata, '$.image_url') as image_url,
                  COUNT(*) as cnt,
                  COUNT(DISTINCT session_id) as conversations
           FROM events
           WHERE event_name='product_recommended'
             AND json_extract(metadata, '$.url') IS NOT NULL
           GROUP BY url, image_url
           ORDER BY cnt DESC
           LIMIT 30"""
    )

    lead_rows = _rows(
        c,
        """SELECT id, session_id, content, timestamp
           FROM messages
           WHERE role='user'
             AND (content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%')
           ORDER BY id DESC
           LIMIT 100"""
    )
    leads = []
    for row in lead_rows:
        lead = _extract_lead_data(row["content"])
        lead.update({"id": row["id"], "session_id": row["session_id"], "timestamp": row["timestamp"]})
        leads.append(lead)

    conversation_rows = _rows(
        c,
        f"""SELECT m.session_id,
                  MIN(m.timestamp) as started_at,
                  MAX(m.timestamp) as last_message_at,
                  COUNT(*) as message_count,
                  SUM(CASE WHEN m.role='user' THEN 1 ELSE 0 END) as user_messages,
                  SUM(CASE WHEN m.role='bot' THEN 1 ELSE 0 END) as bot_messages,
                  MAX(CASE WHEN m.content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR m.content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%' THEN 1 ELSE 0 END) as has_lead,
                  {_ENTRY_PAGE_SELECT}
           FROM messages m
           GROUP BY m.session_id
           ORDER BY MAX(m.timestamp) DESC
           LIMIT 100"""
    )

    language_rows = _rows(
        c,
        """SELECT language, COUNT(*) as cnt
           FROM events
           WHERE language IS NOT NULL AND language != ''
           GROUP BY language
           ORDER BY cnt DESC"""
    )

    peak_hour_rows = _rows(
        c,
        """SELECT strftime('%H', timestamp) as hour, COUNT(*) as cnt
           FROM events
           WHERE event_name IN ('message_user', 'message_bot')
           GROUP BY hour
           ORDER BY cnt DESC
           LIMIT 5"""
    )

    quality_no_answer = _scalar(
        c,
        """SELECT COUNT(*) FROM messages
           WHERE role='bot'
             AND (lower(content) LIKE '%nevím%' OR lower(content) LIKE '%nemám%' OR lower(content) LIKE '%nemohu%' OR lower(content) LIKE '%kontaktujte%')"""
    )
    suspected_url_leaks = _scalar(
        c,
        """SELECT COUNT(*) FROM messages
           WHERE role='bot' AND content LIKE '%[URL:%'"""
    )

    latest_message_id = _scalar(c, "SELECT COALESCE(MAX(id), 0) FROM messages")
    latest_event_id = _scalar(c, "SELECT COALESCE(MAX(id), 0) FROM events")

    conn.close()

    avg_messages = round(total_messages / total_conversations, 2) if total_conversations else 0.0

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "cache_ttl_seconds": DASHBOARD_CACHE_TTL_SECONDS,
        "cursors": {
            "latest_message_id": latest_message_id,
            "latest_event_id": latest_event_id
        },
        "overview": {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "bot_messages": bot_messages,
            "events_total": events_total,
            "conversations_today": today_conversations,
            "conversations_7d": week_conversations,
            "conversations_30d": month_conversations,
            "avg_messages_per_conversation": avg_messages,
            "product_recommendations": product_recommended,
            "leads_total": contact_submitted + contact_passive,
            "contact_submitted": contact_submitted,
            "contact_captured_passive": contact_passive,
            "contact_conversion_rate_pct": _percent(contact_submitted + contact_passive, total_conversations),
            "product_recommendation_rate_pct": _percent(product_recommended, total_conversations)
        },
        "funnel": {
            "chat_started": event_counts.get("chat_started", 0),
            "message_user": event_counts.get("message_user", 0),
            "message_bot": event_counts.get("message_bot", 0),
            "quick_actions_shown": quick_actions,
            "product_recommended": product_recommended,
            "page_link_prompt_shown": page_link_shown,
            "page_link_clicked_yes": page_link_yes,
            "contact_form_shown": form_shown,
            "contact_submitted": contact_submitted,
            "contact_captured_passive": contact_passive,
            "page_link_click_rate_pct": _percent(page_link_yes, page_link_shown),
            "form_submit_rate_pct": _percent(contact_submitted, form_shown)
        },
        "time_series": {
            "daily_30d": [
                {
                    "day": row["day"],
                    "conversations": row["conversations"] or 0,
                    "messages": row["messages"] or 0,
                    "leads": row["leads"] or 0,
                    "product_recommendations": row["product_recommendations"] or 0,
                    "forms_shown": row["forms_shown"] or 0
                }
                for row in daily_rows
            ],
            "peak_hours": [{"hour": row["hour"], "count": row["cnt"]} for row in peak_hour_rows]
        },
        "questions": {
            "top_queries": top_queries,
            "categories": [{"category": key, "count": value} for key, value in category_counts.items()]
        },
        "products": {
            "top_recommended": [
                {
                    "url": row["url"],
                    "image_url": row["image_url"],
                    "count": row["cnt"],
                    "conversations": row["conversations"]
                }
                for row in product_rows
            ]
        },
        "leads": {
            "latest": leads,
            "submitted": contact_submitted,
            "passive": contact_passive,
            "total": contact_submitted + contact_passive
        },
        "conversations": {
            "latest": [
                _conversation_payload(row)
                for row in conversation_rows
            ]
        },
        "quality": {
            "bot_uncertain_or_contact_fallback_count": quality_no_answer,
            "suspected_url_tag_leaks": suspected_url_leaks,
            "manual_review_queue_hint": "Filter conversations with high message_count, no lead, URL leaks, or uncertain bot answers."
        },
        "performance": {
            "known_event_counts": event_counts,
            "timeout_events": event_counts.get("chat_timeout", 0),
            "server_error_events": event_counts.get("chat_error", 0)
        },
        "users": {
            "languages": [{"language": row["language"], "count": row["cnt"]} for row in language_rows]
        }
    }

def refresh_dashboard_cache():
    _init_dashboard_storage()
    snapshot = _build_dashboard_snapshot()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """INSERT OR REPLACE INTO dashboard_cache (cache_key, payload, generated_at)
           VALUES (?, ?, ?)""",
        (DASHBOARD_CACHE_KEY, json.dumps(snapshot, ensure_ascii=False), datetime.utcnow())
    )
    conn.commit()
    conn.close()
    return snapshot

def get_cached_dashboard_snapshot(force_refresh: bool = False):
    _init_dashboard_storage()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT payload, generated_at FROM dashboard_cache WHERE cache_key = ?", (DASHBOARD_CACHE_KEY,))
    row = c.fetchone()
    conn.close()

    if not force_refresh and row:
        generated_at = datetime.fromisoformat(str(row[1]))
        age_seconds = (datetime.utcnow() - generated_at).total_seconds()
        if age_seconds < DASHBOARD_CACHE_TTL_SECONDS:
            return json.loads(row[0])

    return refresh_dashboard_cache()

_init_dashboard_storage()

@router.get("/stats")
async def get_dashboard_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Počet unikátnych konverzácií
    c.execute("SELECT COUNT(DISTINCT session_id) FROM messages")
    total_convs = c.fetchone()[0]
    
    # Počet odporúčaných produktov
    c.execute("SELECT COUNT(*) FROM stats WHERE event_type='product_recommendation'")
    total_prods = c.fetchone()[0]
    
    # Počet správ od užívateľov
    c.execute("SELECT COUNT(*) FROM messages WHERE role='user'")
    total_msgs = c.fetchone()[0]

    conn.close()
    return {
        "total_conversations": total_convs,
        "total_messages": total_msgs,
        "product_recommendations": total_prods,
        "active_users": total_convs,
        "top_query": "Hledání produktu"
    }

@router.get("/history")
async def get_chat_history():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT session_id, role, content, timestamp FROM messages ORDER BY id DESC LIMIT 100")
    rows = c.fetchall()
    conn.close()
    return [{"session_id": r[0], "role": r[1], "content": r[2], "timestamp": r[3]} for r in rows]

@router.get("/events")
async def get_events(
    limit: int = 500,
    event_name: str = None,
    session_id: str = None,
    since_id: int = None
):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    query = """SELECT id, event_name, session_id, message_id, user_id_hash, language, metadata, timestamp, sync_status
               FROM events"""
    conditions = []
    params = []

    if event_name:
        conditions.append("event_name = ?")
        params.append(event_name)
    if session_id:
        conditions.append("session_id = ?")
        params.append(session_id)
    if since_id:
        conditions.append("id > ?")
        params.append(since_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "event_name": r[1],
            "session_id": r[2],
            "message_id": r[3],
            "user_id_hash": r[4],
            "language": r[5],
            "metadata": json.loads(r[6]) if r[6] else {},
            "timestamp": r[7],
            "sync_status": r[8]
        }
        for r in rows
    ]

@router.post("/events/ingest")
async def ingest_events(payload: Union[EventIn, List[EventIn]]):
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        emit_event(
            event_name=event.event_name,
            session_id=event.session_id,
            message_id=event.message_id,
            user_id_hash=event.user_id_hash,
            language=event.language,
            metadata=event.metadata,
            timestamp=event.timestamp,
            sync_status=event.sync_status or "synced"
        )
    return {"ingested": len(events), "status": "ok"}

@router.post("/messages/ingest")
async def ingest_messages(payload: Union[ClientMessageIn, List[ClientMessageIn]]):
    messages = payload if isinstance(payload, list) else [payload]
    for msg in messages:
        role = msg.role.lower().strip()
        if role not in ("user", "bot", "assistant"):
            continue

        normalized_role = "bot" if role == "assistant" else role
        log_message(msg.session_id, normalized_role, msg.content)

        emit_event(
            event_name=msg.event_name or ("message_user" if normalized_role == "user" else "message_bot"),
            session_id=msg.session_id,
            language=msg.language,
            metadata=msg.metadata or {}
        )

    return {"ingested": len(messages), "status": "ok"}

@router.get("/analytics/summary")
async def get_analytics_summary(period: str = "week"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    modifier = _period_modifier(period)

    c.execute(
        """SELECT COUNT(DISTINCT session_id) FROM events
           WHERE event_name='chat_started'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    conversations = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name IN ('message_user', 'message_bot')
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    total_messages = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='message_user'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    user_messages = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='message_bot'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    bot_messages = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='product_recommended'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    product_recommendations = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(DISTINCT session_id) FROM events
           WHERE event_name='product_recommended'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    conversations_with_product = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(DISTINCT session_id) FROM events
           WHERE event_name IN ('contact_submitted', 'contact_captured_passive')
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    contact_converted_sessions = c.fetchone()[0] or 0

    conn.close()

    avg_messages = round(total_messages / conversations, 2) if conversations else 0.0
    bot_user_ratio = round(bot_messages / user_messages, 2) if user_messages else 0.0
    product_conv_rate = round((conversations_with_product / conversations) * 100, 2) if conversations else 0.0
    contact_conv_rate = round((contact_converted_sessions / conversations) * 100, 2) if conversations else 0.0

    return {
        "period": period,
        "kpis": {
            "conversations": conversations,
            "total_messages": total_messages,
            "user_messages": user_messages,
            "bot_messages": bot_messages,
            "avg_messages_per_conversation": avg_messages,
            "bot_user_ratio": bot_user_ratio,
            "product_recommendations": product_recommendations,
            "conversations_with_product": conversations_with_product,
            "product_conversation_rate_pct": product_conv_rate,
            "contact_converted_sessions": contact_converted_sessions,
            "contact_conversion_rate_pct": contact_conv_rate
        }
    }

@router.get("/analytics/timeseries")
async def get_analytics_timeseries(period: str = "week"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    modifier = _period_modifier(period)

    c.execute(
        """SELECT date(timestamp) as day, COUNT(DISTINCT session_id) as conversations
           FROM events
           WHERE event_name='chat_started' AND datetime(timestamp) >= datetime('now', ?)
           GROUP BY date(timestamp)
           ORDER BY day ASC""",
        (modifier,)
    )
    conversations_by_day = [{"day": r[0], "value": r[1]} for r in c.fetchall()]

    c.execute(
        """SELECT date(timestamp) as day, COUNT(*) as messages
           FROM events
           WHERE event_name IN ('message_user', 'message_bot')
           AND datetime(timestamp) >= datetime('now', ?)
           GROUP BY date(timestamp)
           ORDER BY day ASC""",
        (modifier,)
    )
    messages_by_day = [{"day": r[0], "value": r[1]} for r in c.fetchall()]

    c.execute(
        """SELECT strftime('%H', timestamp) as hour, COUNT(*) as events_count
           FROM events
           WHERE event_name IN ('message_user', 'message_bot')
           AND datetime(timestamp) >= datetime('now', ?)
           GROUP BY strftime('%H', timestamp)
           ORDER BY events_count DESC
           LIMIT 1""",
        (modifier,)
    )
    peak_row = c.fetchone()
    peak_hour = peak_row[0] if peak_row else None

    conn.close()
    return {
        "period": period,
        "conversations_by_day": conversations_by_day,
        "messages_by_day": messages_by_day,
        "peak_hour": peak_hour
    }

@router.get("/analytics/top-queries")
async def get_top_queries(period: str = "week", limit: int = 10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    modifier = _period_modifier(period)

    c.execute(
        """SELECT json_extract(metadata, '$.query_text') as query_text, COUNT(*) as cnt
           FROM events
           WHERE event_name='message_user'
           AND datetime(timestamp) >= datetime('now', ?)
           GROUP BY query_text
           HAVING json_extract(metadata, '$.query_text') IS NOT NULL
              AND json_extract(metadata, '$.query_text') != ''
           ORDER BY cnt DESC
           LIMIT ?""",
        (modifier, limit)
    )
    rows = c.fetchall()
    conn.close()

    return {
        "period": period,
        "top_queries": [{"query": r[0], "count": r[1]} for r in rows]
    }

@router.get("/analytics/categories")
async def get_query_categories(period: str = "week"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    modifier = _period_modifier(period)

    c.execute(
        """SELECT json_extract(metadata, '$.query_text') as query_text
           FROM events
           WHERE event_name='message_user'
           AND datetime(timestamp) >= datetime('now', ?)
           AND json_extract(metadata, '$.query_text') IS NOT NULL
           AND json_extract(metadata, '$.query_text') != ''""",
        (modifier,)
    )
    rows = c.fetchall()
    conn.close()

    counts = {"Informace": 0, "Produkty & Nákup": 0, "Podpora & Pomoc": 0}
    for row in rows:
        category = _category_from_query(row[0])
        counts[category] += 1

    return {
        "period": period,
        "categories": [
            {"category": "Informace", "count": counts["Informace"]},
            {"category": "Produkty & Nákup", "count": counts["Produkty & Nákup"]},
            {"category": "Podpora & Pomoc", "count": counts["Podpora & Pomoc"]}
        ]
    }

@router.get("/analytics/conversions")
async def get_conversions(period: str = "week"):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    modifier = _period_modifier(period)

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='contact_form_shown'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    forms_shown = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='contact_submitted'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    contacts_submitted = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(*) FROM events
           WHERE event_name='contact_captured_passive'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    contacts_passive = c.fetchone()[0] or 0

    c.execute(
        """SELECT COUNT(DISTINCT session_id) FROM events
           WHERE event_name='chat_started'
           AND datetime(timestamp) >= datetime('now', ?)""",
        (modifier,)
    )
    conversations = c.fetchone()[0] or 0
    conn.close()

    any_contacts = contacts_submitted + contacts_passive
    conv_rate = round((any_contacts / conversations) * 100, 2) if conversations else 0.0

    return {
        "period": period,
        "contact_form_shown": forms_shown,
        "contact_submitted": contacts_submitted,
        "contact_captured_passive": contacts_passive,
        "any_contact": any_contacts,
        "any_contact_conversion_rate_pct": conv_rate
    }

@router.get("/dashboard/snapshot")
async def get_dashboard_snapshot(request: Request, refresh: bool = False):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot(force_refresh=refresh)

@router.post("/dashboard/refresh")
async def refresh_dashboard_snapshot(request: Request):
    _require_dashboard_api_key(request)
    return refresh_dashboard_cache()


@router.post("/reindex-knowledge")
async def reindex_knowledge(request: Request):
    """
    Stiahne knowledge_base.md z GitHubu a reindexuje do Qdrantu.
    Volané z portálu cez BOT_REINDEX_WEBHOOK_URL po publikovaní zmien.
    """
    _require_dashboard_api_key(request)

    if not is_github_configured():
        raise HTTPException(
            status_code=503,
            detail="GitHub knowledge sync is not configured on the bot.",
        )

    try:
        sections_indexed = sync_knowledge_base(fetch_remote=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}") from exc

    return {
        "status": "success",
        "sections_indexed": sections_indexed,
        "source": "github",
        "file_path": KNOWLEDGE_LOCAL_PATH,
        "target": f"{os.getenv('GITHUB_OWNER', '')}/{os.getenv('GITHUB_REPO', '')}",
    }

@router.get("/dashboard/overview")
async def get_dashboard_overview(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("overview", {})

@router.get("/dashboard/funnel")
async def get_dashboard_funnel(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("funnel", {})

@router.get("/dashboard/questions")
async def get_dashboard_questions(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("questions", {})

@router.get("/dashboard/products")
async def get_dashboard_products(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("products", {})

@router.get("/dashboard/leads")
async def get_dashboard_leads(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("leads", {})

@router.get("/dashboard/quality")
async def get_dashboard_quality(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("quality", {})

@router.get("/dashboard/performance")
async def get_dashboard_performance(request: Request):
    _require_dashboard_api_key(request)
    return get_cached_dashboard_snapshot().get("performance", {})

@router.get("/dashboard/conversations")
async def get_dashboard_conversations(request: Request, limit: int = 100, offset: int = 0, has_lead: Optional[bool] = None):
    _require_dashboard_api_key(request)
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    conn = _connect()
    c = conn.cursor()
    having_clause = ""
    params = []
    if has_lead is not None:
        having_clause = "HAVING MAX(CASE WHEN m.content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR m.content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%' THEN 1 ELSE 0 END) = ?"
        params.append(1 if has_lead else 0)

    params.extend([limit, offset])
    rows = _rows(
        c,
        f"""SELECT m.session_id,
                   MIN(m.timestamp) as started_at,
                   MAX(m.timestamp) as last_message_at,
                   COUNT(*) as message_count,
                   SUM(CASE WHEN m.role='user' THEN 1 ELSE 0 END) as user_messages,
                   SUM(CASE WHEN m.role='bot' THEN 1 ELSE 0 END) as bot_messages,
                   MAX(CASE WHEN m.content LIKE '[KONTAKTNÍ FORMULÁŘ]%' OR m.content LIKE '[PASIVNÍ ZÁCHYT KONTAKTU]%' THEN 1 ELSE 0 END) as has_lead,
                   {_ENTRY_PAGE_SELECT}
            FROM messages m
            GROUP BY m.session_id
            {having_clause}
            ORDER BY MAX(m.timestamp) DESC
            LIMIT ? OFFSET ?""",
        params
    )
    conn.close()

    return {
        "limit": limit,
        "offset": offset,
        "conversations": [
            _conversation_payload(row)
            for row in rows
        ]
    }

@router.get("/dashboard/conversations/{session_id}")
async def get_dashboard_conversation_detail(request: Request, session_id: str):
    _require_dashboard_api_key(request)
    conn = _connect()
    c = conn.cursor()
    message_rows = _rows(
        c,
        """SELECT id, role, content, timestamp
           FROM messages
           WHERE session_id = ?
           ORDER BY id ASC""",
        (session_id,)
    )
    event_rows = _rows(
        c,
        """SELECT id, event_name, language, metadata, timestamp
           FROM events
           WHERE session_id = ?
           ORDER BY id ASC""",
        (session_id,)
    )
    conn.close()

    entry_page = _extract_entry_page_from_events(event_rows)

    return {
        "session_id": session_id,
        **entry_page,
        "messages": [
            {"id": row["id"], "role": row["role"], "content": row["content"], "timestamp": row["timestamp"]}
            for row in message_rows
        ],
        "events": [
            {
                "id": row["id"],
                "event_name": row["event_name"],
                "language": row["language"],
                "metadata": _safe_json(row["metadata"]),
                "timestamp": row["timestamp"]
            }
            for row in event_rows
        ]
    }

@router.get("/dashboard/events")
async def get_dashboard_events(request: Request, since_id: int = 0, limit: int = 500):
    _require_dashboard_api_key(request)
    limit = max(1, min(limit, 1000))
    conn = _connect()
    c = conn.cursor()
    rows = _rows(
        c,
        """SELECT id, event_name, session_id, message_id, user_id_hash, language, metadata, timestamp, sync_status
           FROM events
           WHERE id > ?
           ORDER BY id ASC
           LIMIT ?""",
        (since_id, limit)
    )
    conn.close()
    return {
        "since_id": since_id,
        "limit": limit,
        "events": [
            {
                "id": row["id"],
                "event_name": row["event_name"],
                "session_id": row["session_id"],
                "message_id": row["message_id"],
                "user_id_hash": row["user_id_hash"],
                "language": row["language"],
                "metadata": _safe_json(row["metadata"]),
                "timestamp": row["timestamp"],
                "sync_status": row["sync_status"]
            }
            for row in rows
        ]
    }
