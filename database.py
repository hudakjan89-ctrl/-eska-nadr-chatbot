import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

print("Načítavam jazykový AI model (Qdrant)...")
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# Qdrant si vytvorí zložku priamo v projekte
client = QdrantClient(path="./qdrant_db")
COLLECTION_NAME = "ceskanadrz_products"

def init_db():
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )

def upsert_products(products):
    init_db()
    points =[]
    for prod in products:
        # Spojíme Názov, Kategóriu a Popis do jednej vety, aby to AI lepšie pochopilo
        text_to_embed = f"Název: {prod['name']} Kategorie: {prod.get('category', '')} Popis: {prod.get('description', '')}"
        
        vector = model.encode(text_to_embed).tolist()
        points.append(PointStruct(
            id=prod['id'],
            vector=vector,
            payload=prod
        ))
    
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"Úspešne aktualizovaných {len(points)} produktov v databáze.")

def search_products(query: str, top_k=7):
    # Vyhľadá 7 najlepších produktov
    if not client.collection_exists(COLLECTION_NAME): 
        return[]
    
    query_vector = model.encode(query).tolist()
    hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k
    )
    return[hit.payload for hit in hits]
