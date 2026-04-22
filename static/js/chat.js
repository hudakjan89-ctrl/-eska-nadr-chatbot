// static/js/chat.js
(function() {
  const BASE_URL = 'https://nadrz.eniq.eu'; 

  const fontLink = document.createElement('link');
  fontLink.rel = 'stylesheet';
  fontLink.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
  document.head.appendChild(fontLink);

  const cssLink = document.createElement('link');
  cssLink.rel = 'stylesheet';
  cssLink.href = `${BASE_URL}/static/css/style.css`;
  document.head.appendChild(cssLink);

  const chatHTML = `
    <div class="eniq-launcher" id="chatLauncher" aria-label="Otevřít chat" role="button" tabindex="0">
      <div class="eniq-launcher-avatar">
        <img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'">
      </div>
    </div>

    <div class="eniq-panel" id="chatPanel" aria-label="Chat panel" role="dialog">
      <div class="chat-header">
        <div class="chat-header-left">
          <div class="chat-header-avatar">
             <img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'">
          </div>
          <div class="chat-header-info">
            <div class="chat-header-title">Virtuální asistent</div>
            <div class="chat-header-status">
              <span class="status-dot"></span>
              <span id="statusText">Online</span>
            </div>
          </div>
        </div>
        
        <button class="settings-btn" id="settingsBtn" type="button" aria-label="Nastavení">⋮</button>
        
        <div class="settings-menu" id="settingsMenu">
          <div class="settings-item">
            <div class="toggle-container">
              <span class="settings-label" id="expandLabel">Rozšířit chat</span>
              <div class="toggle-switch" id="expandToggle"><div class="toggle-slider"></div></div>
            </div>
          </div>
          <div class="settings-item">
            <div class="toggle-container">
              <span class="settings-label" id="themeLabel">Tmavý režim</span>
              <div class="toggle-switch" id="themeToggle"><div class="toggle-slider"></div></div>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label" for="langSelect" id="langLabel">Jazyk</label>
            <select class="lang-select" id="langSelect">
                <option value="cs">🇨🇿 Čeština</option>
                <option value="sk">🇸🇰 Slovenčina</option>
                <option value="en">🇬🇧 English</option>
                <option value="uk">🇺🇦 Українська</option>
            </select>
          </div>
        </div>

        <button class="close-btn" id="closeBtn" type="button" aria-label="Zavřít">×</button>
      </div>
      
      <div id="chat-box" class="chat-box"></div>
      
      <div class="input-area">
        <input id="message-input" type="text" placeholder="Napište dotaz…" autocomplete="off" />
        <button class="send-btn" id="sendBtn" type="button" aria-label="Odeslat">➤</button>
      </div>
      
      <div class="powered-by">
        Powered by <a href="https://eniq.eu/" target="_blank" rel="noopener">Eniq</a>
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', chatHTML);

  let sessionId = localStorage.getItem("session_id") || null;
  let selectedLang = localStorage.getItem("eniq_lang") || "cs";
  let isExpanded = localStorage.getItem("eniq_expanded") === "true";
  let isDark = localStorage.getItem("eniq_dark") === "true";
  let isChatOpen = sessionStorage.getItem("eniq_is_open") === "true";
  
  let searchingEl = null;
  let quickActionsShown = false;
  let isFirstMessage = true;
  let typingInterval = null;
  
  let activeFlow = null;
  let flowTurnCount = 0;

  function ensureSessionId() {
    if (sessionId) return sessionId;
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      sessionId = window.crypto.randomUUID();
    } else {
      sessionId = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    }
    localStorage.setItem("session_id", sessionId);
    return sessionId;
  }

  async function emitFrontendEvent(eventName, metadata = {}) {
    try {
      const sid = ensureSessionId();
      await fetch(`${BASE_URL}/admin/events/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event_name: eventName,
          session_id: sid,
          language: selectedLang,
          metadata: {
            source: "widget_frontend",
            ...metadata
          }
        })
      });
    } catch (e) {
      console.log("Frontend analytics event failed:", e);
    }
  }

  async function ingestClientMessage(role, content, metadata = {}, eventName = null) {
    try {
      const sid = ensureSessionId();
      await fetch(`${BASE_URL}/admin/messages/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sid,
          role,
          content,
          language: selectedLang,
          metadata: {
            source: "widget_frontend",
            ...metadata
          },
          event_name: eventName
        })
      });
    } catch (e) {
      console.log("Frontend message ingest failed:", e);
    }
  }

  const UI_TEXT = {
    cs: { placeholder: "Napište zprávu…", welcome: "Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu pomoci?", searching: "Odepisuji...", expandLabel: "Rozšířit chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našel jsem vhodný odkaz. Chcete se na něj podívat?", btnYes: "Ano, přejít", btnNo: "Ne, díky", cfFname: "Jméno a Příjmení", cfEmail: "E-mail", cfPhone: "Telefonní číslo", cfNote: "Poznámka", cfBtn: "Odeslat poptávku", cfSuccess: "Děkujeme, {NAME}😊 Vaši zprávu jsme přijali – ozve se vám náš specialista s konkrétním řešením. Mezitím mi klidně napište podrobnosti – můžeme to rovnou doladit.", cfErr: "Vyplňte prosím e-mail.", ctaBtn: "Zanechat kontakt", ctaHeader: "Zanechte nám svůj kontakt:" },
    sk: { placeholder: "Napíšte správu…", welcome: "Dobrý deň! Som asistent e-shopu Česká nádrž. S čím vám môžem pomôcť?", searching: "Odpisujem...", expandLabel: "Rozšíriť chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našiel som vhodný odkaz. Chcete si ho pozrieť?", btnYes: "Áno, prejsť", btnNo: "Nie, vďaka", cfFname: "Meno a Priezvisko", cfEmail: "E-mail", cfPhone: "Telefónne číslo", cfNote: "Poznámka", cfBtn: "Odoslať dopyt", cfSuccess: "Ďakujeme, {NAME}😊 Vašu správu sme prijali – ozve sa vám náš špecialista s konkrétnym riešením. Medzitým mi pokojne napíšte podrobnosti – môžeme to rovno doladiť.", cfErr: "Vyplňte prosím e-mail.", ctaBtn: "Zanechať kontakt", ctaHeader: "Zanechajte nám svoj kontakt:" },
    en: { placeholder: "Type a message…", welcome: "Hello! I'm the Česká nádrž assistant. How can I help you?", searching: "Typing...", expandLabel: "Expand chat", themeLabel: "Dark mode", langLabel: "Language", showOnPage: "I found a relevant link. Would you like to see it?", btnYes: "Yes, open", btnNo: "No, thanks", cfFname: "Full Name", cfEmail: "E-mail", cfPhone: "Phone number", cfNote: "Note", cfBtn: "Send request", cfSuccess: "Thank you, {NAME}😊 We have received your message – our specialist will contact you with a solution. In the meantime, feel free to write me the details – we can fine-tune it.", cfErr: "Please fill out your email.", ctaBtn: "Leave contact", ctaHeader: "Leave us your contact details:" },
    uk: { placeholder: "Напишіть повідомлення…", welcome: "Добрий день! Я асистент інтернет-магазину Česká nádrž. Чим можу допомогти?", searching: "Відповідаю...", expandLabel: "Розгорнути чат", themeLabel: "Темний режим", langLabel: "Мова", showOnPage: "Я знайшов відповідне посилання. Бажаєте подивитися?", btnYes: "Так, перейти", btnNo: "Ні, дякую", cfFname: "Повне ім'я", cfEmail: "E-mail", cfPhone: "Номер телефону", cfNote: "Примітка", cfBtn: "Надіслати запит", cfSuccess: "Дякуємо, {NAME}😊 Ми отримали ваше повідомлення – наш спеціаліст зв'яжеться з вами. Тим часом, ви можете написати мені деталі – ми можемо все узгодити.", cfErr: "Будь ласка, введіть e-mail.", ctaBtn: "Залишити контакт", ctaHeader: "Залиште нам свої контактні дані:" }
  };

  const QUICK_ACTIONS = {
    cs:[ { key: "help_choose", label: "Pomoc s výběrem" }, { key: "shipping", label: "Doprava a platba" }, { key: "installation", label: "Instalace a usazení" }, { key: "size", label: "Jak vybrat velikost" }, { key: "tech_question", label: "Technický dotaz" }, { key: "contact", label: "Kontakt" } ],
    sk:[ { key: "help_choose", label: "Pomoc s výberom" }, { key: "shipping", label: "Doprava a platba" }, { key: "installation", label: "Inštalácia a usadenie" }, { key: "size", label: "Ako vybrať veľkosť" }, { key: "tech_question", label: "Technická otázka" }, { key: "contact", label: "Kontakt" } ],
    en:[ { key: "help_choose", label: "Help with selection" }, { key: "shipping", label: "Shipping & Payment" }, { key: "installation", label: "Installation" }, { key: "size", label: "How to choose size" }, { key: "tech_question", label: "Technical question" }, { key: "contact", label: "Contact" } ],
    uk:[ { key: "help_choose", label: "Допомога у виборі" }, { key: "shipping", label: "Доставка та оплата" }, { key: "installation", label: "Встановлення" }, { key: "size", label: "Як вибрати розмір" }, { key: "tech_question", label: "Технічне питання" }, { key: "contact", label: "Контакти" } ]
  };

  const INSTANT_ANSWERS = {
    cs: { 
      help_choose: "Rád vám pomohu s výběrem vhodného řešení.\nNapište mi, co řešíte (např. jímku, nádrž na vodu, vsakovací systém…) a podíváme se na to.\n\n👉 Pokud budete chtít, můžete mi na sebe nechat kontakt a ozveme se vám.",
      shipping: "Dopravu zajišťujeme po celé ČR.\n• Velké nádrže rozvážíme vlastními vozy ZDARMA. Termín doručení domlouváme předem a řidič vás před příjezdem kontaktuje.\n• Menší zboží zasíláme kurýrní službou. O odeslání vás informujeme, doručení bývá zpravidla následující pracovní den od odeslání.\n\nPlatba je možná převodem nebo při převzetí.",
      installation: "Instalace nádrže, jímky, šachty atd. se vždy přizpůsobuje podmínkám na pozemku.\nNejčastěji záleží na typu půdy, výskytu spodní vody nebo zatížení (např. pojezd).\nSprávné usazení a obsyp jsou klíčové pro dlouhou životnost.",
      size: "Správná velikost nádrže, jímky, septiku, vsaku nebo dalších produktů závisí na konkrétní situaci (počet osob, využití, plocha střechy apod.).\nAbychom doporučili správný objem, potřebujeme pár základních informací.",
      tech_question: "Rád vám pomohu s technickým dotazem.\nNapište mi, co řešíte – hned se na to podívám.",
      contact: "Napište mi, co potřebujete vyřešit, nebo vyplňte formulář níže – ozveme se vám co nejdříve s konkrétním řešením.\n\nPřípadně nás můžete kontaktovat na\n📧 **obchod@ceskanadrz.cz**\n📞 **737 234 461**"
    },
    sk: { 
      help_choose: "Rád vám pomôžem s výberom vhodného riešenia.\nNapíšte mi, čo riešite (napr. žumpu, nádrž na vodu, vsakovací systém…) a pozrieme sa na to.\n\n👉 Ak budete chcieť, môžete mi na seba nechať kontakt a ozveme sa vám.",
      shipping: "Dopravu zabezpečujeme po celej SR aj ČR.\n• Veľké nádrže rozvážame vlastnými vozidlami ZADARMO. Termín doručenia dohadujeme vopred a vodič vás pred príchodom kontaktuje.\n• Menší tovar zasielame kuriérskou službou. O odoslaní vás informujeme, doručenie býva spravidla nasledujúci pracovný deň.\n\nPlatba je možná prevodom alebo pri prevzatí.",
      installation: "Inštalácia nádrže, žumpy, šachty atď. sa vždy prispôsobuje podmienkam na pozemku.\nNajčastejšie záleží na type pôdy, výskyte spodnej vody alebo zaťažení (napr. prejazd).\nSprávne usadenie a obsyp sú kľúčové pre dlhú životnosť.",
      size: "Správna veľkosť nádrže, žumpy, septiku, vsaku alebo ďalších produktov závisí od konkrétnej situácie (počet osôb, využitie, plocha strechy a pod.).\nAby sme odporučili správny objem, potrebujeme zopár základných informácií.",
      tech_question: "Rád vám pomôžem s technickou otázkou.\nNapíšte mi, čo riešite – hneď sa na to pozriem.",
      contact: "Napíšte mi, čo potrebujete vyriešiť, alebo vyplňte formulár nižšie – ozveme sa vám čo najskôr s konkrétnym riešením.\n\nPrípadne nás môžete kontaktovať na\n📧 **obchod@ceskanadrz.cz**\n📞 **737 234 461**"
    },
    en: { 
      help_choose: "I will gladly help you choose a suitable solution.\nWrite to me about what you are looking for (e.g., cesspool, water tank, infiltration system...) and we'll look into it.\n\n👉 If you want, you can leave us your contact details and we will reach out.",
      shipping: "We provide delivery.\n• Large tanks are delivered FREE with our vehicles. Delivery dates are arranged in advance.\n• Smaller items are sent by courier.\n\nPayment is possible by bank transfer or on delivery.",
      installation: "Installation of a tank, cesspool, shaft, etc., always adapts to site conditions.\nIt mostly depends on soil type, groundwater, or load.\nProper placement and backfill are key to longevity.",
      size: "The correct size depends on your specific situation (number of people, usage, roof area, etc.).\nTo recommend the right volume, we need a few basic details.",
      tech_question: "I will gladly help with your technical question.\nWrite me what you need to solve – I will look into it right away.",
      contact: "Write me what you need to resolve, or fill out the form below – we'll contact you with a solution shortly.\n\nOr contact us at\n📧 **obchod@ceskanadrz.cz**\n📞 **737 234 461**"
    },
    uk: { 
      help_choose: "З радістю допоможу вибрати відповідне рішення.\nНапишіть мені, що ви шукаєте (наприклад, вигрібна яма, резервуар для води, інфільтраційна система...) і ми це розглянемо.\n\n👉 Якщо бажаєте, ви можете залишити свої контактні дані, і ми зв'яжемося з вами.",
      shipping: "Ми забезпечуємо доставку.\n• Великі резервуари доставляються БЕЗКОШТОВНО нашими автомобілями.\n• Менші товари відправляються кур'єром.\n\nОплата можлива банківським переказом або при доставці.",
      installation: "Встановлення резервуара завжди адаптується до умов ділянки.\nПравильне встановлення та засипка є ключовими для довговічності.",
      size: "Правильний розмір залежить від вашої конкретної ситуації (кількість осіб, використання, площа даху тощо).\nЩоб рекомендувати правильний об'єм, нам потрібна базова інформація.",
      tech_question: "Я з радістю допоможу з вашим технічним питанням.\nНапишіть, що вам потрібно вирішити – я відразу перегляну.",
      contact: "Напишіть, що вам потрібно вирішити, або заповніть форму нижче – ми зв'яжемося з вами.\n\nАбо зверніться до нас за адресою\n📧 **obchod@ceskanadrz.cz**\n📞 **737 234 461**"
    }
  };

  const FLOW_PLACEHOLDERS = {
    cs: {
      help_choose: "Co řešíte? (např. jímka, nádrž na vodu, vsaky… + základní info)",
      shipping: "Uveďte, o jaký produkt nebo objednávku se jedná a místo dodání",
      installation: "Co chcete instalovat a v jakých podmínkách? (např. typ nádrže/jímky, půda, spodní voda, pojezd…)",
      size: "Co chcete řešit (např. jímka, nádrž, vsaky…)? Přidejte počet osob / plochu střechy a způsob využití",
      tech_question: "Popište co nejpřesněji váš dotaz nebo situaci",
      contact: "Napište, co potřebujete vyřešit (produkt, doprava, termín…)"
    },
    sk: {
      help_choose: "Čo riešite? (napr. žumpa, nádrž na vodu, vsaky… + základné info)",
      shipping: "Uveďte o aký produkt alebo objednávku sa jedná a miesto dodania",
      installation: "Čo chcete inštalovať a v akých podmienkach? (napr. typ nádrže, pôda, spodná voda…)",
      size: "Čo chcete riešiť? Pridajte počet osôb / plochu strechy a spôsob využitia",
      tech_question: "Popíšte čo najpresnejšie vašu otázku alebo situáciu",
      contact: "Napíšte, čo potrebujete vyriešiť (produkt, doprava, termín…)"
    },
    en: {
      help_choose: "What are you looking for? (e.g., tank, cesspool... + basic info)",
      shipping: "Specify the product or order and the delivery location",
      installation: "What do you want to install and in what conditions?",
      size: "What do you need? Add the number of people / roof area and usage",
      tech_question: "Describe your question or situation as accurately as possible",
      contact: "Write what you need to resolve (product, shipping, date...)"
    },
    uk: {
      help_choose: "Що ви шукаєте? (наприклад, резервуар... + базова інформація)",
      shipping: "Вкажіть товар або замовлення та місце доставки",
      installation: "Що ви хочете встановити і в яких умовах?",
      size: "Що вам потрібно? Додайте кількість осіб і використання",
      tech_question: "Опишіть ваше питання якомога точніше",
      contact: "Напишіть, що вам потрібно вирішити (продукт, доставка, дата...)"
    }
  };

  const CTA_TEXTS = {
    cs: {
      generic: "Chcete, aby se vám ozval náš specialista a probral to s vámi?\nNechte mi na sebe kontakt.",
      shipping: "👉 Chcete ověřit termín doručení nebo stav objednávky? Vyplňte formulář a ozveme se vám s přesným termínem.",
      installation: "👉 Nejste si jistí instalací? Nechte nám kontakt a doporučíme vám správný postup.\n👉 Nebo mi napište do chatu a podíváme se na to spolu.",
      size: "👉 Vyplňte krátký formulář a připravíme vám přesné doporučení.\n👉 Nebo mi napište do chatu a společně to projdeme."
    },
    sk: {
      generic: "Chcete, aby sa vám ozval náš špecialista a prebral to s vami?\nNechajte mi na seba kontakt.",
      shipping: "👉 Chcete overiť termín doručenia alebo stav objednávky? Vyplňte formulár a ozveme sa vám.",
      installation: "👉 Nie ste si istí inštaláciou? Nechajte nám kontakt a odporučíme vám správny postup.\n👉 Alebo mi napíšte do chatu a pozrieme sa na to spolu.",
      size: "👉 Vyplňte krátky formulár a pripravíme vám presné odporúčanie.\n👉 Alebo mi napíšte do chatu a spoločne to prejdeme."
    },
    en: {
      generic: "Would you like our specialist to contact you and discuss this?\nLeave me your contact details.",
      shipping: "👉 Want to check delivery dates or order status? Fill out the form and we will reach out.",
      installation: "👉 Unsure about installation? Leave us your contact and we will recommend the right procedure.\n👉 Or write to me in the chat.",
      size: "👉 Fill out a short form and we will prepare an exact recommendation."
    },
    uk: {
      generic: "Бажаєте, щоб наш спеціаліст зв'язався з вами та обговорив це?\nЗалиште мені свої контактні дані.",
      shipping: "👉 Бажаєте перевірити дати доставки? Заповніть форму, і ми зв'яжемося з вами.",
      installation: "👉 Не впевнені щодо встановлення? Залиште нам контакт, і ми порекомендуємо правильну процедуру.",
      size: "👉 Заповніть коротку форму, і ми підготуємо точну рекомендацію."
    }
  };

  const panel = document.getElementById("chatPanel");
  const chatBox = document.getElementById("chat-box");
  const input = document.getElementById("message-input");
  const sendBtn = document.getElementById("sendBtn");
  
  function updateUI() {
    input.placeholder = UI_TEXT[selectedLang].placeholder;
    document.getElementById("expandLabel").textContent = UI_TEXT[selectedLang].expandLabel;
    document.getElementById("themeLabel").textContent = UI_TEXT[selectedLang].themeLabel;
    document.getElementById("langLabel").textContent = UI_TEXT[selectedLang].langLabel;
    document.getElementById("langSelect").value = selectedLang;
  }

  function setExpanded(expanded) {
    isExpanded = expanded; localStorage.setItem("eniq_expanded", expanded);
    if(expanded) { panel.classList.add('expanded'); document.getElementById("expandToggle").classList.add('active'); }
    else { panel.classList.remove('expanded'); document.getElementById("expandToggle").classList.remove('active'); }
  }

  function setTheme(dark) {
    isDark = dark; localStorage.setItem("eniq_dark", dark);
    if(dark) { panel.classList.add('dark-theme'); document.getElementById("themeToggle").classList.add('active'); }
    else { panel.classList.remove('dark-theme'); document.getElementById("themeToggle").classList.remove('active'); }
  }

  function scrollToBottom() {
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function isNearBottom(threshold = 150) {
    return chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight < threshold;
  }

  function scrollToBottomIfNear() {
    if (isNearBottom()) scrollToBottom();
  }
  
  function formatText(text) { 
    if (!text) return "";
    let formatted = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>"); 
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    formatted = formatted.replace(urlRegex, '<a href="$1" target="_blank" class="chat-link">$1</a>');
    return formatted.replace(/\n/g, '<br>');
  }

  function showQuickActionsInChat() {
    if (quickActionsShown) return;
    const actionsRow = document.createElement("div"); actionsRow.className = "quick-actions-inline";
    QUICK_ACTIONS[selectedLang].forEach(item => {
      const btn = document.createElement("button"); btn.className = "quick-action-btn"; btn.dataset.action = item.key; btn.textContent = item.label; actionsRow.appendChild(btn);
    });
    chatBox.appendChild(actionsRow); quickActionsShown = true; scrollToBottomIfNear();
    emitFrontendEvent("quick_actions_shown", {
      actions: QUICK_ACTIONS[selectedLang].map(item => item.key)
    });
  }

  function showPageLinkButtons(pageUrl, imageUrl = null) {
    const row = document.createElement("div"); row.className = "page-link-prompt";
    let imgHtml = "";
    if (imageUrl) {
        imgHtml = `<div style="text-align: center; margin-bottom: 10px; background: transparent; padding: 0; border: none;">
                      <img src="${imageUrl}" style="max-width: 100%; max-height: 160px; object-fit: contain; border-radius: 6px;">
                   </div>`;
    }
    const text = document.createElement("div"); text.className = "page-link-text"; text.textContent = UI_TEXT[selectedLang].showOnPage;
    const buttons = document.createElement("div"); buttons.className = "page-link-buttons";
    const btnYes = document.createElement("button"); btnYes.className = "page-link-btn page-link-btn-yes"; btnYes.textContent = UI_TEXT[selectedLang].btnYes; btnYes.dataset.url = pageUrl;
    const btnNo = document.createElement("button"); btnNo.className = "page-link-btn page-link-btn-no"; btnNo.textContent = UI_TEXT[selectedLang].btnNo;
    buttons.appendChild(btnYes); buttons.appendChild(btnNo); 
    if(imgHtml) row.insertAdjacentHTML('beforeend', imgHtml);
    row.appendChild(text); 
    row.appendChild(buttons);
    chatBox.appendChild(row); 
    scrollToBottomIfNear();
    emitFrontendEvent("page_link_prompt_shown", {
      page_url: pageUrl,
      has_image: Boolean(imageUrl)
    });
  }

  // Funkce vytvoří jen lákavé CTA k formuláři
  function renderContactCTA(introText, placeholderText) {
    const row = document.createElement("div"); row.className = "message bot cta-block";
    row.innerHTML = `<div class="message-content" style="background: var(--bg-card); border: 1px solid var(--border-color); color: var(--text-base);">
        <div style="margin-bottom: 10px; font-size: 14px; line-height: 1.4;">${formatText(introText)}</div>
        <button class="cta-contact-btn" style="background: #2563eb; color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;">${UI_TEXT[selectedLang].ctaBtn}</button>
    </div>`;
    chatBox.appendChild(row);
    scrollToBottomIfNear();
    emitFrontendEvent("contact_cta_shown", {
      active_flow: activeFlow || null
    });
    
    row.querySelector('.cta-contact-btn').addEventListener('click', () => {
        emitFrontendEvent("contact_cta_clicked", {
          active_flow: activeFlow || null
        });
        row.remove();
        renderContactForm(placeholderText);
    });
  }

  function renderContactForm(customPlaceholderText) {
    const row = document.createElement("div"); row.className = "contact-form-container";
    
    let cfHeaderTxt = UI_TEXT[selectedLang].ctaHeader;
    let placeholderTxt = customPlaceholderText || UI_TEXT[selectedLang].cfNote;

    row.innerHTML = `
      <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-base, #111827); font-size: 14px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">👇 ${cfHeaderTxt}</div>
      <input type="text" class="cf-input cf-fname" placeholder="${UI_TEXT[selectedLang].cfFname}">
      <input type="email" class="cf-input cf-email" placeholder="${UI_TEXT[selectedLang].cfEmail}">
      <input type="tel" class="cf-input cf-phone" placeholder="${UI_TEXT[selectedLang].cfPhone}">
      <textarea class="cf-input cf-note" placeholder="${placeholderTxt}" rows="3" style="resize:vertical;"></textarea>
      <button class="cf-submit-btn">${UI_TEXT[selectedLang].cfBtn}</button>
    `;
    chatBox.appendChild(row); 
    scrollToBottomIfNear();
    emitFrontendEvent("contact_form_shown", {
      active_flow: activeFlow || null,
      placeholder: placeholderTxt
    });
    
    // Scrolujeme měkce k formluáři – jen at je vidět hlavička, nechceme schovat zbytek diskuse
    // Odstraněno automatické scrollování podle požadavku, aby uživateli neujel text zprávy.
    // row.scrollIntoView({ behavior: 'smooth', block: 'end' });

    const emailInput = row.querySelector('.cf-email');
    const fnameInput = row.querySelector('.cf-fname');
    const phoneInput = row.querySelector('.cf-phone');
    const noteInput = row.querySelector('.cf-note');
    let passiveSent = false;
    let formInteractionLogged = false;

    const logFormInteraction = (fieldName) => {
      if (formInteractionLogged) return;
      formInteractionLogged = true;
      emitFrontendEvent("contact_form_interaction", {
        first_field: fieldName,
        active_flow: activeFlow || null
      });
    };

    [fnameInput, emailInput, phoneInput, noteInput].forEach((field) => {
      field.addEventListener('focus', () => {
        logFormInteraction(field.className || "unknown");
      });
      field.addEventListener('click', () => {
        logFormInteraction(field.className || "unknown");
      });
    });
    
    emailInput.addEventListener('blur', () => {
      const email = emailInput.value.trim();
      const fname = fnameInput.value.trim() || 'Nezadáno';
      if (!passiveSent && email.includes('@') && email.includes('.')) {
        passiveSent = true;
        const msg = `[PASIVNÍ ZÁCHYT KONTAKTU] E-mail: ${email}, Jméno: ${fname}. Toto je tiše odchycený nedokončený lead z rozkoukaného formuláře, nijak na něj neodpovídej, jen si ho ulož.`;
        fetch(`${BASE_URL}/chat`, { 
          method: "POST", headers: { "Content-Type": "application/json", "X-Nadrz-Token": "nadrz-secure-2026" }, 
          body: JSON.stringify({ message: msg, session_id: sessionId, language: selectedLang }) 
        }).catch(e => console.log('Passive track fail', e));
      }
    });

    const submitBtn = row.querySelector('.cf-submit-btn');
    submitBtn.addEventListener('click', () => {
      const fname = row.querySelector('.cf-fname').value.trim();
      const email = row.querySelector('.cf-email').value.trim();
      const phone = row.querySelector('.cf-phone').value.trim();
      const note = row.querySelector('.cf-note').value.trim();

      if (!email) { alert(UI_TEXT[selectedLang].cfErr); return; }

      let successText = UI_TEXT[selectedLang].cfSuccess.replace("{NAME}", fname || "");
      row.innerHTML = `<div class="cf-success" style="white-space: pre-wrap;">${successText}</div>`;
      
      const safeFname = fname || "Nevyplněno";
      const safePhone = phone || "Nevyplněno";
      const safeNote = note || "Žádná poznámka";
      const hiddenMessage = `[KONTAKTNÍ FORMULÁŘ] E-mail: ${email}, Jméno: ${safeFname}, Telefon: ${safePhone}, Poznámka: ${safeNote}. Zákazník právě vyplnil formulář. Poděkuj mu a řekni, že to předáváš, a zeptej se, s čím dalším mu teď můžeš pomoci.`;
      
      addMessage(`[Odeslán kontakt | E-mail: ${email}]`, "user", false);
      ingestClientMessage(
        "user",
        `[Odeslán kontakt | E-mail: ${email}]`,
        {
          channel: "contact_form",
          has_name: fname.length > 0,
          has_email: email.length > 0,
          has_phone: phone.length > 0,
          has_note: note.length > 0
        },
        "contact_submitted"
      );
      
      // Odesíláme potichu do botu
      fetch(`${BASE_URL}/chat`, { 
          method: "POST", headers: { "Content-Type": "application/json", "X-Nadrz-Token": "nadrz-secure-2026" }, 
          body: JSON.stringify({ message: hiddenMessage, session_id: sessionId, language: selectedLang }) 
      });
    });
  }

  function addMessage(text, type, showActions = false) {
    const row = document.createElement("div"); row.className = `message ${type}`;
    if (type === "bot") {
      row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div>`;
    }
    const bubble = document.createElement("div"); bubble.className = "message-content"; bubble.innerHTML = formatText(text); row.appendChild(bubble); 
    chatBox.appendChild(row);
    scrollToBottomIfNear();
    if (type === "bot" && showActions && isFirstMessage && !quickActionsShown) showQuickActionsInChat();
    return row;
  }

  async function streamText(bubble, fullText) {
    let index = 0; let currentText = "";

    while (index < fullText.length) { 
      currentText += fullText.slice(index, index + 2); 
      bubble.innerHTML = formatText(currentText); 
      index += 2; 
      await new Promise(r => setTimeout(r, 15)); 
    }
    scrollToBottomIfNear();
  }

  function showSearching() {
    const row = document.createElement("div"); row.className = "searching-row";
    row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div><div class="searching-bubble"><span class="typing-text"></span><span class="typing-cursor">|</span></div>`;
    chatBox.appendChild(row); searchingEl = row; scrollToBottomIfNear();
    const textEl = row.querySelector('.typing-text'); const text = UI_TEXT[selectedLang].searching; let index = 0;
    typingInterval = setInterval(() => {
      if (index < text.length) {
        textEl.textContent += text[index++];
      } else clearInterval(typingInterval);
    }, 80);
  }

  function hideSearching() {
    if (typingInterval) clearInterval(typingInterval);
    if (searchingEl) { searchingEl.remove(); searchingEl = null; }
  }

  document.getElementById("chatLauncher").addEventListener("click", () => {
    panel.classList.add('open'); sessionStorage.setItem("eniq_is_open", "true");
    if (chatBox.children.length === 0) { isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); }
  });

  document.getElementById("closeBtn").addEventListener("click", () => { 
    panel.classList.remove('open'); sessionStorage.setItem("eniq_is_open", "false"); document.getElementById("settingsMenu").classList.remove('active'); 
  });
  
  document.getElementById("settingsBtn").addEventListener("click", () => document.getElementById("settingsMenu").classList.toggle('active'));
  document.getElementById("expandToggle").addEventListener("click", () => setExpanded(!isExpanded));
  document.getElementById("themeToggle").addEventListener("click", () => setTheme(!isDark));
  
  document.getElementById("langSelect").addEventListener("change", (e) => { 
    selectedLang = e.target.value; localStorage.setItem("eniq_lang", selectedLang); updateUI();
    chatBox.innerHTML = ""; isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true);
  });

  chatBox.addEventListener("click", (e) => {
    const actionBtn = e.target.closest(".quick-action-btn");
    const linkBtn = e.target.closest(".page-link-btn");
    
    if (actionBtn) {
      isFirstMessage = false; 
      
      const key = actionBtn.dataset.action;
      const quickText = actionBtn.textContent.trim();
      emitFrontendEvent("message_user", {
        action_key: key,
        query_text: quickText,
        channel: "quick_action"
      });
      addMessage(quickText, "user", false);
      ingestClientMessage("user", quickText, { action_key: key, channel: "quick_action" }, "message_user");
      scrollToBottom();
      
      activeFlow = key;
      flowTurnCount = 0;

      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div>`;
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row); 
      
      const instantAnswer = INSTANT_ANSWERS[selectedLang][key];
      streamText(bubble, instantAnswer).then(() => {
        emitFrontendEvent("message_bot", {
          action_key: key,
          channel: "quick_action",
          has_product_url: false,
          show_contact_form: key === "contact" || key === "shipping" || key === "installation" || key === "size"
        });
        ingestClientMessage(
          "bot",
          instantAnswer,
          {
            action_key: key,
            channel: "quick_action",
            has_product_url: false,
            show_contact_form: key === "contact" || key === "shipping" || key === "installation" || key === "size"
          },
          "message_bot"
        );
        if (key === "shipping" || key === "installation" || key === "size") {
           renderContactCTA(CTA_TEXTS[selectedLang][key], FLOW_PLACEHOLDERS[selectedLang][key]);
        } else if (key === "contact") {
           renderContactForm(FLOW_PLACEHOLDERS[selectedLang][key]);
        }
      });
    }
    
    if (linkBtn) {
      if (linkBtn.classList.contains("page-link-btn-yes")) {
        emitFrontendEvent("page_link_clicked_yes", { page_url: linkBtn.dataset.url });
        window.open(linkBtn.dataset.url, '_blank') || (window.location.href = linkBtn.dataset.url);
      } else {
        emitFrontendEvent("page_link_clicked_no", {});
      }
      // Tlačidla necháváme navždy aktivní, nemažeme je ani nezakazujeme.
    }
  });

  async function sendDirectMessageToAPI(messageText) {
    showSearching();
    try {
      const resp = await fetch(`${BASE_URL}/chat`, { 
        method: "POST", headers: { "Content-Type": "application/json", "X-Nadrz-Token": "nadrz-secure-2026" }, 
        body: JSON.stringify({ message: messageText, session_id: sessionId, language: selectedLang }) 
      });
      const data = await resp.json(); 
      sessionId = data.session_id; localStorage.setItem("session_id", sessionId);
      hideSearching();
      
      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div>`;
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row);
      
      await streamText(bubble, data.response);
      
      flowTurnCount++;

      // Inteligentní zobrazení okna pokud chater je v toku kde má dotaz pošoupnout dál k emailu
      if ((activeFlow === "help_choose" || activeFlow === "tech_question") && flowTurnCount === 1) {
          renderContactCTA(CTA_TEXTS[selectedLang]["generic"], FLOW_PLACEHOLDERS[selectedLang][activeFlow]);
      }

      if (data.page_section) showPageLinkButtons(data.page_section, data.image_url);
      
      // Fallback: Pokud backend silně vynutí kontaktní formulář pomocí [SHOW_CONTACT_FORM] stringu
      if (data.show_contact_form && flowTurnCount !== 1) {
          // Použijeme generický placeholder, protože jsme v nespecifickém toku
          renderContactForm(UI_TEXT[selectedLang].cfNote);
      }
      
    } catch (err) {
      hideSearching(); addMessage("Omlouváme se, nastala chyba serveru.", "bot", false);
    }
  }

  async function sendMessage() {
    const userText = input.value.trim(); if (!userText) return;
    ensureSessionId();
    sendBtn.disabled = true; input.value = ""; isFirstMessage = false;
    
    addMessage(userText, "user", false); 
    scrollToBottom();
    
    await sendDirectMessageToAPI(userText);
    
    sendBtn.disabled = false; input.focus(); 
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

  updateUI(); setExpanded(isExpanded); setTheme(isDark);
  if (isChatOpen) { 
    panel.classList.add('open'); 
    if (chatBox.children.length === 0) { isFirstMessage = true; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); } 
  }
})();
