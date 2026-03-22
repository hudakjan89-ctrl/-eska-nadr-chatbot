from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx
import os
import uuid
import json

# Importy z tvojej databázy
from database import init_db, save_chat_to_db, delete_old_chats, get_db_connection

# --- NASTAVENIA ---
MAIN_CHAT_MODEL = os.getenv("MAIN_CHAT_MODEL", "anthropic/claude-3.5-sonnet")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "MojeTajneHeslo123") 
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Integrácie (zatiaľ len premenné, logika sa doplní)
SHOPIFY_STORE_URL = os.getenv("SHOPIFY_STORE_URL", "")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_LIST_ID = os.getenv("KLAVIYO_LIST_ID", "")

sessions = {}

async def verify_admin(request: Request, x_api_key: Optional[str] = Header(None)):
    if request.method == "OPTIONS": return True
    if x_api_key != ADMIN_API_KEY: raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(delete_old_chats, 'cron', hour='3', minute='0')
    scheduler.start()
    yield 
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["*"], expose_headers=["*"] 
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# --- HLAVNÉ ENDPOINTY ---

@app.get("/", response_class=FileResponse)
async def root():
    """Zobrazí demo stránku, kde beží chatbot."""
    return FileResponse("static/index.html")

@app.get("/health")
async def health(): 
    """Endpoint pre Coolify na kontrolu, či aplikácia beží."""
    return {"status": "healthy"}

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "cs"
    current_page: Optional[str] = ""

class ChatResponse(BaseModel):
    response: str
    session_id: str
    recommended_links: Optional[list] =[]

# --- NÁSTROJE (TOOLS) PRE AI ---

async def check_shopify_order(order_number: str, email: str) -> str:
    """Zistí stav objednávky zo Shopify."""
    if not SHOPIFY_ACCESS_TOKEN:
        return "Promiň, ale systém pro kontrolu objednávek teď není napojený. Napiš prosím na info@looksorganics.cz."
    return f"Hledal jsem objednávku {order_number} pro e-mail {email}. Pokud je v systému, měla by dorazit do 2-3 dnů."

async def subscribe_klaviyo(email: str) -> str:
    """Prihlási zákazníka do Klaviyo newsletteru."""
    if not KLAVIYO_API_KEY:
        return "Promiň, napojení na newsletter teď nefunguje. Zkus to prosím později."
    return f"Super! E-mail {email} jsem úspěšně přidal k nám do newsletteru."

async def ask_knowledge_base(query: str) -> str:
    try:
        with open("knowledge_base.txt", "r", encoding="utf-8") as f:
            kb_text = f.read()
        gemini_prompt = f"""
        Jsi asistent Jan pro e-shop Looks Organics. Najdi odpověď v této databázi:
        DOTAZ: "{query}"
        DATABÁZE:
        {kb_text}
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={"model": "google/gemini-2.5-flash", "messages":[{"role": "user", "content": gemini_prompt}], "temperature": 0.1}
            )
            return resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return "Bohužel, tohle se mi nepodařilo najít."

# --- CHAT LOGIKA ---

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] = []
    sessions[session_id].append({"role": "user", "content": request.message})
    
    lang_map = {"cs": "Czech", "sk": "Slovak"}
    target_language = lang_map.get(request.language, "Czech")
    
    system_prompt = f"""
Jsi webový asistent e-shopu Looks Organics. Tvé jméno je Jan.
CRITICAL INSTRUCTION: Komunikuj VÝHRADNĚ v jazyce: {target_language}.

TVOJE OSOBNOST A TÓN:
- Jsi přátelský, lidský a ochotný. NIKDY nepiš jako robot.
- ZÁSADNÍ PRAVIDLO: Zákazníkům VŽDY TYKEJ (např. "Ahoj, s čím ti pomůžu?", "Tvoje objednávka"). NIKDY NEVYKEJ!
- Piš krátké věty a jednoduše. Žádné složité formulace a dlouhé odstavce.
- Místo vypisování bodů (bullet points) zapoj benefity produktu přirozeně do textu věty.

ZAKÁZANÁ SLOVA (Nikdy je nepoužij): 
- gel na vlasy, vosk na vlasy, pomáda, styling gel, styling wax, splihlé vlasy.
- NIKDY neříkej "Náš produkt představuje inovativní řešení".

