import os
import re
import unicodedata
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from xml_parser import detect_placement

logger = logging.getLogger("ceska_nadrz.database")

logger.info("Načítavam jazykový AI model (Qdrant)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

_qdrant_path = os.getenv("QDRANT_PATH")
if not _qdrant_path:
    _data_dir = os.getenv("DATA_DIR", "data")
    _qdrant_path = os.path.join(_data_dir, "qdrant_db")
os.makedirs(_qdrant_path, exist_ok=True)
logger.info("Qdrant path: %s", _qdrant_path)

client = QdrantClient(path=_qdrant_path)
COLLECTION_PRODUCTS = "ceskanadrz_products"
COLLECTION_KNOWLEDGE = "ceskanadrz_knowledge"  # Nová databáza pre vedomosti

PLACEMENT_SYNONYMS = {
    "podzemni": "podzemní do země pod zemí samonosná k obetonování zakopaná",
    "nadzemni": "nadzemní volně stojící nad zemí",
    "neznamo": "",
}

ACCESSORY_HINTS = (
    "sběrač", "sberac", "zásuvka", "zasuvka", "poklop", "hadice", "filtr",
    "čerpadlo", "cerpadlo", "přečerpávací stanice", "precerpavaci stanice",
)

def _remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text or '') if unicodedata.category(c) != 'Mn')

def _normalize_text(text: str) -> str:
    text = _remove_diacritics((text or "").lower())
    text = text.replace("m³", "m3")
    text = re.sub(r'(\d+)\s*m\s*3', r'\1m3', text)
    return text

def product_embedding_text(prod: dict) -> str:
    placement = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
    synonyms = PLACEMENT_SYNONYMS.get(placement, "")
    return (
        f"Název: {prod['name']} "
        f"Umístění: {synonyms} "
        f"Kategorie: {prod.get('category', '')} "
        f"Popis: {prod.get('description', '')}"
    )

def expand_search_query(query: str) -> str:
    q = _normalize_text(query)
    extra = []

    if any(term in q for term in ("podzemni", "pod zem", "do zeme", "zakopan", "zakopat")):
        extra.extend(["samonosná nádrž", "nádrž k obetonování", "podzemní"])
    if any(term in q for term in ("nadzemni", "nad zem", "volne stojici", "volne stoj")):
        extra.extend(["nadzemní volně stojící"])
    if "retenc" in q:
        extra.append("retenční nádrž")
    if "destov" in q or "destovka" in q:
        extra.append("nádrž na dešťovou vodu")

    if extra:
        return f"{query} {' '.join(extra)}"
    return query

def _is_tank_product(prod: dict) -> bool:
    name = _normalize_text(prod.get("name", ""))
    if "nadrz" not in name:
        return False
    return not any(hint in name for hint in ACCESSORY_HINTS)

def _product_rank_score(prod: dict, query: str) -> int:
    q = _normalize_text(query)
    name = _normalize_text(prod.get("name", ""))
    placement = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
    score = 0

    wants_underground = any(term in q for term in ("podzemni", "pod zem", "do zeme", "samonos", "obetonov"))
    wants_aboveground = any(term in q for term in ("nadzemni", "nad zem", "volne stojici"))

    if wants_underground:
        if placement == "podzemni":
            score += 120
        if "nadzem" in name:
            score -= 250
    if wants_aboveground:
        if placement == "nadzemni":
            score += 120
        if placement == "podzemni":
            score -= 80

    if any(term in q for term in ("nadrz", "retenc", "destov", "destovka", "vodu")):
        if _is_tank_product(prod):
            score += 60
        else:
            score -= 40

    volume_match = re.search(r'(\d+)\s*m\s*3', q) or re.search(r'(\d+)m3', q)
    if volume_match:
        volume = volume_match.group(1)
        if f"{volume}m3" in name.replace(" ", ""):
            score += 50

    return score

def rerank_products(products: list, query: str) -> list:
    if not products:
        return products
    ranked = sorted(products, key=lambda prod: _product_rank_score(prod, query), reverse=True)
    return ranked

