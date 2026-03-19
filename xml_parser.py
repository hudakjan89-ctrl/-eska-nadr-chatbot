import httpx
import xml.etree.ElementTree as ET
import uuid
import re

def get_product_id(url: str) -> str:
    # Vytvorí plne validné UUID pre Qdrant na základe URL produktu
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))

def clean_html(raw_html: str) -> str:
    """Odstráni HTML tagy z popisu pre lepšie pochopenie umelou inteligenciou"""
    if not raw_html:
        return ""
    # Odstráni všetky <tagy>
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, ' ', raw_html)
    # Odstráni viacnásobné medzery a entery
    return " ".join(cleantext.split())

async def fetch_and_parse_xml():
    url = "https://www.ceskanadrz.cz/universal.xml"
    print("Stahujem XML feed (Universal)...")
    try:
        async with httpx.AsyncClient() as client:
            # Universal feed môže byť veľký, dáme mu dlhší čas na stiahnutie
            response = await client.get(url, timeout=120.0)
            
        root = ET.fromstring(response.content)
        products =[]
        
        # Získame všetky produkty pod tagom SHOPITEM
        items = root.findall('.//SHOPITEM')
        if not items:
            items = root.findall('.//ITEM')
            
        for item in items:
            # Hľadáme názov produktu (podľa tvojho screenshotu je to <PRODUCT>)
            name = item.find('PRODUCT')
            if name is None: name = item.find('PRODUCTNAME')
            if name is None: name = item.find('NAME')
            
            link = item.find('URL')
            desc = item.find('DESCRIPTION')
            price = item.find('PRICE_VAT')
            cat = item.find('CATEGORYTEXT')
            
            if name is not None and name.text and link is not None and link.text:
                
                # Extrakcia popisu a očistenie od HTML (aby to AI lepšie chápalo)
                desc_text = ""
                if desc is not None:
                    # itertext() spojí text aj v prípade, že je schovaný v <strong> alebo <li>
                    desc_text = "".join(desc.itertext())
                    desc_text = clean_html(desc_text)[:800] # Zoberieme len dôležitý začiatok popisu
                
                # Cena
                price_val = price.text.strip() if price is not None and price.text else ""
                if price_val and "Kč" not in price_val and "CZK" not in price_val:
                    price_val += " Kč"
                    
                products.append({
                    'id': get_product_id(link.text.strip()),
                    'name': name.text.strip(),
                    'url': link.text.strip(),
                    'description': desc_text,
                    'price': price_val,
                    'category': cat.text.strip() if cat is not None and cat.text else ''
                })
                
        print(f"Úspěšně staženo a připraveno {len(products)} produktů do AI databáze.")
        return products
        
    except Exception as e:
        print(f"Kritická chyba při stahování/parsování XML: {e}")
        return
