# Manuál pro úpravu znalostní báze chatbota (TRAINING)

Tento dokument slouží jako interní příručka pro majitele e-shopu a jeho tým. Vysvětluje, jak funguje znalostní báze chatbota, a krok za krokem popisuje, jak bezpečně přidávat a upravovat informace, ze kterých chatbot čerpá. 

Znalostní báze je hlavním zdrojem všech netechnických i technických informací mimo produktový katalog (ten se plní automaticky z XML feedu e-shopu). Je tedy naprosto klíčová pro to, aby chatbot dokázal odpovídat správně, srozumitelně a odborně.

---

## Obsah
1. [Kde se databáze nachází](#kde-se-databáze-nachází)
2. [Jak přidat nebo upravit informaci](#jak-přidat-nebo-upravit-informaci)
3. [Jak se změny dostanou do chatbota](#jak-se-změny-dostanou-do-chatbota)
4. [Ruční reindex](#ruční-reindex)
5. [Dobré praktiky pro psaní obsahu](#dobré-praktiky-pro-psaní-obsahu)
6. [Co dělat a NEdělat](#co-dělat-a-nedělat)
7. [Kontakt v případě problémů](#kontakt-v-případě-problémů)

---

## Kde se databáze nachází

Hlavní soubor s databází se nachází přímo v kořenovém adresáři (rootu) vašeho projektu.
Tento soubor se jmenuje: **`knowledge_base.md`**

Jedná se o běžný textový soubor formátovaný pomocí jednoduchého jazyka Markdown. Díky tomu je velmi snadno čitelný jak pro člověka, tak pro stroj.

Dokument je logicky rozdělen na tematické sekce pomocí nadpisů třetí a čtvrté úrovně (`###` a `####`). 

Každá sekce, která je uvozena nadpisem `###`, se při zpracování (indexování) stává samostatným, izolovaným a prohledávatelným blokem informací. Těmto blokům se odborně říká „chunky“ a ukládají se do vektorové databáze RAG (Retrieval-Augmented Generation). Chatbot následně při své práci vybírá ty chunky, které nejlépe odpovídají na dotaz zákazníka.

---

## Jak přidat nebo upravit informaci

Pokud chcete upravit existující informace, přidat nové téma nebo smazat zastaralý obsah, postupujte krok za krokem podle tohoto návodu:

### 1. Otevření souboru
Otevřete soubor `knowledge_base.md` ve vašem oblíbeném textovém editoru. 
Můžete použít moderní editory jako je VS Code, Notepad++, Sublime Text nebo jakýkoli jiný nástroj, který podporuje úpravy prostého textu a formát Markdown.

### 2. Nalezení příslušné sekce
Pokud upravujete stávající informaci, najděte příslušnou sekci podle jejího nadpisu.
Využijte funkci hledání ve vašem editoru (obvykle `Ctrl+F` nebo `Cmd+F`).
Hledejte například texty jako:
- `### 10. Doprava`
- `### 20.2 Septik`
- `### 15. Platba a fakturace`

### 3. Vytvoření nové sekce
Pokud vytváříte úplně nové téma, které v dokumentu ještě neexistuje, založte novou sekci s novým `###` nadpisem.
Zařaďte tuto sekci na vhodné místo v dokumentu (např. na konec příslušné kapitoly).

### 4. Vepsání obsahu
Pod samotný nadpis napište váš obsah.
Pište v běžném textu, odstavcích, nebo využijte jednoduché seznamy s pomlčkami (`- Položka seznamu`).

### 5. Uložení a nasazení
Jakmile jste s úpravami spokojeni, soubor uložte.
Poté změnu standardně commitněte do gitu a případně pushněte/deployněte na server podle toho, jak máte nastavený proces vývoje.

### Důrazné upozornění k číslování
Nikdy nezasahujte do číslování u existujících sekcí! 
Například: Pokud sekce nese název `### 9.1 Výběr čerpadla`, nikdy neměňte ono `9.1`.
Toto číslování má smysl nejen pro lidskou orientaci v dlouhém dokumentu, ale především se podle těchto přesných nadpisů generují unikátní ID chunků. Změna nadpisu u existující sekce by mohla systém splést a rozbít indexování v databázi.

---

## Jak se změny dostanou do chatbota

Poté, co provedete úpravu v souboru `knowledge_base.md`, se tyto změny neprojeví v chatbotovi ihned samy od sebe. Aby je chatbot mohl začít využívat, musí proběhnout tzv. reindexace.

Změny se do vědomostí chatbota propisují těmito automatickými způsoby:

### A) Při startu aplikace
Při každém úplném restartu vaší aplikace se automaticky spustí systémová funkce `load_and_upsert_knowledge()`. 
Tato funkce v první řadě přečte celý soubor `knowledge_base.md`. Následně ho pečlivě rozdělí na jednotlivé sekce podle `###` nadpisů a přepíše všechny tyto chunky do vektorové databáze Qdrant. Stará data jsou přepsána novými.

### B) Pravidelný cyklus na pozadí
Váš systém je navržen tak, že reindex se spouští zcela automaticky každých 6 hodin. 
Zajišťuje to nástroj zvaný APScheduler, který běží tiše na pozadí. 

**Co to znamená v praxi?**
Jakmile úpravu v souboru uložíte a nahrajete na server (commit/deploy), změna se aktivuje:
- Buď **okamžitě**, pokud vzápětí dojde k restartu aplikace.
- Nebo **nejpozději do 6 hodin** v rámci výše zmíněného pravidelného cyklu.

Pokud potřebujete provést okamžitou aktualizaci bez nutnosti čekat a bez nutnosti restartovat celou aplikaci, podívejte se do následující sekce.

---

## Ruční reindex

V aktuální verzi produkční aplikace neexistuje v uživatelském rozhraní ani v admin panelu žádné tlačítko pro ruční spuštění reindexu.

### Doporučené rozšíření do budoucna
Je vřele doporučeno přidat do backendu (například do souboru `admin.py` nebo `main.py`) jednoduchý administrační endpoint. Tento endpoint by mohl vypadat například takto: `POST /admin/reindex-knowledge`.

Účelem tohoto endpointu by bylo bezpečně zavolat funkci `load_and_upsert_knowledge()` a vrátit jako odpověď celkový počet nově naindexovaných sekcí. 

Po přidání a zprovoznění tohoto endpointu by stačilo poslat POST request (například přes nástroj curl, Postman, nebo přes k tomu určené tlačítko v admin panelu). Změna by v takovém případě byla okamžitě aktivní pro všechny nové konverzace bez jakéhokoliv čekání na 6hodinový reindex cyklus.

### Ukázka kódu pro vývojáře
Zde je příklad, jak by takový endpoint mohl v reálném kódu vypadat (upozornění: jedná se pouze o ukázku, v tuto chvíli není na serveru aktivní):

```python
@app.post("/admin/reindex-knowledge")
async def manual_reindex():
    try:
        # Volání funkce pro smazání starých a uložení nových dat do Qdrantu
        chunks_count = load_and_upsert_knowledge()
        return {
            "status": "success", 
            "message": f"Úspěšně indexováno {chunks_count} sekcí."
        }
    except Exception as e:
        return {
            "status": "error", 
            "message": str(e)
        }
```

---

## Dobré praktiky pro psaní obsahu

Aby chatbot správně rozuměl vašemu textu, efektivně v něm vyhledával a poskytoval zákazníkům ty nejlepší možné odpovědi, dodržujte striktně následující doporučení:

### 1. Tematická čistota
Každá sekce začínající `###` nadpisem by měla řešit **pouze jedno samostatné téma**. 
Chatbot totiž při zodpovídání dotazu zákazníka tahá z databáze celé sekce, ne izolované věty. Pokud smícháte dopravu a technické vlastnosti čerpadel do jednoho bloku, chatbot může být velmi zmatený.

### 2. Ideální délka sekce
Ideální délka jedné logické sekce je zhruba **50–500 slov**.
- Příliš krátké sekce (1–2 věty) se vektorové databázi velmi špatně a nepřesně vyhledávají, protože obsahují málo klíčových slov a kontextu.
- Příliš dlouhé sekce se zase nevejdou do paměťového kontextu modelu a chatbot v takovém množství textu snadno ztratí přehled.

### 3. Minimum formátování
Vyhýbejte se používání jakýchkoliv emoji, složitých markdown tabulek a zbytečných zanořených nadpisů (např. `####` a další). Zcela vynechte vizuální oddělovače typu `---`. Chatbot má ve svém systémovém nastavení výslovně zakázáno reprodukovat takové formátování a příliš komplikovaná struktura ho může mást a nutit k halucinacím.

### 4. Plné věty
Představte si, že dokument píšete pro cizince, který oboru vůbec nerozumí.
Pište v celých, jasných a strukturovaných větách. Důrazně se vyhýbejte izolovaným odrážkám (bullet pointům), kterým chybí okolní kontext. Místo „- 150 litrů“ napište „- Doporučený denní objem vody na jednu osobu je 150 litrů.“.

### 5. Konzistentní názvosloví
Používejte přesně ty samé pojmy, které obvykle ve svých dotazech hledají vaši zákazníci. Zahrňte pro jistotu synonyma. 
Například: Uvádějte „dešťovka“ i „dešťová voda“, „septik“ i „tříkomorový septik“, „jímka“ i „žumpa“. Tím rapidně zvýšíte úspěšnost vyhledávání.

### 6. Zápis do sekce FAQ
Pokud do dokumentu přidáváte odpovědi na Často kladené dotazy (FAQ), vždy je formátujte přesně podle tohoto pevného vzoru. Pokud otázku a odpověď nedodržíte, chatbot ji v textu nemusí najít:

- **Otázka:** text otázky na jednom řádku
- **Odpověď:** text odpovědi hned na dalším řádku

Příklad:
- **Otázka:** Jak často se musí vyvážet jímka 10 m³?
  **Odpověď:** U běžné 4členné domácnosti je to obvykle každé 3–5 týdnů, v závislosti na spotřebě vody.

---

## Co dělat a NEdělat

Pro zachování maximální kvality a spolehlivosti odpovědí dodržujte v dokumentu tyto zásady:

### ❌ Cemu se absolutně vyhnout

- ❌ **Nepřidávejte** do znalostní báze konkrétní čísla paragrafů, znění zákonů ani čísla technických norem a nařízení (jako například zmiňovat „NV 401/2015 Sb.“). Jazykové modely mají tendenci se na tyto identifikátory upnout, aplikovat na ně svá předtrénovaná (a často chybná) data a vyvozovat z nich nevyžádané a nesprávné právní závěry, které pak suverénně servírují zákazníkovi. Pište raději neutrálně, např.: „Naše produkty splňují české legislativní normy, ale konkrétní povolení vydává místní úřad.“
- ❌ **Neuvádějte** nikdy konkrétní ceny produktů ve znalostní bázi! Ceny, skladové dostupnosti a parametry konkrétních položek se do chatbota tahají dynamicky a zcela automaticky z XML feedu e-shopu. Zápisem ceny do `knowledge_base.md` byste riskovali, že bot nabídne starou cenu.
- ❌ **Nepřidávejte** zbytečné marketingové fráze a slovní vatu typu „náš produkt je absolutně nejlepší na trhu“, „garantujeme špičkovou nadpozemskou kvalitu“. Chatbot není copywriter a tyto texty bude tupě přepisovat zákazníkům jako doložená objektivní fakta, což ve finále zní velmi neprofesionálně a nedůvěryhodně.
- ❌ **Neodstraňujte** celé sekce s nadpisy `###`, které už nepoužíváte. Je mnohem lepší je pouze zkrátit na jedno oznámení, zpřesnit nebo upravit text uvnitř. Zabráníte tak rozbití číselné struktury a indexování.

### ✅ Co je naopak žádané

- ✅ **Pravidelně kontrolujte**, co bot reálně odpovídá vašim zákazníkům. Dělejte to v historii konverzací (například nahlížením do databáze nebo přes endpoint `/admin/history`). Pokud si všimnete, že chatbot dává opakovaně nepřesné, zmatečné nebo nesmyslné odpovědi na určitou otázku, okamžitě upravte, doplňte nebo přeformulujte příslušnou sekci v `knowledge_base.md`. Bot se to naučí k dalšímu updatu a už chybu neudělá.

---

## Kontakt v případě problémů

Pokud si při úpravách nejste něčím jistí, obáváte se, že jste dokument poškodili, nebo pokud po vaší nedávné editaci začal chatbot zčistajasna odpovídat nelogicky, nepanikařte a kontaktujte technickou podporu projektu. 

Změny v souboru `knowledge_base.md` naprosto nejsou destruktivní. Jelikož je projekt verzován pod kontrolním systémem Git, lze jakoukoliv vaši změnu pomocí Git historie snadno a rychle vrátit do původního, stoprocentně funkčního stavu. Vaše data jsou tak vždy v bezpečí.
