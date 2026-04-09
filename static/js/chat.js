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

  const UI_TEXT = {
    cs: { placeholder: "Napište zprávu…", welcome: "Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu pomoci?", searching: "Odepisuji...", expandLabel: "Rozšířit chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našel jsem vhodný odkaz. Chcete se na něj podívat?", btnYes: "Ano, přejít", btnNo: "Ne, díky", cfFname: "Jméno a Příjmení", cfEmail: "E-mail", cfPhone: "Telefonní číslo", cfNote: "Poznámka", cfBtn: "Odeslat / Submit", cfSuccess: "✔ Údaje odeslány. Děkujeme!", cfErr: "Vyplňte prosím e-mail." },
    sk: { placeholder: "Napíšte správu…", welcome: "Dobrý deň! Som asistent e-shopu Česká nádrž. S čím vám môžem pomôcť?", searching: "Odpisujem...", expandLabel: "Rozšíriť chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našiel som vhodný odkaz. Chcete si ho pozrieť?", btnYes: "Áno, prejsť", btnNo: "Nie, vďaka", cfFname: "Meno a Priezvisko", cfEmail: "E-mail", cfPhone: "Telefónne číslo", cfNote: "Poznámka", cfBtn: "Odoslať / Submit", cfSuccess: "✔ Údaje odoslané. Ďakujeme!", cfErr: "Vyplňte prosím e-mail." },
    en: { placeholder: "Type a message…", welcome: "Hello! I'm the Česká nádrž assistant. How can I help you?", searching: "Typing...", expandLabel: "Expand chat", themeLabel: "Dark mode", langLabel: "Language", showOnPage: "I found a relevant link. Would you like to see it?", btnYes: "Yes, open", btnNo: "No, thanks", cfFname: "Full Name", cfEmail: "E-mail", cfPhone: "Phone number", cfNote: "Note", cfBtn: "Submit", cfSuccess: "✔ Submitted. Thank you!", cfErr: "Please fill out your email." },
    uk: { placeholder: "Напишіть повідомлення…", welcome: "Добрий день! Я асистент інтернет-магазину Česká nádrž. Чим можу допомогти?", searching: "Відповідаю...", expandLabel: "Розгорнути чат", themeLabel: "Темний режим", langLabel: "Мова", showOnPage: "Я знайшов відповідне посилання. Бажаєте подивитися?", btnYes: "Так, перейти", btnNo: "Ні, дякую", cfFname: "Повне ім'я", cfEmail: "E-mail", cfPhone: "Номер телефону", cfNote: "Примітка", cfBtn: "Надіслати", cfSuccess: "✔ Дані надіслано. Дякуємо!", cfErr: "Будь ласка, введіть e-mail." }
  };

  const QUICK_ACTIONS = {
    cs:[ { key: "guide", label: "Pomoc s výběrem" }, { key: "question", label: "Mám dotaz" }, { key: "shipping", label: "Doprava a platba" }, { key: "contact", label: "Kontakt" } ],
    sk:[ { key: "guide", label: "Pomoc s výberom" }, { key: "question", label: "Mám dotaz" }, { key: "shipping", label: "Doprava a platba" }, { key: "contact", label: "Kontakt" } ],
    en:[ { key: "guide", label: "Help me choose" }, { key: "question", label: "I have a question" }, { key: "shipping", label: "Shipping & Payment" }, { key: "contact", label: "Contact" } ],
    uk:[ { key: "guide", label: "Допомога у виборі" }, { key: "question", label: "У мене є питання" }, { key: "shipping", label: "Доставка та оплата" }, { key: "contact", label: "Контакти" } ]
  };

  const INSTANT_ANSWERS = {
    cs: { guide: "Rád pomohu s výběrem. Co konkrétně řešíte? (např. nádrž na vodu, jímka, vsakovací systém, šachta na vrt nebo něco jiného?)", question: "Napište mi, co řešíte. Pokud bude potřeba, doptám se na pár detailů a doporučím řešení.", shipping: "Dopravu zajišťujeme po celé ČR.\n\nVelké nádrže rozvážíme vlastními vozy ZDARMA.\nPřed doručením vás kontaktujeme (cca 1–2 dny dopředu) a řidič volá ještě zhruba 30 minut před příjezdem.\nMenší zboží zasíláme kurýrní službou (např. Toptrans).\nO odeslání vás informujeme a doručení probíhá standardně následující pracovní den.\n\nPlatba je možná:\n- převodem předem\n- nebo hotově při převzetí (u řidiče / dopravce)", contact: "Napište na **obchod@ceskanadrz.cz** nebo zavolejte na **737 234 461**. Případně vyplňte Váš e-mail, jméno, telefonní číslo a poznámku a my se Vám ozveme.\n\nZanechte svůj kontakt níže:" },
    sk: { guide: "Rád pomôžem s výberom. Čo konkrétne riešite? (napr. nádrž na vodu, žumpa, vsakovací systém, šachta na vrt alebo niečo iné?)", question: "Napíšte mi, čo riešite. Ak bude potrebné, spýtam sa na zopár detailov a odporučím riešenie.", shipping: "Dopravu zabezpečujeme po celej ČR.\n\nVeľké nádrže rozvážame vlastnými vozidlami ZADARMO.\nPred doručením vás kontaktujeme (cca 1–2 dni vopred) a vodič volá ešte zhruba 30 minút pred príchodom.\nMenší tovar zasielame kuriérskou službou (napr. Toptrans).\nO odoslaní vás informujeme a doručenie prebieha štandardne nasledujúci pracovný deň.\n\nPlatba je možná:\n- prevodom vopred\n- alebo v hotovosti pri prevzatí (u vodiča / dopravcu)", contact: "Napíšte na **obchod@ceskanadrz.cz** alebo zavolajte na **737 234 461**. Prípadne vyplňte Váš e-mail, meno, telefónne číslo a poznámku a my sa Vám ozveme.\n\nZanechajte svoj kontakt nižšie:" },
    en: { guide: "I'd be happy to help you choose. What exactly are you looking for? (e.g., water tank, cesspool, infiltration system, borehole shaft or something else?)", question: "Write me what you need. If necessary, I will ask for a few details and recommend a solution.", shipping: "We offer shipping throughout the Czech Republic.\n\nLarge tanks are delivered FREE of charge by our own vehicles.\nWe will contact you before delivery (approx. 1-2 days in advance) and the driver will call you about 30 minutes before arrival.\nSmaller goods are sent by courier service (e.g. Toptrans).\nWe will inform you about the dispatch and delivery standardly takes place the next working day.\n\nPayment is possible:\n- by bank transfer in advance\n- or in cash on delivery (to the driver / courier)", contact: "Email us at **obchod@ceskanadrz.cz** or call **737 234 461**. Or fill out your email, name, phone number, and a note, and we will get back to you.\n\nLeave your contact below:" },
    uk: { guide: "З радістю допоможу з вибором. Що саме ви шукаєте? (наприклад, резервуар для води, вигрібна яма, інфільтраційна система, шахта для свердловини чи щось інше?)", question: "Напишіть, що ви шукаєте. Якщо потрібно, я запитаю кілька деталей і порекомендую рішення.", shipping: "Ми забезпечуємо доставку по всій Чехії.\n\nВеликі резервуари доставляємо БЕЗКОШТОВНО власним транспортом.\nМи зв'яжемося з вами перед доставкою (приблизно за 1-2 дні), а водій зателефонує приблизно за 30 хвилин до прибуття.\nМенші товари відправляємо кур'єрською службою (наприклад, Toptrans).\nМи повідомимо вас про відправку, а доставка зазвичай відбувається наступного робочого дня.\n\nОплата можлива:\n- банківським переказом заздалегідь\n- або готівкою при доставці (водієві / кур'єру)", contact: "Напишіть на **obchod@ceskanadrz.cz** або зателефонуйте **737 234 461**. Або введіть свій e-mail, ім'я, номер телефону та примітку, і ми зв'яжемося з вами.\n\nЗалиште свій контакт нижче:" }
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

  function scrollToBottom() { chatBox.scrollTop = chatBox.scrollHeight; }
  
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
    chatBox.appendChild(actionsRow); quickActionsShown = true; scrollToBottom();
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
    scrollToBottom();
  }

  function renderContactForm() {
    const row = document.createElement("div"); row.className = "contact-form-container";
    
    let cfHeaderTxt = "Zanechte nám svůj kontakt:";
    if (selectedLang === "sk") cfHeaderTxt = "Zanechajte nám svoj kontakt:";
    else if (selectedLang === "en") cfHeaderTxt = "Leave us your contact details:";
    else if (selectedLang === "uk") cfHeaderTxt = "Залиште нам свої контактні дані:";

    row.innerHTML = `
      <div style="font-weight: 600; margin-bottom: 12px; color: var(--text-base, #111827); font-size: 14px; border-bottom: 1px solid #e5e7eb; padding-bottom: 8px;">👇 ${cfHeaderTxt}</div>
      <input type="text" class="cf-input cf-fname" placeholder="${UI_TEXT[selectedLang].cfFname}">
      <input type="email" class="cf-input cf-email" placeholder="${UI_TEXT[selectedLang].cfEmail}">
      <input type="tel" class="cf-input cf-phone" placeholder="${UI_TEXT[selectedLang].cfPhone}">
      <textarea class="cf-input cf-note" placeholder="${UI_TEXT[selectedLang].cfNote}" rows="3" style="resize:vertical;"></textarea>
      <button class="cf-submit-btn">${UI_TEXT[selectedLang].cfBtn}</button>
    `;
    chatBox.appendChild(row); scrollToBottom();

    const emailInput = row.querySelector('.cf-email');
    const fnameInput = row.querySelector('.cf-fname');
    let passiveSent = false;
    
    // Pasivní sběr - při sjetí z pole email se zkusí potichu odeslat kontakt (pokud je tam aspon "@")
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

      row.innerHTML = `<div class="cf-success">${UI_TEXT[selectedLang].cfSuccess}</div>`;
      const safeFname = fname || "Nevyplněno";
      const safePhone = phone || "Nevyplněno";
      const safeNote = note || "Žádná poznámka";
      const hiddenMessage = `[KONTAKTNÍ FORMULÁŘ] E-mail: ${email}, Jméno: ${safeFname}, Telefon: ${safePhone}, Poznámka: ${safeNote}. Zákazník právě vyplnil formulář. Poděkuj mu a řekni, že to předáváš, a zeptej se, s čím dalším mu teď můžeš pomoci.`;
      
      addMessage(`[Odeslán kontakt | E-mail: ${email}]`, "user", false);
      sendDirectMessageToAPI(hiddenMessage);
    });
  }

  function addMessage(text, type, showActions = false) {
    const row = document.createElement("div"); row.className = `message ${type}`;
    if (type === "bot") {
      row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div>`;
    }
    const bubble = document.createElement("div"); bubble.className = "message-content"; bubble.innerHTML = formatText(text); row.appendChild(bubble); chatBox.appendChild(row);
    if (type === "bot" && showActions && isFirstMessage && !quickActionsShown) showQuickActionsInChat();
    scrollToBottom(); return row;
  }

  async function streamText(bubble, fullText) {
    let index = 0; let currentText = "";
    while (index < fullText.length) { 
      currentText += fullText.slice(index, index + 2); 
      bubble.innerHTML = formatText(currentText); 
      index += 2; scrollToBottom(); 
      await new Promise(r => setTimeout(r, 15)); 
    }
  }

  function showSearching() {
    const row = document.createElement("div"); row.className = "searching-row";
    row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div><div class="searching-bubble"><span class="typing-text"></span><span class="typing-cursor">|</span></div>`;
    chatBox.appendChild(row); searchingEl = row; scrollToBottom();
    const textEl = row.querySelector('.typing-text'); const text = UI_TEXT[selectedLang].searching; let index = 0;
    typingInterval = setInterval(() => { if (index < text.length) { textEl.textContent += text[index++]; scrollToBottom(); } else clearInterval(typingInterval); }, 80);
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
      isFirstMessage = false; addMessage(actionBtn.textContent.trim(), "user", false);
      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><img src="${BASE_URL}/static/img/bot.png" alt="Bot" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%; background: #ffffff; display: block;" onerror="this.style.display='none'"></div>`;
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row); scrollToBottom();
      streamText(bubble, INSTANT_ANSWERS[selectedLang][actionBtn.dataset.action]).then(() => {
        if (actionBtn.dataset.action === "contact" || actionBtn.dataset.action === "question") {
          renderContactForm();
        }
      });
    }
    
    if (linkBtn) {
      if (linkBtn.classList.contains("page-link-btn-yes")) { window.open(linkBtn.dataset.url, '_blank') || (window.location.href = linkBtn.dataset.url); }
      linkBtn.closest(".page-link-prompt").remove(); 
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
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row); scrollToBottom();
      
      await streamText(bubble, data.response);
      
      if (data.page_section) showPageLinkButtons(data.page_section, data.image_url);
      if (data.show_contact_form) renderContactForm();
      
    } catch (err) {
      hideSearching(); addMessage("Omlouváme se, nastala chyba serveru.", "bot", false);
    }
  }

  async function sendMessage() {
    const userText = input.value.trim(); if (!userText) return;
    sendBtn.disabled = true; input.value = ""; isFirstMessage = false;
    
    addMessage(userText, "user", false); 
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
