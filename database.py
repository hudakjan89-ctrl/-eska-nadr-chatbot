import os
import re
import time
import threading
import unicodedata
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from xml_parser import detect_placement, detect_construction_type

logger = logging.getLogger("ceska_nadrz.database")

logger.info("Načítavam jazykový AI model (Qdrant)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

_qdrant_path = os.getenv("QDRANT_PATH")
if not _qdrant_path:
    _data_dir = os.getenv("DATA_DIR", "data")
    _qdrant_path = os.path.join(_data_dir, "qdrant_db")
os.makedirs(_qdrant_path, exist_ok=True)
logger.info("Qdrant path: %s", _qdrant_path)

_client: QdrantClient | None = None
_client_lock = threading.Lock()

def get_qdrant_client() -> QdrantClient:
    """Lazy singleton — Qdrant local path nepodporuje viac procesov naraz."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        last_error = None
        for attempt in range(8):
            try:
                _client = QdrantClient(path=_qdrant_path)
                return _client
            except RuntimeError as exc:
                last_error = exc
                if "already accessed" in str(exc).lower() and attempt < 7:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "Qdrant DB je zamknutá (pokus %d/8), čakám %ds — typicky pri redeployi.",
                        attempt + 1,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                raise
        if last_error:
            raise last_error
        raise RuntimeError("Nepodarilo sa inicializovať Qdrant klienta.")

COLLECTION_PRODUCTS = "ceskanadrz_products"
COLLECTION_KNOWLEDGE = "ceskanadrz_knowledge"

_product_cache: list[dict] = []
_knowledge_section_count = 0

PLACEMENT_SYNONYMS = {
    "podzemni": "podzemní do země pod zemí samonosná k obetonování dvouplášťová zakopaná",
    "nadzemni": "nadzemní volně stojící nad zemí",
    "neznamo": "",
}

CONSTRUCTION_LABELS = {
    "samonosna": "samonosná",
    "obetonovani": "k obetonování",
    "dvouplastova": "dvouplášťová",
    "nadzemni": "nadzemní",
}

ACCESSORY_HINTS = (
    "sběrač", "sberac", "zásuvka", "zasuvka", "poklop", "hadice", "filtr",
    "čerpadlo", "cerpadlo", "přečerpávací stanice", "precerpavaci stanice",
    "hlásič", "hlasic", "plovák", "plovak", "sání", "sani",
)

TANK_HINTS = ("nadrz", "jimk", "septik", "cistick", "cistirn", "sacht", "odlucovac")

CZECH_NUMBER_WORDS = {
    "jedna": "1", "jeden": "1", "dva": "2", "tri": "3", "ctyri": "4", "pet": "5",
    "sest": "6", "sedm": "7", "osm": "8", "devet": "9", "deset": "10",
    "jedenact": "11", "dvanact": "12", "trinact": "13", "ctrnact": "14", "patnact": "15",
    "dvacet": "20", "tricet": "30", "ctyricet": "40", "padesat": "50",
}

def _remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text or '') if unicodedata.category(c) != 'Mn')

def _normalize_text(text: str) -> str:
    text = _remove_diacritics((text or "").lower())
    text = text.replace("m³", "m3").replace(",", ".")
    text = re.sub(r'(\d+)\s*m\s*3', r'\1m3', text)
    text = re.sub(r'(\d+)\s*m\s*³', r'\1m3', text)
    return text

def normalize_volume_query(query: str) -> str:
    q = _normalize_text(query)
    for word, num in CZECH_NUMBER_WORDS.items():
        q = re.sub(rf'\b{word}\b', num, q)
    q = re.sub(r'\bkubik\w*\b', 'm3', q)
    q = re.sub(r'(\d+)\s*m\s*3', r'\1m3', q)
    q = re.sub(r'(\d+)\s+m3', r'\1m3', q)
    q = re.sub(r'(\d+(?:\.\d+)?)\s*m(?!3|2|m|\d)', r'\1m3', q)
    return q

def _tokenize(text: str) -> set[str]:
    text = _normalize_text(text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return {token for token in text.split() if len(token) > 1}

def _extract_volumes(text: str) -> set[str]:
    normalized = normalize_volume_query(text)
    volumes = set()
    for match in re.finditer(r'(\d+(?:\.\d+)?)m3', normalized.replace(" ", "")):
        volumes.add(match.group(1).replace(".", ","))
        volumes.add(match.group(1).replace(",", "."))
    return volumes

def _product_volumes(prod: dict) -> set[str]:
    combined = f"{prod.get('name', '')} {prod.get('url', '')}"
    return _extract_volumes(combined)

def detect_query_intent(query: str) -> dict:
    q = _normalize_text(query)
    return {
        "wants_underground": any(term in q for term in (
            "podzemni", "pod zem", "do zeme", "zakopan", "samonos", "obetonov", "dvouplast",
        )),
        "wants_aboveground": any(term in q for term in ("nadzemni", "nad zem", "volne stojici")),
        "wants_retention": "retenc" in q or "pozarn" in q,
        "wants_rainwater": any(term in q for term in ("destov", "destovka", "srazkov", "zaliv")),
        "wants_drinking": any(term in q for term in ("pitn", "pitna voda")),
        "wants_sewage": any(term in q for term in ("splask", "odpadn", "kalov")),
        "wants_accessory": any(term in q for term in ACCESSORY_HINTS),
        "wants_tank": any(term in q for term in TANK_HINTS) or "retenc" in q,
        "volumes": _extract_volumes(q),
    }

def detect_product_purpose(prod: dict) -> str:
    combined = _normalize_text(f"{prod.get('name', '')} {prod.get('category', '')} {prod.get('url', '')}")
    if any(term in combined for term in ("destov", "destovka", "srazkov")):
        return "destovka"
    if any(term in combined for term in ("pitn",)):
        return "pitna"
    if any(term in combined for term in ("pozarn", "retenc")):
        return "pozarni_retencni"
    if any(term in combined for term in ("jimk", "septik", "splask", "kalov", "odpadn")):
        return "splasky"
    if any(term in combined for term in ACCESSORY_HINTS):
        return "accessory"
    return "general"

def _is_tank_product(prod: dict) -> bool:
    name = _normalize_text(prod.get("name", ""))
    if not any(hint in name for hint in TANK_HINTS):
        return False
    return not any(hint in name for hint in ACCESSORY_HINTS)

def _is_accessory_product(prod: dict) -> bool:
    combined = _normalize_text(f"{prod.get('name', '')} {prod.get('category', '')}")
    return any(hint in combined for hint in ACCESSORY_HINTS)

def product_embedding_text(prod: dict) -> str:
    placement = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
    construction = prod.get("construction_type") or detect_construction_type(prod.get("name", ""), prod.get("url", ""))
    placement_synonyms = PLACEMENT_SYNONYMS.get(placement, "")
    construction_label = CONSTRUCTION_LABELS.get(construction, "")
    purpose = detect_product_purpose(prod)
    purpose_labels = {
        "destovka": "nádrž na dešťovou vodu dešťovka",
        "pitna": "nádrž na pitnou vodu",
        "pozarni_retencni": "požární retenční nádrž",
        "splasky": "jímka septik splašky",
        "accessory": "příslušenství doplněk",
    }
    return (
        f"Název: {prod['name']} "
        f"Umístění: {placement_synonyms} "
        f"Provedení: {construction_label} "
        f"Účel: {purpose_labels.get(purpose, '')} "
        f"Kategorie: {prod.get('category', '')} "
        f"Popis: {prod.get('description', '')}"
    )

def expand_search_query(query: str) -> str:
    q = normalize_volume_query(query)
    extra = []

    if any(term in q for term in ("podzemni", "pod zem", "do zeme", "zakopan", "zakopat")):
        extra.extend(["samonosná nádrž", "nádrž k obetonování", "dvouplášťová nádrž", "podzemní"])
    if any(term in q for term in ("nadzemni", "nad zem", "volne stojici", "volne stoj")):
        extra.extend(["nadzemní volně stojící"])
    if "retenc" in q or "pozarn" in q:
        extra.extend(["požární nádrž", "retenční nádrž", "nádrž na dešťovou vodu"])
    if any(term in q for term in ("destov", "destovka", "srazkov", "zaliv")):
        extra.extend(["nádrž na dešťovou vodu", "samonosná nádrž"])
    if any(term in q for term in ("pitn", "pitna voda")):
        extra.extend(["nádrž na pitnou vodu"])
    if any(term in q for term in ("hlasic", "hlásič", "naplnen")):
        extra.extend(["hlásič naplnění jímky nádrže septiku"])
    if any(term in q for term in ("cerpadl", "čerpadl", "plovak", "plovák")):
        extra.extend(["kalové čerpadlo čerpadlo plovák"])
    if any(term in q for term in ("jimk", "septik", "zump")):
        extra.extend(["jímka septik"])

    if extra:
        return f"{query} {' '.join(extra)}"
    return query

def _lexical_score(prod: dict, query: str, intent: dict) -> float:
    name = _normalize_text(prod.get("name", ""))
    category = _normalize_text(prod.get("category", ""))
    description = _normalize_text(prod.get("description", ""))
    combined = f"{name} {category} {description}"
    query_tokens = _tokenize(query)
    product_tokens = _tokenize(combined)
    if not query_tokens:
        return 0.0

    overlap = query_tokens.intersection(product_tokens)
    score = len(overlap) * 12.0

    for token in query_tokens:
        if len(token) >= 4 and token in combined:
            score += 8.0

    if intent["volumes"]:
        product_volumes = _product_volumes(prod)
        if product_volumes.intersection(intent["volumes"]):
            score += 80.0
        elif intent["volumes"]:
            score -= 25.0

    placement = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
    construction = prod.get("construction_type") or detect_construction_type(prod.get("name", ""), prod.get("url", ""))
    purpose = detect_product_purpose(prod)

    if intent["wants_underground"]:
        if placement == "podzemni":
            score += 50.0
        if placement == "nadzemni" or "nadzem" in name:
            score -= 120.0
    if intent["wants_aboveground"]:
        if placement == "nadzemni":
            score += 50.0
        if placement == "podzemni":
            score -= 40.0

    if intent["wants_retention"]:
        if purpose == "pozarni_retencni":
            score += 70.0
        elif purpose == "destovka":
            score += 35.0
        elif purpose == "pitna":
            score -= 20.0

    if intent["wants_rainwater"]:
        if purpose == "destovka":
            score += 80.0
        elif purpose == "pitna":
            score -= 60.0
        elif placement == "nadzemni":
            score -= 55.0
    if intent["wants_drinking"]:
        if purpose == "pitna":
            score += 80.0
        elif purpose == "destovka":
            score -= 30.0

    if intent["wants_accessory"]:
        if _is_accessory_product(prod):
            score += 90.0
        elif _is_tank_product(prod):
            score -= 30.0
    elif intent["wants_tank"] or intent["wants_retention"] or intent["wants_rainwater"] or intent["wants_drinking"]:
        if _is_tank_product(prod):
            score += 45.0
        elif _is_accessory_product(prod):
            score -= 35.0

    if "dvouplast" in query_tokens or "dvouplastova" in _normalize_text(query):
        if construction == "dvouplastova":
            score += 40.0
    if "samonos" in _normalize_text(query) and construction == "samonosna":
        score += 35.0
    if "obetonov" in _normalize_text(query) and construction == "obetonovani":
        score += 35.0

    if "retenc" in _normalize_text(query) and "nadzem" in name and not intent["wants_aboveground"]:
        score -= 100.0

    return score

def _embedding_rank_score(rank: int, total: int) -> float:
    if total <= 1:
        return 100.0
    return max(0.0, 100.0 - (rank * 100.0 / max(total - 1, 1)))

def _product_rank_score(prod: dict, query: str, embedding_rank: int = 0, embedding_total: int = 1) -> float:
    intent = detect_query_intent(query)
    lexical = _lexical_score(prod, query, intent)
    embedding = _embedding_rank_score(embedding_rank, embedding_total)
    return lexical * 0.65 + embedding * 0.35

def rerank_products(products: list, query: str, embedding_ranks: dict | None = None) -> list:
    if not products:
        return products
    embedding_ranks = embedding_ranks or {}
    total = len(products)

    def sort_key(prod: dict) -> float:
        rank = embedding_ranks.get(prod.get("url") or prod.get("id"), total)
        return _product_rank_score(prod, query, rank, total)

    return sorted(products, key=sort_key, reverse=True)

def _lexical_search_products(query: str, limit: int = 30) -> list[dict]:
    if not _product_cache:
        return []
    intent = detect_query_intent(query)
    scored = []
    for prod in _product_cache:
        score = _lexical_score(prod, query, intent)
        if score > 0:
            scored.append((score, prod))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [prod for _, prod in scored[:limit]]

def collection_exists(coll_name):
    try:
        collections_response = get_qdrant_client().get_collections()
        for collection in collections_response.collections:
            if collection.name == coll_name:
                return True
        return False
    except Exception:
        return False

def init_db():
    if not collection_exists(COLLECTION_PRODUCTS):
        logger.info(f"Vytváram databázu: {COLLECTION_PRODUCTS}")
        get_qdrant_client().create_collection(collection_name=COLLECTION_PRODUCTS, vectors_config=VectorParams(size=384, distance=Distance.COSINE))
    
    if not collection_exists(COLLECTION_KNOWLEDGE):
        logger.info(f"Vytváram databázu: {COLLECTION_KNOWLEDGE}")
        get_qdrant_client().create_collection(collection_name=COLLECTION_KNOWLEDGE, vectors_config=VectorParams(size=384, distance=Distance.COSINE))

def _merge_product_results(*lists: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for products in lists:
        for prod in products:
            key = prod.get("url") or prod.get("id")
            if key and key not in seen:
                seen.add(key)
                merged.append(prod)
    return merged

def upsert_products(products):
    global _product_cache
    init_db()
    if not products:
        return
    enriched = []
    for prod in products:
        payload = dict(prod)
        payload["placement"] = prod.get("placement") or detect_placement(prod.get("name", ""), prod.get("url", ""))
        payload["construction_type"] = prod.get("construction_type") or detect_construction_type(prod.get("name", ""), prod.get("url", ""))
        enriched.append(payload)

    _product_cache = enriched
    points = []
    texts = [product_embedding_text(prod) for prod in enriched]
    logger.info(f"Generujem embeddingy pre {len(enriched)} produktov...")
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()
    for prod, vector in zip(enriched, vectors):
        points.append(PointStruct(
            id=prod['id'],
            vector=vector,
            payload=prod,
        ))
    if points:
        get_qdrant_client().upsert(collection_name=COLLECTION_PRODUCTS, points=points)
        logger.info(f"Úspešne aktualizovaných {len(points)} produktov v databáze.")

def search_products(query: str, top_k=10):
    if not collection_exists(COLLECTION_PRODUCTS):
        return []

    expanded_query = expand_search_query(query)
    intent = detect_query_intent(expanded_query)
    fetch_k = max(top_k * 8, 80)
    if intent["wants_accessory"]:
        fetch_k = max(fetch_k, 60)

    query_vector = model.encode(expanded_query, show_progress_bar=False).tolist()
    hits = get_qdrant_client().search(collection_name=COLLECTION_PRODUCTS, query_vector=query_vector, limit=fetch_k)
    embedding_products = [hit.payload for hit in hits]
    embedding_ranks = {
        (hit.payload.get("url") or hit.payload.get("id")): idx
        for idx, hit in enumerate(hits)
    }

    lexical_products = _lexical_search_products(expanded_query, limit=max(top_k * 4, 40))
    merged = _merge_product_results(embedding_products, lexical_products)
    ranked = rerank_products(merged, expanded_query, embedding_ranks)
    return ranked[:top_k]

def load_and_upsert_knowledge(filepath="knowledge_base.md"):
    init_db()
    if not os.path.exists(filepath):
        logger.warning(f"Súbor {filepath} neexistuje. Vedomostná databáza sa nenačíta.")
        return 0

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    return upsert_knowledge_content(content)


def upsert_knowledge_content(content: str):
    global _knowledge_section_count
    init_db()
    items = _parse_knowledge_sections(content)

    if not items:
        logger.warning("Knowledge content neobsahuje žiadne platné sekcie (očakávaný formát: ### Nadpis alebo ## Nadpis).")
        _knowledge_section_count = 0
        return 0

    points = []
    texts = [f"Téma: {item['title']}\nInformace: {item['body']}" for item in items]
    logger.info(f"Generujem embeddingy pre {len(items)} informačných blokov...")
    vectors = model.encode(texts, batch_size=32, show_progress_bar=False).tolist()

    for item, vector in zip(items, vectors):
        chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, item['title']))

        points.append(PointStruct(
            id=chunk_id,
            vector=vector,
            payload={"title": item['title'], "content": item['body']}
        ))
    if points:
        get_qdrant_client().upsert(collection_name=COLLECTION_KNOWLEDGE, points=points)
        logger.info(f"Úspešne rozsekaných a uložených {len(points)} informačných blokov z manuálu.")

    _knowledge_section_count = len(points)
    return len(points)


def _parse_knowledge_sections(content: str) -> list[dict]:
    content = (content or "").strip()
    if not content:
        return []

    for level in ("###", "##"):
        pattern = re.compile(rf'^{re.escape(level)}\s+(.+)$', re.MULTILINE)
        matches = list(pattern.finditer(content))
        if not matches:
            continue
        items = []
        for index, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            body = content[start:end].strip()
            if title and body:
                items.append({"title": title, "body": body})
        if items:
            return items
    return []


def refresh_knowledge_section_count() -> int:
    global _knowledge_section_count
    if not collection_exists(COLLECTION_KNOWLEDGE):
        _knowledge_section_count = 0
        return 0
    try:
        info = get_qdrant_client().get_collection(COLLECTION_KNOWLEDGE)
        _knowledge_section_count = int(getattr(info, "points_count", 0) or 0)
    except Exception:
        pass
    return _knowledge_section_count

def search_knowledge(query: str, top_k=3):
    if not collection_exists(COLLECTION_KNOWLEDGE):
        return []
    expanded_query = expand_search_query(query)
    query_vector = model.encode(expanded_query, show_progress_bar=False).tolist()
    hits = get_qdrant_client().search(collection_name=COLLECTION_KNOWLEDGE, query_vector=query_vector, limit=top_k)
    return [hit.payload for hit in hits]

def product_count() -> int:
    return len(_product_cache)

def knowledge_section_count() -> int:
    return _knowledge_section_count

def is_knowledge_index_ready() -> bool:
    if _knowledge_section_count > 0:
        return True
    return refresh_knowledge_section_count() > 0

def is_product_index_ready() -> bool:
    return product_count() > 0
