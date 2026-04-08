import httpx
import xml.etree.ElementTree as ET
import uuid
import re
import logging

logger = logging.getLogger("ceska_nadrz.xml_parser")

def get_product_id(url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return " ".join(cleantext.split())

async def fetch_and_parse_xml():
    url = "https://www.ceskanadrz.cz/universal.xml"
    logger.info("Stahujem XML feed (Universal)...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=120.0)
            
        root = ET.fromstring(response.content)
        products =[]
        
        items = root.findall('.//SHOPITEM')
        if not items:
            items = root.findall('.//ITEM')
            
        for item in items:
            name = item.find('PRODUCT')
            if name is None: name = item.find('PRODUCTNAME')
            if name is None: name = item.find('NAME')
            
            link = item.find('URL')
            desc = item.find('DESCRIPTION')
            price = item.find('PRICE_VAT')
            cat = item.find('CATEGORYTEXT')
            
            # --- ZACHYTENIE OBRÁZKU ---
            img = item.find('IMGURL')
            img_url = img.text.strip() if img is not None and img.text else ""
            
            if name is not None and name.text and link is not None and link.text:
                desc_text = ""
                if desc is not None:
                    desc_text = "".join(desc.itertext())
                    desc_text = clean_html(desc_text)[:800] 
                
                price_val = price.text.strip() if price is not None and price.text else ""
                if price_val and "Kč" not in price_val and "CZK" not in price_val:
                    price_val += " Kč"
                    
                products.append({
                    'id': get_product_id(link.text.strip()),
                    'name': name.text.strip(),
                    'url': link.text.strip(),
                    'image_url': img_url,  # <--- ULOŽENIE OBRÁZKU DO DATABÁZY
                    'description': desc_text,
                    'price': price_val,
                    'category': cat.text.strip() if cat is not None and cat.text else ''
                })
                
        logger.info(f"Úspěšně staženo a připraveno {len(products)} produktů (včetně obrázků).")
        return products
        
    except Exception as e:
        logger.exception(f"Kritická chyba při stahování/parsování XML: {e}")
        return[]
