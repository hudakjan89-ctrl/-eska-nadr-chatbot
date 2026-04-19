from fastapi import APIRouter
import sqlite3
from logger import DB_PATH
import json
from pydantic import BaseModel
from typing import Optional, List, Union
from logger import emit_event

router = APIRouter(prefix="/admin", tags=["admin"])

class EventIn(BaseModel):
    event_name: str
    session_id: Optional[str] = None
    message_id: Optional[str] = None
    user_id_hash: Optional[str] = None
    language: Optional[str] = None
    metadata: Optional[dict] = None
    timestamp: Optional[str] = None
    sync_status: Optional[str] = "synced"

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
