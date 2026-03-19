import os
import uuid
import httpx
import asyncio
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from knowledge import CESKA_NADRZ_KNOWLEDGE
from xml_parser import fetch_and_parse_xml
from database import upsert_products, search_products

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

sessions = {}

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "cs"

class ChatResponse(BaseModel):
    response: str
    session_id: str
    page_section: Optional[str] = None
    show_contact_form: bool = False

# ==========================================
# AKTUALIZÁCIA DATABÁZY (Každých 6 hodín)
# ==========================================
async def update_database_task():
    print("Spúšťam sťahovanie a aktualizáciu XML feedu...")
    products = await fetch_and_parse_xml()
    if products:
        upsert_products(products)

@app.on_event("startup")
async def startup_event():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_database_task, 'interval', hours=6)
    scheduler.start()
    # Spustí update jednorazovo aj hneď pri zapnutí servera
    asyncio.create_task(update_database_task())

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž Qdrant Bot is running", "version": "2.0"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] =[]
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    # RAG - Získame 7 najlepších produktov z Qdrantu pre aktuálnu otázku
    found_products = search_products(request.message)
    products_context = "NAŠEL JSEM TYTO PRODUKTY V DATABÁZI (Z nich doporuč to nejlepší):\n"
    for p in found_products:
        products_context += f"- Název: {p['name']} | Cena: {p['price']} Kč | Odkaz: {p['url']} | Kategorie: {p['category']}\n"
    if not found_products:
        products_context = "V databázi nebyly nalezeny žádné přesné produkty pro tento dotaz."

    lang_instruction = "MUSÍŠ odpovídat striktně ČESKY."
    if request.language == "sk": lang_instruction = "MUSÍŠ odpovedať striktne SLOVENSKY!"
    elif request.language == "en": lang_instruction = "You MUST answer strictly in ENGLISH!"
    elif request.language == "uk": lang_instruction = "Ти ПОВИНЕН відповідати строго УКРАЇНСЬКОЮ мовою!"

    # PROMPT CACHING - Aby OpenRouter šetril tokeny, statická časť (Knowledge) musí byť prvá!
    system_prompt = (
        f"Jsi technický poradce a asistent e-shopu Česká nádrž.\n\n"
        f"STATICKÁ FIREMNÍ DATABÁZE:\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        f"---------------------\n"
        f"{products_context}\n"
        f"---------------------\n"
        "TVÉ HLAVNÍ ÚKOLY:\n"
        "1. KROK 1 (DOPTAZOVÁNÍ): Zjisti účel, objem a podloží. Pokud nevíš objem, ptej se!\n"
        "2. KROK 2 (DOPORUČENÍ): Vyber 1-2 nejvhodnější produkty ze seznamu 'NAŠEL JSEM TYTO PRODUKTY'. Vypiš parametry a VŽDY ZAŘAĎ PŘESNÝ ODKAZ (URL) na produkt do své odpovědi, aby na něj mohl zákazník kliknout.\n"
        "3. KROK 3 (KONTAKT - LEAD GEN): Pokud má zákazník technický dotaz na míru (usazení, jíl, atypické řešení), IHNED ukonči prodej. Napiš: 'Tohle je už velmi specifický technický dotaz. Nejlépe vám poradí náš specialista Petr Nováček. Zanechte mi prosím své Jméno, E-mail a Telefon a Petr se vám ozve.' a NA ÚPLNÝ KONEC PŘIDEJ TAG: [SHOW_CONTACT_FORM]\n"
        "4. KROK 4 (NENALEZENO): Pokud seznam produktů výše nedává smysl pro zákazníkův dotaz, nevymýšlej si! Omluv se, že v databázi tento konkrétní typ nevidíš a odkaž ho na příslušnou kategorii.\n\n"
        "PRAVIDLA:\n"
        "- Vystupuj jako skutečný asistent e-shopu (odborný, přátelský).\n"
        "- Nepoužívej hvězdičky (**) k formátování.\n"
        f"- {lang_instruction}\n"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                # Claude 3.5 Sonnet
                json={"model": "anthropic/claude-sonnet-4.6", "messages": messages, "temperature": 0.2, "max_tokens": 500}
            )
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            show_form = False
            msg_lower = assistant_message.lower()
            if "[SHOW_CONTACT_FORM]" in assistant_message or "formulář" in msg_lower or "petr" in msg_lower or "zanechte mi" in msg_lower:
                show_form = True
                assistant_message = assistant_message.replace("[SHOW_CONTACT_FORM]", "").strip()
            
            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            
            # Kedze bot už vkladá URL priamo do textu, "page_section" môžeme zrušiť,
            # ale ponechávame ho prázdne, aby nepadol Frontend.
            return ChatResponse(
                response=assistant_message, 
                session_id=session_id, 
                page_section=None,
                show_contact_form=show_form
            )
            
    except Exception as e:
        print(f"Error in /chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
