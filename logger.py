import sqlite3
from datetime import datetime

DB_PATH = "analytics.db"

def init_analytics_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Tabuľka pre históriu správ
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, 
                  content TEXT, timestamp DATETIME)''')
    # Tabuľka pre udalosti (napr. odporúčanie produktu)
    c.execute('''CREATE TABLE IF NOT EXISTS stats 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

def log_message(session_id: str, role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
              (session_id, role, content, datetime.now()))
    conn.commit()
    conn.close()

def log_event(event_type: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO stats (event_type, timestamp) VALUES (?, ?)", (event_type, datetime.now()))
    conn.commit()
    conn.close()

init_analytics_db()
