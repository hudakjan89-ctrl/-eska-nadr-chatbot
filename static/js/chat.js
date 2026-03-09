// static/js/chat.js
(function() {
  const BASE_URL = 'https://nadrz.eniq.eu'; 

  // 1. Vloženie fontov a CSS
  const fontLink = document.createElement('link');
  fontLink.rel = 'stylesheet';
  fontLink.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
  document.head.appendChild(fontLink);

  const cssLink = document.createElement('link');
  cssLink.rel = 'stylesheet';
  cssLink.href = `${BASE_URL}/static/css/style.css`;
  document.head.appendChild(cssLink);

  // 2. Vloženie HTML widgetu
  const chatHTML = `
    <div class="eniq-launcher" id="chatLauncher" aria-label="Otevřít chat" role="button" tabindex="0">
      <div class="eniq-launcher-avatar">
        <svg fill="#ffffff" viewBox="0 0 24 24" width="32" height="32"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg>
      </div>
    </div>

    <div class="eniq-panel" id="chatPanel" aria-label="Chat panel" role="dialog">
      <div class="chat-header">
        <div class="chat-header-left">
          <div class="chat-header-avatar">
             <svg fill="#005b9f" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg>
          </div>
          <div class="chat-header-info">
            <div class="chat-header-title">Česká nádrž AI</div>
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
                <option value="en">🇺🇸 English</option>
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

  // 3. LOGIKA A PREKLADY
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
    cs: { placeholder: "Napište zprávu…", welcome: "Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu pomoci?", searching: "Odepisuji...", expandLabel: "Rozšířit chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našel jsem vhodný odkaz. Chcete přejít na produkt/kategorii?", btnYes: "Ano, přejít", btnNo: "Ne, díky" },
    sk: { placeholder: "Napíšte správu…", welcome: "Dobrý deň! Som asistent e-shopu Česká nádrž. S čím vám môžem pomôcť?", searching: "Odpisujem...", expandLabel: "Rozšíriť chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našiel som vhodný odkaz. Chcete prejsť na produkt/kategóriu?", btnYes: "Áno, prejsť", btnNo: "Nie, vďaka" },
    en: { placeholder: "Type a message…", welcome: "Hello! I'm the Česká nádrž assistant. How can I help you?", searching: "Typing...", expandLabel: "Expand chat", themeLabel: "Dark mode", langLabel: "Language", showOnPage: "I found a matching link. Would you like to check it out?", btnYes: "Yes, open", btnNo: "No, thanks" }
  };

  const QUICK_ACTIONS = {
    cs:[ { key: "guide", label: "Pomoc s výběrem" }, { key: "shipping", label: "Doprava a platba" }, { key: "contact", label: "Kontakt" } ],
    sk:[ { key: "guide", label: "Pomoc s výberom" }, { key: "shipping", label: "Doprava a platba" }, { key: "contact", label: "Kontakt" } ],
    en:[ { key: "guide", label: "Help me choose" }, { key: "shipping", label: "Shipping & Payment" }, { key: "contact", label: "Contact" } ]
  };

  const INSTANT_ANSWERS = {
    cs: { guide: "Rád pomohu! Na co budete nádrž primárně potřebovat? (Dešťovka, jímka, septik?)", shipping: "Dopravu velkých nádrží máme po ČR ZDARMA! Platí se hotově u řidiče nebo převodem.", contact: "Napište na obchod@ceskanadrz.cz nebo zavolejte na 723 045 274." },
    sk: { guide: "Rád pomôžem! Na čo budete nádrž primárne potrebovať? (Dažďová voda, žumpa, septik?)", shipping: "Dopravu veľkých nádrží máme po ČR ZDARMA! Platí sa v hotovosti u vodiča alebo prevodom.", contact: "Napíšte na obchod@ceskanadrz.cz alebo zavolajte na 723 045 274." },
    en: { guide: "I'd be happy to help! What will you use the tank for primarily?", shipping: "We offer FREE shipping for large tanks within the CZ! Payment is via cash on delivery or bank transfer.", contact: "Email us at obchod@ceskanadrz.cz or call 723 045 274." }
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
    let formatted = text.replace(/\*\*/g, ""); 
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

  // Tlačidlá pre presmerovanie
  function showPageLinkButtons(pageUrl) {
    const row = document.createElement("div"); row.className = "page-link-prompt";
    const text = document.createElement("div"); text.className = "page-link-text"; text.textContent = UI_TEXT[selectedLang].showOnPage;
    const buttons = document.createElement("div"); buttons.className = "page-link-buttons";
    const btnYes = document.createElement("button"); btnYes.className = "page-link-btn page-link-btn-yes"; btnYes.textContent = UI_TEXT[selectedLang].btnYes; btnYes.dataset.url = pageUrl;
    const btnNo = document.createElement("button"); btnNo.className = "page-link-btn page-link-btn-no"; btnNo.textContent = UI_TEXT[selectedLang].btnNo;
    buttons.appendChild(btnYes); buttons.appendChild(btnNo); row.appendChild(text); row.appendChild(buttons);
    chatBox.appendChild(row); scrollToBottom();
  }

  function addMessage(text, type, showActions = false) {
    const row = document.createElement("div"); row.className = `message ${type}`;
    if (type === "bot") {
      row.innerHTML = `<div class="message-avatar"><svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg></div>`;
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
    row.innerHTML = `<div class="message-avatar"><svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg></div><div class="searching-bubble"><span class="typing-text"></span><span class="typing-cursor">|</span></div>`;
    chatBox.appendChild(row); searchingEl = row; scrollToBottom();
    const textEl = row.querySelector('.typing-text'); const text = UI_TEXT[selectedLang].searching; let index = 0;
    typingInterval = setInterval(() => { if (index < text.length) { textEl.textContent += text[index++]; scrollToBottom(); } else clearInterval(typingInterval); }, 80);
  }

  function hideSearching() {
    if (typingInterval) clearInterval(typingInterval);
    if (searchingEl) { searchingEl.remove(); searchingEl = null; }
  }

  // --- EVENT LISTENERY ---
  document.getElementById("chatLauncher").addEventListener("click", () => {
    panel.classList.add('open'); sessionStorage.setItem("eniq_is_open", "true");
    if (chatBox.children.length === 0) { isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); }
  });

  document.getElementById("closeBtn").addEventListener("click", () => { 
    panel.classList.remove('open'); sessionStorage.setItem("eniq_is_open", "false"); 
    document.getElementById("settingsMenu").classList.remove('active'); 
  });
  
  document.getElementById("settingsBtn").addEventListener("click", () => document.getElementById("settingsMenu").classList.toggle('active'));
  document.getElementById("expandToggle").addEventListener("click", () => setExpanded(!isExpanded));
  document.getElementById("themeToggle").addEventListener("click", () => setTheme(!isDark));
  
  document.getElementById("langSelect").addEventListener("change", (e) => { 
    selectedLang = e.target.value; localStorage.setItem("eniq_lang", selectedLang); updateUI();
    chatBox.innerHTML = ""; isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true);
  });

  // Reakcia na kliknutie do chatu (Rýchle akcie alebo Odkazy URL)
  chatBox.addEventListener("click", (e) => {
    const actionBtn = e.target.closest(".quick-action-btn");
    const linkBtn = e.target.closest(".page-link-btn");
    
    // Kliknutie na predvolené tlačidlo (Doprava, Kontakt...)
    if (actionBtn) {
      isFirstMessage = false; addMessage(actionBtn.textContent.trim(), "user", false);
      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg></div>`;
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row); scrollToBottom();
      streamText(bubble, INSTANT_ANSWERS[selectedLang][actionBtn.dataset.action]);
    }
    
    // Kliknutie na Presmerovanie (Áno/Nie)
    if (linkBtn) {
      if (linkBtn.classList.contains("page-link-btn-yes")) { 
          // Otvorí produkt na novej karte, taktiež pre istotu v aktuálnom ak by blokoval popup
          window.open(linkBtn.dataset.url, '_blank') || (window.location.href = linkBtn.dataset.url);
      }
      linkBtn.closest(".page-link-prompt").remove(); // Skryje ponuku po kliknutí
    }
  });

  async function sendMessage() {
    const userText = input.value.trim(); if (!userText) return;
    sendBtn.disabled = true; input.value = ""; isFirstMessage = false;
    
    addMessage(userText, "user", false); 
    showSearching();
    
    try {
      const resp = await fetch(`${BASE_URL}/chat`, { 
        method: "POST", headers: { "Content-Type": "application/json" }, 
        body: JSON.stringify({ message: userText, session_id: sessionId, language: selectedLang }) 
      });
      const data = await resp.json(); 
      sessionId = data.session_id; localStorage.setItem("session_id", sessionId);
      hideSearching();
      
      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg></div>`;
      const bubble = document.createElement("div"); bubble.className = "message-content"; row.appendChild(bubble); chatBox.appendChild(row); scrollToBottom();
      
      await streamText(bubble, data.response);
      
      // Zobrazenie animovaných tlačidiel na presmerovanie na URL
      if (data.page_section) {
        showPageLinkButtons(data.page_section);
      }
    } catch (err) {
      hideSearching();
      addMessage("Omlouváme se, nastala chyba serveru.", "bot", false);
    } finally { 
      sendBtn.disabled = false; input.focus(); 
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

  // Inicializácia widgetu po načítaní
  updateUI(); setExpanded(isExpanded); setTheme(isDark);
  if (isChatOpen) { 
    panel.classList.add('open'); 
    if (chatBox.children.length === 0) { 
      isFirstMessage = true; 
      addMessage(UI_TEXT[selectedLang].welcome, "bot", true); 
    } 
  }
})();
