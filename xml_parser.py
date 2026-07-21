import httpx
import xml.etree.ElementTree as ET
import uuid
import re
import unicodedata
import logging
from alerter import fire_alert

logger = logging.getLogger("ceska_nadrz.xml_parser")

def _normalize_text(text: str) -> str:
    text = unicodedata.normalize('NFD', text or '')
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower()

def get_product_id(url: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return " ".join(cleantext.split())

def detect_construction_type(name: str, url: str = "") -> str:
    combined = _normalize_text(f"{name} {url}")
    if "dvouplast" in combined:
        return "dvouplastova"
    if "samonos" in combined:
        return "samonosna"
    if "obetonov" in combined:
        return "obetonovani"
    if "nadzem" in combined:
        return "nadzemni"
    return "neznamo"

def detect_placement(name: str, url: str = "") -> str:
    combined = _normalize_text(f"{name} {url}")
    if "nadzem" in combined:
        return "nadzemni"
    if any(term in combined for term in ("samonos", "obetonov", "dvouplast", "dvouplastov")):
        return "podzemni"
    if any(term in combined for term in ("nadrz", "jimk", "septik", "cistick", "cistirn", "sacht")):
        return "podzemni"
    return "neznamo"


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

                product_name = name.text.strip()
                product_url = link.text.strip()
                products.append({
                    'id': get_product_id(product_url),
                    'name': product_name,
                    'url': product_url,
                    'image_url': img_url,
                    'description': desc_text,
                    'price': price_val,
                    'category': cat.text.strip() if cat is not None and cat.text else '',
                    'placement': detect_placement(product_name, product_url),
                    'construction_type': detect_construction_type(product_name, product_url),
                })
                
        logger.info(f"Úspěšně staženo a připraveno {len(products)} produktů (včetně obrázků).")
        return products
        
    except Exception as e:
        error_msg = f"Kritická chyba při stahování/parsování XML: {e}"
        logger.exception(error_msg)
        fire_alert(error_msg)
        return[]