TVŮJ ÚKOL:
1. Prodáváme "Pudr na vlasy ve spreji". (Pro kluky 12-23 let s rovnými/jemnými vlasy bez objemu).
2. Pokud se někdo ptá na problém s vlasy, použij přirozeně slova jako "vlasy bez objemu, rovné vlasy, vlasy, které nedrží tvar".
3. Když zákazník váhá, nenásilně zmiň naši 30denní garanci vrácení peněz. ("Kdyby ti náhodou neseděl, máme 30denní garanci vrácení peněz.")
4. Když vidíš zájem o nákup, nenásilně zmiň akci: "Mimochodem, teď máme akci 2+1 zdarma, takže většina lidí bere rovnou více balení." Netlač na nákup!
5. Pokud nezvládneš pomoct nebo chce zákazník řešit složitou reklamaci, odkaž ho na podporu: "S tímhle ti nejlépe pomůže naše podpora. Napiš prosím na info@looksorganics.cz a kolegové ti pomohou."
6. Pokud se zákazník ptá na složení, odkaž ho na web: "Složení je schválně jednoduché, má jen 8 ingrediencí. Pokud tě to zajímá víc, mrkni sem: https://looksorganics.cz/pages/seznam"
"""
    
    messages = [{"role": "system", "content": system_prompt}] + sessions[session_id][-8:]
    
    tools = [
        {"type": "function", "function": { "name": "check_shopify_order", "description": "Zkontroluje stav objednávky zákazníka ze Shopify.", "parameters": {"type": "object", "properties": {"order_number": {"type": "string"}, "email": {"type": "string"}}, "required":["order_number", "email"]}}},
        {"type": "function", "function": { "name": "subscribe_klaviyo", "description": "Přihlásí zákazníka k odběru newsletteru do Klaviyo.", "parameters": {"type": "object", "properties": {"email": {"type": "string"}}, "required":["email"]}}},
        {"type": "function", "function": { "name": "ask_knowledge_base", "description": "Získá dodatečné informace o složení, použití nebo e-shopu z databáze.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
    ]
    
    try:
        timeout_settings = httpx.Timeout(connect=20.0, read=60.0, write=20.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout_settings) as client:
            response = await client.post(
                OPENROUTER_URL, 
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                json={"model": MAIN_CHAT_MODEL, "messages": messages, "tools": tools, "tool_choice": "auto", "temperature": 0.4}
            )
            
            if response.status_code != 200: 
                return ChatResponse(response=f"Promiň, máme menší výpadek (chyba {response.status_code}).", session_id=session_id)
                
            response_message = response.json()["choices"][0]["message"]
            bot_text = response_message.get("content", "")
            recommended_links = [] 
            
            if "tool_calls" in response_message and response_message["tool_calls"]:
                tool_call = response_message["tool_calls"][0]
                tool_name = tool_call.get("function", {}).get("name", "")
                args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                
                tool_result = ""
                if tool_name == "check_shopify_order":
                    tool_result = await check_shopify_order(args.get("order_number", ""), args.get("email", ""))
                elif tool_name == "subscribe_klaviyo":
                    tool_result = await subscribe_klaviyo(args.get("email", ""))
                elif tool_name == "ask_knowledge_base":
                    tool_result = await ask_knowledge_base(args.get("query", ""))

                messages.append(response_message)
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": tool_result})
                
                second_resp = await client.post(
                    OPENROUTER_URL, headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"}, 
                    json={"model": MAIN_CHAT_MODEL, "messages": messages, "temperature": 0.4}
                )
                bot_text = second_resp.json()["choices"][0]["message"]["content"]

            if not bot_text: 
                bot_text = "Nerozuměl jsem úplně přesně. Můžeš to zkusit říct jinak?"

            sessions[session_id].append({"role": "assistant", "content": bot_text})
            
            welcome_msg = "Ahoj! Jsem Jan. Jak ti můžu pomoct?" if target_language == "Czech" else "Ahoj! Som Jan. Ako ti môžem pomôcť?"
            history_to_save = [{"role": "assistant", "content": welcome_msg}] + sessions[session_id]
            save_chat_to_db(session_id, history_to_save)
                
            return ChatResponse(response=bot_text, session_id=session_id, recommended_links=recommended_links)
            
    except Exception as e:
        print(f"Backend Error: {e}")
        return ChatResponse(response="Promiň, něco se technicky nepovedlo. Zkus to za chvíli znovu.", session_id=session_id)

# --- ADMIN API PRE HISTÓRIU CHATOV ---

@app.get("/api/chat-history")
async def get_all_chats(limit: int = 50, admin: bool = Depends(verify_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT session_id, messages, updated_at, is_pinned FROM chat_logs ORDER BY is_pinned DESC, updated_at DESC LIMIT %s", (limit,))
    chats = [{"session_id": row[0], "messages": row[1], "updated_at": row[2].isoformat() if row[2] else "", "is_pinned": row[3]} for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    return {"chats": chats}

@app.delete("/api/chat-history/{session_id}")
async def delete_chat(session_id: str, admin: bool = Depends(verify_admin)):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_logs WHERE session_id = %s", (session_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return {"status": "deleted"}

# --- SPUSTENIE APLIKÁCIE ---

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