def collection_exists(coll_name):
    try:
        collections_response = client.get_collections()
        for collection in collections_response.collections:
            if collection.name == coll_name:
                return True
        return False
    except Exception:
        return False

def init_db():
    # Inicializácia produktovej databázy
    if not collection_exists(COLLECTION_PRODUCTS):
        logger.info(f"Vytváram databázu: {COLLECTION_PRODUCTS}")
        client.create_collection(collection_name=COLLECTION_PRODUCTS, vectors_config=VectorParams(size=384, distance=Distance.COSINE))
    
    # Inicializácia vedomostnej databázy
    if not collection_exists(COLLECTION_KNOWLEDGE):
        logger.info(f"Vytváram databázu: {COLLECTION_KNOWLEDGE}")
        client.create_collection(collection_name=COLLECTION_KNOWLEDGE, vectors_config=VectorParams(size=384, distance=Distance.COSINE))

# ================= PRODUKTY =================
def upsert_products(products):
    init_db()
    if not products:
        return
    points = []
    texts = [product_embedding_text(prod) for prod in products]
    logger.info(f"Generujem embeddingy pre {len(products)} produktov...")
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()
    for prod, vector in zip(products, vectors):
        payload = dict(prod)
        payload["placement"] = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
        points.append(PointStruct(
            id=prod['id'],
            vector=vector,
            payload=payload
        ))
    if points:
        client.upsert(collection_name=COLLECTION_PRODUCTS, points=points)
        logger.info(f"Úspešne aktualizovaných {len(points)} produktov v databáze.")

def search_products(query: str, top_k=10):
    if not collection_exists(COLLECTION_PRODUCTS):
        return []
    expanded_query = expand_search_query(query)
    query_vector = model.encode(expanded_query, show_progress_bar=False).tolist()
    fetch_k = max(top_k * 3, 24)
    hits = client.search(collection_name=COLLECTION_PRODUCTS, query_vector=query_vector, limit=fetch_k)
    products = [hit.payload for hit in hits]
    return rerank_products(products, expanded_query)[:top_k]

# ================= VEDOMOSTNÁ BÁZA (FAQ, INFO) =================
def load_and_upsert_knowledge(filepath="knowledge_base.md"):
    init_db()
    if not os.path.exists(filepath):
        logger.warning(f"Súbor {filepath} neexistuje. Vedomostná databáza sa nenačíta.")
        return 0

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    return upsert_knowledge_content(content)


def upsert_knowledge_content(content: str):
    # Rozsekáme text presne podľa tvojich nadpisov "### "
    sections = content.split('\n### ')
    points = []
    items = []
    # Preskočíme úplne prvý blok (hlavný nadpis dokumentu), ten nepotrebujeme ako samostatnú radu
    for section in sections[1:]:
        lines = section.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()

        if title and body:
            items.append({"title": title, "body": body})
            
    if not items:
        return 0

    texts = [f"Téma: {item['title']}\nInformace: {item['body']}" for item in items]
    logger.info(f"Generujem embeddingy pre {len(items)} informačných blokov...")
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()
    
    for item, vector in zip(items, vectors):
        # Vytvoríme unikátne ID z názvu sekcie (aby sa pri reštarte nepridávali duplikáty)
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, item['title']))
        
        points.append(PointStruct(
            id=chunk_id,
            vector=vector,
            payload={"title": item['title'], "content": item['body']}
        ))
    if points:
        client.upsert(collection_name=COLLECTION_KNOWLEDGE, points=points)
        logger.info(f"Úspešne rozsekaných a uložených {len(points)} informačných blokov z manuálu.")

    return len(points)

def search_knowledge(query: str, top_k=3):
    # Vyhľadá len 3 najrelevantnejšie odseky z manuálu (extrémne šetrenie tokenov!)
    if not collection_exists(COLLECTION_KNOWLEDGE): return[]
    query_vector = model.encode(query, show_progress_bar=False).tolist()
    hits = client.search(collection_name=COLLECTION_KNOWLEDGE, query_vector=query_vector, limit=top_k)
    return[hit.payload for hit in hits]
