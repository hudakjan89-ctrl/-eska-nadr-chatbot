import httpx
import xml.etree.ElementTree as ET
import hashlib

def get_product_id(url: str) -> str:
    # Vytvorí unikátne ID na základe URL
    return hashlib.md5(url.encode('utf-8')).hexdigest()

async def fetch_and_parse_xml():
    url = "https://www.ceskanadrz.cz/universal.xml"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=60.0)
            
        root = ET.fromstring(response.content)
        products =[]
        
        # Universal/Heureka feed zvyčajne používa tag SHOPITEM alebo ITEM
        items = root.findall('.//SHOPITEM')
        if not items:
            items = root.findall('.//ITEM')
            
        for item in items:
            name = item.find('PRODUCTNAME')
            if name is None: name = item.find('NAME')
            
            link = item.find('URL')
            desc = item.find('DESCRIPTION')
            price = item.find('PRICE_VAT')
            cat = item.find('CATEGORYTEXT')
            
            if name is not None and link is not None:
                products.append({
                    'id': get_product_id(link.text),
                    'name': name.text,
                    'url': link.text,
                    'description': desc.text[:600] if desc is not None and desc.text else '',
                    'price': price.text if price is not None else '',
                    'category': cat.text if cat is not None else ''
                })
        return products
    except Exception as e:
        print(f"Chyba pri parsovaní XML: {e}")
        return[]
