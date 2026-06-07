import os
import uuid
import logging
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("ceska_nadrz.database")

logger.info("Načítavam jazykový AI model (Qdrant)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

client = QdrantClient(path="./qdrant_db")
COLLECTION_PRODUCTS = "ceskanadrz_products"
COLLECTION_KNOWLEDGE = "ceskanadrz_knowledge"  # Nová databáza pre vedomosti

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
    points =[]
    for prod in products:
        text_to_embed = f"Název: {prod['name']} Kategorie: {prod.get('category', '')} Popis: {prod.get('description', '')}"
        vector = model.encode(text_to_embed, show_progress_bar=False).tolist()
        points.append(PointStruct(
            id=prod['id'],
            vector=vector,
            payload=prod
        ))
    if points:
        client.upsert(collection_name=COLLECTION_PRODUCTS, points=points)
        logger.info(f"Úspešne aktualizovaných {len(points)} produktov v databáze.")

def search_products(query: str, top_k=10):
    if not collection_exists(COLLECTION_PRODUCTS): return[]
    query_vector = model.encode(query, show_progress_bar=False).tolist()
    hits = client.search(collection_name=COLLECTION_PRODUCTS, query_vector=query_vector, limit=top_k)
    return [hit.payload for hit in hits]

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

    # Preskočíme úplne prvý blok (hlavný nadpis dokumentu), ten nepotrebujeme ako samostatnú radu
    for section in sections[1:]:
        lines = section.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[1:]).strip()

        if title and body:
            # Spojíme nadpis a telo do jedného textu pre AI
            text_to_embed = f"Téma: {title}\nInformace: {body}"
            vector = model.encode(text_to_embed, show_progress_bar=False).tolist()

            # Vytvoríme unikátne ID z názvu sekcie (aby sa pri reštarte nepridávali duplikáty)
            chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, title))

            points.append(PointStruct(
                id=chunk_id,
                vector=vector,
                payload={"title": title, "content": body}
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
