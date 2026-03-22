from fastapi import APIRouter
import sqlite3
from logger import DB_PATH

router = APIRouter(prefix="/admin", tags=["admin"])

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
