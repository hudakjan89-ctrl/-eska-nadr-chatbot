// static/js/chat.js
(function() {
  // Ak to bezi na rovnakej doméne, necháme prázdne. Ak na inej subdoméne, zadaj URL k tvojmu FastAPI serveru.
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
        <!-- SVG Ikona správ (ak nemáš obrázok bota, toto funguje dokonale) -->
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
            <div class="chat-header-title">Podpora Česká nádrž</div>
            <div class="chat-header-status">
              <span class="status-dot"></span>
              <span id="statusText">Jsme online</span>
            </div>
          </div>
        </div>
        <button class="close-btn" id="closeBtn" type="button" aria-label="Zavřít">×</button>
      </div>
      
      <div id="chat-box" class="chat-box"></div>
      
      <div class="input-area">
        <input id="message-input" type="text" placeholder="Napište váš dotaz…" autocomplete="off" />
        <button class="send-btn" id="sendBtn" type="button" aria-label="Odeslat">➤</button>
      </div>
      
      <div class="powered-by">
        Powered by AI
      </div>
    </div>
  `;
  document.body.insertAdjacentHTML('beforeend', chatHTML);

  let sessionId = localStorage.getItem("session_id") || null;
  let isChatOpen = sessionStorage.getItem("eniq_is_open") === "true";
  let searchingEl = null;
  let quickActionsShown = false;
  let isFirstMessage = true;
  let typingInterval = null;

  const QUICK_ACTIONS =[ 
      { key: "guide", label: "Pomoc s výběrem" }, 
      { key: "shipping", label: "Doprava a platba" },
      { key: "faq", label: "Časté dotazy" },
      { key: "contact", label: "Kontaktovat podporu" }
  ];

  const INSTANT_ANSWERS = {
      guide: "Rád vám pomohu s výběrem! Abychom vybrali tu správnou nádrž, na co ji budete primárně potřebovat? (Na dešťovou vodu, splaškovou vodu jako jímku, nebo septik?)", 
      shipping: "Dopravu velkých nádrží máme po celé ČR ZDARMA! Rozvážíme vlastními dodávkami. Pozor, skládání z auta zajišťuje zákazník, řidič vám s tím pouze pomůže. Platit lze hotově u řidiče (nemá terminál na karty) nebo převodem.",
      faq: "Nejčastěji se zákazníci ptají na to, jaký typ nádrže zvolit. Pokud máte na pozemku spodní vodu nebo jíl, potřebujete vždy 'Dvouplášťovou nádrž'. Pokud ji dáváte do místa, kde se bude jezdit autem, pak 'K obetonování'. V běžné zemině stačí 'Samonosná'. S čím mohu pomoci vám?",
      contact: "Můžete nám napsat na obchod@ceskanadrz.cz nebo zavolat na 723 045 274 (Technické dotazy - Petr Nováček). Případně mi tady můžete nechat váš e-mail a my se vám ozveme."
  };

  const launcher = document.getElementById("chatLauncher");
  const panel = document.getElementById("chatPanel");
  const chatBox = document.getElementById("chat-box");
  const input = document.getElementById("message-input");
  const sendBtn = document.getElementById("sendBtn");
  const closeBtn = document.getElementById("closeBtn");

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
    const actionsRow = document.createElement("div");
    actionsRow.className = "quick-actions-inline";
    QUICK_ACTIONS.forEach(item => {
      const btn = document.createElement("button");
      btn.className = "quick-action-btn";
      btn.dataset.action = item.key;
      btn.textContent = item.label;
      actionsRow.appendChild(btn);
    });
    chatBox.appendChild(actionsRow);
    quickActionsShown = true;
    scrollToBottom();
  }

  function addMessage(text, type, showActions = false) {
    const row = document.createElement("div");
    row.className = `message ${type}`;
    if (type === "bot") {
      const av = document.createElement("div");
      av.className = "message-avatar";
      av.innerHTML = `<svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg>`;
      row.appendChild(av);
    }
    const bubble = document.createElement("div");
    bubble.className = "message-content";
    bubble.innerHTML = formatText(text);
    row.appendChild(bubble);
    chatBox.appendChild(row);
    
    if (type === "bot" && showActions && isFirstMessage && !quickActionsShown) {
        showQuickActionsInChat();
    }
    scrollToBottom();
    return row;
  }

  function addStreamingMessage(type) {
    const row = document.createElement("div");
    row.className = `message ${type}`;
    if (type === "bot") {
      const av = document.createElement("div");
      av.className = "message-avatar";
      av.innerHTML = `<svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg>`;
      row.appendChild(av);
    }
    const bubble = document.createElement("div");
    bubble.className = "message-content";
    bubble.innerHTML = "";
    row.appendChild(bubble);
    chatBox.appendChild(row);
    scrollToBottom();
    return bubble;
  }

  async function streamText(bubble, fullText) {
    let index = 0; 
    const chunkSize = 2;
    let currentText = "";
    while (index < fullText.length) {
      currentText += fullText.slice(index, index + chunkSize);
      bubble.innerHTML = formatText(currentText); 
      index += chunkSize; 
      scrollToBottom();
      await new Promise(r => setTimeout(r, 15));
    }
  }

  function showSearching() {
    const row = document.createElement("div");
    row.className = "searching-row";
    row.innerHTML = `
      <div class="message-avatar"><svg fill="#ffffff" viewBox="0 0 24 24" width="20" height="20"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"></path></svg></div>
      <div class="searching-bubble"><span class="typing-text"></span><span class="typing-cursor">|</span></div>`;
    chatBox.appendChild(row);
    searchingEl = row; scrollToBottom();
    
    const textEl = row.querySelector('.typing-text');
    const text = "Odepisuji...";
    let index = 0;
    typingInterval = setInterval(() => {
      if (index < text.length) { textEl.textContent += text[index]; index++; scrollToBottom(); } 
      else clearInterval(typingInterval);
    }, 80);
  }

  function hideSearching() {
    if (typingInterval) clearInterval(typingInterval);
    if (searchingEl) { searchingEl.remove(); searchingEl = null; }
  }

  launcher.addEventListener("click", () => {
    panel.classList.add('open');
    sessionStorage.setItem("eniq_is_open", "true");
    if (chatBox.children.length === 0) { 
        isFirstMessage = true;
        quickActionsShown = false;
        addMessage("Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu dnes pomoci?", "bot", true); 
    }
  });

  closeBtn.addEventListener("click", () => {
    panel.classList.remove('open');
    sessionStorage.setItem("eniq_is_open", "false");
  });

  chatBox.addEventListener("click", (e) => {
    const btn = e.target.closest(".quick-action-btn");
    if (btn) {
      const key = btn.dataset.action; 
      isFirstMessage = false;
      addMessage(btn.textContent.trim(), "user", false);
      
      const bubble = addStreamingMessage("bot");
      streamText(bubble, INSTANT_ANSWERS[key]);
    }
  });

  async function sendMessage() {
    const userText = input.value.trim();
    if (!userText) return;
    
    sendBtn.disabled = true; 
    input.value = ""; 
    isFirstMessage = false;
    
    addMessage(userText, "user", false);
    showSearching();

    try {
      const resp = await fetch(`${BASE_URL}/chat`, {
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText, session_id: sessionId })
      });
      const data = await resp.json();
      sessionId = data.session_id; 
      localStorage.setItem("session_id", sessionId);
      
      hideSearching();
      
      const bubble = addStreamingMessage("bot");
      await streamText(bubble, data.response);

      if (data.page_section) {
         // Tu sa da implementovat scrollovanie na sekciu, napr. na id="doprava" na tvojom webe.
         // window.location.hash = data.page_section;
      }
      
    } catch (err) {
      hideSearching(); 
      addMessage("Omlouváme se, nastala chyba na serveru.", "bot", false);
    } finally {
      sendBtn.disabled = false; 
      input.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });
  
  if (isChatOpen) { 
    panel.classList.add('open'); 
    if (chatBox.children.length === 0) {
        isFirstMessage = true;
        addMessage("Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu dnes pomoci?", "bot", true); 
    }
  }
})();
