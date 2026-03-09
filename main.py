# main.py
import os
import uuid
import httpx
import unicodedata
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from knowledge import CESKA_NADRZ_KNOWLEDGE

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

# ==========================================
# DETEKCIA SEKCIE PRE PRESMEROVANIE NA WEBE
# ==========================================
def remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# Kľúčové slová prispôsobené pre Českú nádrž
KEYWORDS = {
    "doprava":["doprava", "dovoz", "rozvoz", "zadarmo", "zdarma", "dodavka", "ridic", "skladani"],
    "kontakt":["kontakt", "telefon", "email", "adresa", "kde vas najdem", "kde vas najdu", "spojeni"],
    "eshop":["eshop", "koupit", "objednat", "cena", "cenik", "produkty", "katalog"],
    "poradce":["vyber", "jakou nadrz", "samonosn", "obetonovan", "dvouplast", "podlozi", "spodni voda"]
}

def detect_page_section(message: str) -> Optional[str]:
    msg_clean = remove_diacritics(message.lower())
    for section, terms in KEYWORDS.items():
        if any(term in msg_clean for term in terms):
            return section
    return None

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž Bot is running", "version": "1.0.beta"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    system_prompt = (
        f"Jsi AI nákupní asistent a zákaznická podpora pro e-shop Česká nádrž.\n\n"
        f"ZDE JSOU TVÉ ZNALOSTI (Z NICH ČERPEJ):\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        "TVÉ HLAVNÍ ÚKOLY A CHOVÁNÍ:\n"
        "1. FAQ: Odpovídat na dotazy ohledně dopravy (je zdarma), platby (nelze kartou u řidiče) a kvality. Buď stručný a jasný.\n"
        "2. NÁKUPNÍ ASISTENT: Pokud zákazník neví, jakou nádrž vybrat, NEPOSÍLEJ mu rovnou seznam. Postupně se ho ptej na 3 věci: 1. Účel, 2. Objem, 3. Podloží (zda je tam spodní voda, jíl nebo svah). Ptej se max na 1-2 věci v jedné zprávě, ať je to konverzace.\n"
        "3. EMAIL HANDOFF: Pokud se zákazník ptá na složité technické řešení (atypické rozměry, výška přítoku, hydrogeologie, stav objednávky), OMLUV SE, že jsi jen AI asistent, a VYZVI HO K ZADÁNÍ EMAILU A TELEFONU, aby se mu mohl ozvat technik Petr. Pokud ti zákazník pošle svůj email/telefon, poděkuj mu, řekni, že to předáváš kolegům, a ukonči technické poradenství.\n\n"
        "ABSOLUTNÍ PRAVIDLA:\n"
        "- NIKDY nepoužívej hvězdičky (**) ani jiné složité formátování (Markdown bold/italic).\n"
        "- NIKDY si nevymýšlej produkty, ceny nebo termíny dodání, které nejsou v tvých znalostech.\n"
        "- Komunikuj profesionálně, přátelsky, v češtině a zákazníkům vykej.\n"
    )
    
    # Udržujeme len posledných 10 správ, aby sme neprekročili tokeny a bot mal kontext
    messages = [{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://www.ceskanadrz.cz",
                    "X-Title": "Ceska Nadrz Bot"
                },
                json={
                    "model": "openai/gpt-4o-mini", 
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 400
                }
            )
            
            if response.status_code != 200:
                print(f"AI Error: {response.text}")
                raise HTTPException(status_code=response.status_code, detail="AI Service Error")
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            
            detected_section = detect_page_section(request.message)
            
            return ChatResponse(
                response=assistant_message,
                session_id=session_id,
                page_section=detected_section
            )
            
    except Exception as e:
        print(f"Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
