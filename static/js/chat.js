// static/js/chat.js
(function() {
  if (window.__ENIQ_WIDGET__) return;
  window.__ENIQ_WIDGET__ = 1;

  const BASE_URL = 'https://nadrz.eniq.eu';
  const WIDGET_VERSION = '9.4.12';
  const assetV = `v=${WIDGET_VERSION}`;
  const WIDGET_CSS_URL = `${BASE_URL}/widget/style.css`;

  const fontLink = document.createElement('link');
  fontLink.rel = 'stylesheet';
  fontLink.href = 'https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;500;600;700;800&display=swap';
  if (document.head) document.head.appendChild(fontLink);

  const cssLink = document.createElement('link');
  cssLink.rel = 'stylesheet';
  cssLink.setAttribute('data-eniq-widget-css', '1');
  cssLink.href = WIDGET_CSS_URL;
  if (document.head) document.head.appendChild(cssLink);

  const BOT_IMG = `${BASE_URL}/static/img/logo-kapka.png?${assetV}`;

  async function syncWidgetAssetsFromServer() {
    try {
      const response = await fetch(`${BASE_URL}/widget/manifest.json`, { cache: 'no-store' });
      if (!response.ok) return;
      const manifest = await response.json();
      if (!manifest || !manifest.version) return;
      const css = document.querySelector('link[data-eniq-widget-css]');
      if (css) {
        const nextHref = `${BASE_URL}/widget/style.css?v=${manifest.version}`;
        if (!css.href.includes(manifest.version)) css.href = nextHref;
      }
    } catch (_) {}
  }

  const QA_ICONS = {
    help_choose: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    shipping: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3" width="15" height="13"/><path d="M16 8h4l3 3v5h-7V8z"/><circle cx="5.5" cy="18.5" r="2.5"/><circle cx="18.5" cy="18.5" r="2.5"/></svg>',
    installation: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
    size: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>',
    tech_question: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9z"/><path d="M9 1v3"/><path d="M15 1v3"/><path d="M9 20v3"/><path d="M15 20v3"/><path d="M20 9h3"/><path d="M20 14h3"/><path d="M1 9h3"/><path d="M1 14h3"/></svg>',
    contact: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>'
  };

  const EMOJIS = ["😊","👍","🙏","💧","🏠","📦","✅","❓","📞","📧","🔧","💡","😀","😄","🙂","👏","❤️","⭐","🚚","🛒"];

  const chatHTML = `
    <div class="eniq-launcher-wrap">
    <button id="chatLauncher" class="eniq-launcher" type="button" aria-label="Otevřít chat">
      <span class="eniq-launcher-face">
        <span class="eniq-launcher-avatar">
          <img src="${BOT_IMG}" alt="Česká nádrž" class="bot-img">
        </span>
        <span class="launcher-online" aria-hidden="true"></span>
      </span>
      <span id="eniqBadge" class="eniq-badge">1</span>
    </button>
    </div>

    <div id="invitePopup" class="invite-popup" role="dialog" aria-label="Pozvánka k chatu">
      <button id="inviteClose" class="invite-close" type="button" aria-label="Zavřít pozvánku">
        <span class="invite-close-face">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </span>
      </button>
      <div class="invite-head">
        <div class="invite-avatar">
          <span class="invite-avatar-face">
            <img src="${BOT_IMG}" alt="Česká nádrž" class="bot-img">
            <span class="launcher-online" aria-hidden="true"></span>
          </span>
        </div>
        <div class="invite-meta">
          <div class="invite-name" id="inviteName">Virtuální asistent</div>
          <div class="invite-status"><span class="status-dot"></span> <span id="inviteOnline">Online</span></div>
        </div>
      </div>
      <div class="invite-text" id="inviteText">Dobrý den! Potřebujete poradit s výběrem nádrže, jímky nebo septiku? Rád pomohu.</div>
      <button id="inviteCta" class="invite-cta" type="button">
        <span class="invite-cta-face">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
          </svg>
          <span id="inviteCtaLabel">Začít konverzaci</span>
        </span>
      </button>
    </div>

    <div class="eniq-panel" id="chatPanel" aria-label="Chat panel" role="dialog">
      <div class="chat-header">
        <div class="chat-header-left">
          <div class="chat-header-avatar">
            <span class="chat-header-avatar-face">
              <img src="${BOT_IMG}" alt="Česká nádrž" class="bot-img">
            </span>
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
        <button class="close-btn" id="closeBtn" type="button" aria-label="Zavřít">×</button>
      </div>

      <div class="settings-menu" id="settingsMenu">
        <div class="settings-item desktop-only-setting">
          <div class="settings-label" id="expandLabel">Rozšířit chat</div>
          <div class="toggle-container"><div id="expandToggle" class="toggle-switch"><div class="toggle-slider"></div></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-label" id="themeLabel">Tmavý režim</div>
          <div class="toggle-container"><div id="themeToggle" class="toggle-switch"><div class="toggle-slider"></div></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-label" id="animLabel">Animace a efekty</div>
          <div class="toggle-container"><div id="animToggle" class="toggle-switch active"><div class="toggle-slider"></div></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-label" id="soundLabel">Zvuk zpráv</div>
          <div class="toggle-container"><div id="soundToggle" class="toggle-switch active"><div class="toggle-slider"></div></div></div>
        </div>
        <div class="settings-item">
          <div class="settings-label" id="fontLabel">Velikost písma</div>
          <select id="fontSelect" class="lang-select">
            <option value="sm">Malé</option>
            <option value="md" selected>Střední</option>
            <option value="lg">Velké</option>
          </select>
        </div>
        <div class="settings-item">
          <div class="settings-label" id="langLabel">Jazyk</div>
          <select class="lang-select" id="langSelect">
            <option value="cs">Čeština</option>
            <option value="sk">Slovenčina</option>
            <option value="en">English</option>
            <option value="uk">Українська</option>
          </select>
        </div>
        <button id="clearChatBtn" class="settings-action" type="button">Resetovat konverzaci</button>
        <div class="chat-disclaimer">
          <span id="disclaimerText">Asistent může dělat chyby. Důležité informace si ověřte.</span>
          <button id="consentLink" class="consent-link" type="button">Zpracování osobních údajů</button>
          <div id="consentBox" class="consent-box"></div>
        </div>
      </div>

      <div id="chat-box" class="chat-box"></div>

      <div id="attachPreview" class="attach-preview"></div>
      <div id="emojiPanel" class="emoji-panel"></div>

      <div class="input-area">
        <div class="composer-row">
          <textarea id="message-input" class="composer-input" rows="1" placeholder="Napište zprávu…" autocomplete="off"></textarea>
          <button class="send-btn is-empty" id="sendBtn" type="button" aria-label="Odeslat">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </div>
        <div class="composer-actions">
          <button id="attachBtn" class="composer-btn" type="button" aria-label="Přiložit soubor" title="Přiložit soubor">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
          </button>
          <button id="emojiBtn" class="composer-btn" type="button" aria-label="Emoji" title="Emoji">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M8 14s1.5 2 4 2 4-2 4-2"></path><line x1="9" y1="9" x2="9.01" y2="9"></line><line x1="15" y1="9" x2="15.01" y2="9"></line></svg>
          </button>
        </div>
        <input type="file" id="fileInput" multiple hidden />
      </div>

      <div class="powered-by">Powered by <a href="https://eniq.eu/" target="_blank" rel="noopener">Eniq</a></div>
    </div>
  `;

  function bootWidget() {
  if (window.__ENIQ_WIDGET_BOOTED__) return;
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
  let contactCtaShownForFlow = null;
  let isRequestInFlight = false;
  let inviteTimer = null;
  const INVITE_DELAY_MS = 10000;
  let soundEnabled = localStorage.getItem("eniq_sound") !== "off";
  let animEnabled = localStorage.getItem("eniq_anim") !== "off";
  let fontSize = localStorage.getItem("eniq_font") || "md";

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
    cs: { placeholder: "Napište zprávu…", welcome: "Dobrý den! Jsem asistent e-shopu Česká nádrž. S čím vám mohu pomoci?", searching: "Odepisuji...", expandLabel: "Rozšířit chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našel jsem vhodný odkaz. Chcete se na něj podívat?", btnYes: "Ano, přejít", btnNo: "Ne, díky", redirecting: "Přesměrovávám...", cfFname: "Jméno a Příjmení", cfEmail: "E-mail", cfPhone: "Telefonní číslo", cfNote: "Poznámka", cfBtn: "Odeslat poptávku", cfSuccess: "Děkujeme, {NAME}😊 Vaši zprávu jsme přijali – ozve se vám náš specialista s konkrétním řešením. Mezitím mi klidně napište podrobnosti – můžeme to rovnou doladit.", cfErr: "Vyplňte prosím e-mail.", ctaBtn: "Zanechat kontakt", ctaHeader: "Zanechte nám svůj kontakt:", inviteText: "Dobrý den! Potřebujete poradit s výběrem nádrže, jímky nebo septiku? Rád pomohu.", inviteCta: "Začít konverzaci", inviteOnline: "Online" },
    sk: { placeholder: "Napíšte správu…", welcome: "Dobrý deň! Som asistent e-shopu Česká nádrž. S čím vám môžem pomôcť?", searching: "Odpisujem...", expandLabel: "Rozšíriť chat", themeLabel: "Tmavý režim", langLabel: "Jazyk", showOnPage: "Našiel som vhodný odkaz. Chcete si ho pozrieť?", btnYes: "Áno, prejsť", btnNo: "Nie, vďaka", redirecting: "Presmerovávam...", cfFname: "Meno a Priezvisko", cfEmail: "E-mail", cfPhone: "Telefónne číslo", cfNote: "Poznámka", cfBtn: "Odoslať dopyt", cfSuccess: "Ďakujeme, {NAME}😊 Vašu správu sme prijali – ozve sa vám náš špecialista s konkrétnym riešením. Medzitým mi pokojne napíšte podrobnosti – môžeme to rovno doladiť.", cfErr: "Vyplňte prosím e-mail.", ctaBtn: "Zanechať kontakt", ctaHeader: "Zanechajte nám svoj kontakt:", inviteText: "Dobrý deň! Potrebujete poradiť s výberom nádrže, žumpy alebo septiku? Rád pomôžem.", inviteCta: "Začať konverzáciu", inviteOnline: "Online" },
    en: { placeholder: "Type a message…", welcome: "Hello! I'm the Česká nádrž assistant. How can I help you?", searching: "Typing...", expandLabel: "Expand chat", themeLabel: "Dark mode", langLabel: "Language", showOnPage: "I found a relevant link. Would you like to see it?", btnYes: "Yes, open", btnNo: "No, thanks", redirecting: "Redirecting...", cfFname: "Full Name", cfEmail: "E-mail", cfPhone: "Phone number", cfNote: "Note", cfBtn: "Send request", cfSuccess: "Thank you, {NAME}😊 We have received your message – our specialist will contact you with a solution. In the meantime, feel free to write me the details – we can fine-tune it.", cfErr: "Please fill out your email.", ctaBtn: "Leave contact", ctaHeader: "Leave us your contact details:", inviteText: "Hello! Need help choosing a tank, cesspool or septic system? I'm here to help.", inviteCta: "Start conversation", inviteOnline: "Online" },
    uk: { placeholder: "Напишіть повідомлення…", welcome: "Добрий день! Я асистент інтернет-магазину Česká nádrž. Чим можу допомогти?", searching: "Відповідаю...", expandLabel: "Розгорнути чат", themeLabel: "Темний режим", langLabel: "Мова", showOnPage: "Я знайшов відповідне посилання. Бажаєте подивитися?", btnYes: "Так, перейти", btnNo: "Ні, дякую", redirecting: "Перенаправлення...", cfFname: "Повне ім'я", cfEmail: "E-mail", cfPhone: "Номер телефону", cfNote: "Примітка", cfBtn: "Надіслати запит", cfSuccess: "Дякуємо, {NAME}😊 Ми отримали ваше повідомлення – наш спеціаліст зв'яжеться з вами. Тим часом, ви можете написати мені деталі – ми можемо все узгодити.", cfErr: "Будь ласка, введіть e-mail.", ctaBtn: "Залишити контакт", ctaHeader: "Залиште нам свої контактні дані:", inviteText: "Доброго дня! Потрібна порада щодо резервуара, вигрібної ями чи септика? Допоможу.", inviteCta: "Почати розмову", inviteOnline: "Онлайн" }
  };

  const EXTRA_TEXT = {
    cs: { disclaimer: "Asistent může dělat chyby. Důležité informace si ověřte.", consentLink: "Zpracování osobních údajů", consentFull: "Vaše zprávy zpracovává provozovatel e-shopu Česká nádrž jako správce údajů. Údaje slouží pouze k vyřízení vašeho dotazu.", animLabel: "Animace a efekty", soundLabel: "Zvuk zpráv", fontLabel: "Velikost písma", clearLabel: "Resetovat konverzaci" },
    sk: { disclaimer: "Asistent môže robiť chyby. Dôležité informácie si overte.", consentLink: "Spracovanie osobných údajov", consentFull: "Vaše správy spracúva prevádzkovateľ e-shopu Česká nádrž ako správca údajov.", animLabel: "Animácie a efekty", soundLabel: "Zvuk správ", fontLabel: "Veľkosť písma", clearLabel: "Resetovať konverzáciu" },
    en: { disclaimer: "The assistant may make mistakes. Please verify important information.", consentLink: "Personal data processing", consentFull: "Your messages are processed by Česká nádrž e-shop as the data controller.", animLabel: "Animations & effects", soundLabel: "Message sounds", fontLabel: "Font size", clearLabel: "Reset conversation" },
    uk: { disclaimer: "Асистент може помилятися. Перевіряйте важливу інформацію.", consentLink: "Обробка персональних даних", consentFull: "Ваші повідомлення обробляє інтернет-магазин Česká nádrž як розпорядник даних.", animLabel: "Анімації та ефекти", soundLabel: "Звук повідомлень", fontLabel: "Розмір шрифту", clearLabel: "Скинути розмову" }
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

  const CONTACT_INTENTS = [
    "chci zanechat kontakt",
    "zanechat kontakt",
    "chci vyplnit kontakt",
    "vyplnit kontakt",
    "kontaktní formulář",
    "kontaktny formular",
    "chcem zanechať kontakt",
    "zanechať kontakt",
    "chcem zanechat kontakt",
    "zanechat kontakt",
    "leave contact"
  ];

  const panel = document.getElementById("chatPanel");
  const launcher = document.getElementById("chatLauncher");
  const chatBox = document.getElementById("chat-box");
  const input = document.getElementById("message-input");
  const sendBtn = document.getElementById("sendBtn");
  const invitePopup = document.getElementById("invitePopup");
  const badge = document.getElementById("eniqBadge");
  const emojiPanel = document.getElementById("emojiPanel");
  const emojiBtn = document.getElementById("emojiBtn");
  const settingsMenu = document.getElementById("settingsMenu");
  const attachBtn = document.getElementById("attachBtn");
  const fileInput = document.getElementById("fileInput");
  const animToggle = document.getElementById("animToggle");
  const soundToggle = document.getElementById("soundToggle");
  const fontSelect = document.getElementById("fontSelect");
  const consentBox = document.getElementById("consentBox");

  if (!panel || !launcher || !chatBox || !input || !sendBtn) {
    console.error("[Eniq widget] Chybí DOM elementy widgetu.");
    return;
  }
  function updateUI() {
    input.placeholder = UI_TEXT[selectedLang].placeholder;
    document.getElementById("expandLabel").textContent = UI_TEXT[selectedLang].expandLabel;
    document.getElementById("themeLabel").textContent = UI_TEXT[selectedLang].themeLabel;
    document.getElementById("langLabel").textContent = UI_TEXT[selectedLang].langLabel;
    document.getElementById("langSelect").value = selectedLang;
    const inviteText = document.getElementById("inviteText");
    const inviteCtaLabel = document.getElementById("inviteCtaLabel");
    const inviteOnline = document.getElementById("inviteOnline");
    if (inviteText) inviteText.textContent = UI_TEXT[selectedLang].inviteText;
    if (inviteCtaLabel) inviteCtaLabel.textContent = UI_TEXT[selectedLang].inviteCta;
    if (inviteOnline) inviteOnline.textContent = UI_TEXT[selectedLang].inviteOnline;
    const extra = EXTRA_TEXT[selectedLang] || EXTRA_TEXT.cs;
    const animLabel = document.getElementById("animLabel");
    const soundLabel = document.getElementById("soundLabel");
    const fontLabel = document.getElementById("fontLabel");
    const clearChatBtn = document.getElementById("clearChatBtn");
    if (animLabel) animLabel.textContent = extra.animLabel;
    if (soundLabel) soundLabel.textContent = extra.soundLabel;
    if (fontLabel) fontLabel.textContent = extra.fontLabel;
    if (clearChatBtn) clearChatBtn.textContent = extra.clearLabel;
    fillConsentTexts();
  }

  function fillConsentTexts() {
    const extra = EXTRA_TEXT[selectedLang] || EXTRA_TEXT.cs;
    const disclaimer = document.getElementById("disclaimerText");
    const consentLink = document.getElementById("consentLink");
    if (disclaimer) disclaimer.textContent = extra.disclaimer;
    if (consentLink) consentLink.textContent = extra.consentLink;
    if (consentBox) consentBox.textContent = extra.consentFull;
  }

  function setSound(on) {
    soundEnabled = on;
    localStorage.setItem("eniq_sound", on ? "on" : "off");
    if (soundToggle) soundToggle.classList.toggle("active", on);
  }

  function setAnim(on) {
    animEnabled = on;
    localStorage.setItem("eniq_anim", on ? "on" : "off");
    if (panel) panel.classList.toggle("no-anim", !on);
    if (animToggle) animToggle.classList.toggle("active", on);
  }

  function setFontSize(size) {
    fontSize = size;
    localStorage.setItem("eniq_font", size);
    if (panel) {
      panel.classList.remove("fs-sm", "fs-md", "fs-lg");
      panel.classList.add("fs-" + size);
    }
    if (fontSelect) fontSelect.value = size;
  }

  function clearConversation() {
    chatBox.innerHTML = "";
    isFirstMessage = true;
    quickActionsShown = false;
    if (input) input.value = "";
    autoGrowInput();
    updateSendState();
    if (emojiPanel) emojiPanel.classList.remove("open");
    if (settingsMenu) settingsMenu.classList.remove("active");
    addMessage(UI_TEXT[selectedLang].welcome, "bot", true);
  }

  function autoGrowInput() {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  function updateSendState() {
    if (!sendBtn || !input) return;
    sendBtn.classList.toggle("is-empty", !input.value.trim());
  }

  function buildEmojiPanel() {
    if (!emojiPanel) return;
    emojiPanel.innerHTML = "";
    EMOJIS.forEach((em) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "emoji-item";
      btn.dataset.emoji = em;
      btn.textContent = em;
      btn.addEventListener("click", () => {
        input.value += em;
        autoGrowInput();
        updateSendState();
        input.focus();
      });
      emojiPanel.appendChild(btn);
    });
  }

  function setExpanded(expanded) {
    isExpanded = expanded; localStorage.setItem("eniq_expanded", expanded);
    if(expanded) { panel.classList.add('expanded'); document.getElementById("expandToggle").classList.add('active'); }
    else { panel.classList.remove('expanded'); document.getElementById("expandToggle").classList.remove('active'); }
  }

  function setTheme(dark) {
    isDark = dark; localStorage.setItem("eniq_dark", dark);
    if(dark) {
      panel.classList.add('dark-mode');
      document.getElementById("themeToggle").classList.add('active');
      if (invitePopup) invitePopup.classList.add('invite-dark');
    } else {
      panel.classList.remove('dark-mode');
      document.getElementById("themeToggle").classList.remove('active');
      if (invitePopup) invitePopup.classList.remove('invite-dark');
    }
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

  function scrollMessageToTop(messageRow) {
    if (!messageRow) return;
    const chatRect = chatBox.getBoundingClientRect();
    const rowRect = messageRow.getBoundingClientRect();
    const topPadding = 8;
    chatBox.scrollTo({
      top: chatBox.scrollTop + rowRect.top - chatRect.top - topPadding,
      behavior: "smooth"
    });
  }

  function dismissBadge() {
    sessionStorage.setItem("eniq_badge_dismissed", "1");
    if (badge) badge.classList.remove("show");
  }

  function closeInvite(keepBadge) {
    if (inviteTimer) clearTimeout(inviteTimer);
    inviteTimer = null;
    if (invitePopup) invitePopup.classList.remove("open");
    if (!keepBadge) dismissBadge();
  }

  function showBadge() {
    if (sessionStorage.getItem("eniq_badge_dismissed") === "1") return;
    if (badge) badge.classList.add("show");
  }

  function markChatEngaged() {
    sessionStorage.setItem("eniq_chat_engaged", "1");
    dismissBadge();
  }

  function nudgeLauncher() {
    if (!launcher) return;
    const wrap = launcher.closest(".eniq-launcher-wrap");
    [launcher, wrap].filter(Boolean).forEach((el) => {
      el.classList.remove("nudge");
      void el.offsetWidth;
      el.classList.add("nudge");
    });
    setTimeout(() => {
      launcher.classList.remove("nudge");
      if (wrap) wrap.classList.remove("nudge");
    }, 700);
  }

  function showInvite() {
    if (!invitePopup || panel.classList.contains("open")) return;
    if (sessionStorage.getItem("eniq_invite_seen") === "1") return;
    sessionStorage.setItem("eniq_invite_seen", "1");
    invitePopup.classList.add("open");
    showBadge();
    nudgeLauncher();
  }

  function scheduleInvite() {
    closeInvite(true);
    if (panel.classList.contains("open")) return;
    if (sessionStorage.getItem("eniq_badge_dismissed") === "1") return;
    if (sessionStorage.getItem("eniq_invite_seen") === "1") {
      showBadge();
      return;
    }
    inviteTimer = setTimeout(showInvite, INVITE_DELAY_MS);
  }

  function normalizeIntentText(text) {
    return text
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function isContactIntent(text) {
    const normalizedText = normalizeIntentText(text);
    return CONTACT_INTENTS.some(intent => normalizedText === normalizeIntentText(intent));
  }
  
  function formatText(text) { 
    if (!text) return "";
    let formatted = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>"); 
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    formatted = formatted.replace(urlRegex, '<a href="$1" target="_blank" class="chat-link">$1</a>');
    return formatted.replace(/\n/g, '<br>');
  }

  function showQuickActionsInChat(bubbleCol) {
    if (quickActionsShown || !bubbleCol) return;
    const actionsRow = document.createElement("div"); actionsRow.className = "quick-actions-inline";
    QUICK_ACTIONS[selectedLang].forEach(item => {
      const btn = document.createElement("button");
      btn.className = "quick-action-btn";
      btn.dataset.action = item.key;
      const icon = QA_ICONS[item.key] || "";
      btn.innerHTML = `<span class="qa-icon">${icon}</span><span class="qa-label">${item.label}</span>`;
      actionsRow.appendChild(btn);
    });
    bubbleCol.appendChild(actionsRow); quickActionsShown = true; scrollToBottomIfNear();
    emitFrontendEvent("quick_actions_shown", {
      actions: QUICK_ACTIONS[selectedLang].map(item => item.key)
    });
  }

  function showPageLinkButtons(pageUrl, imageUrl = null) {
    const row = document.createElement("div"); row.className = "page-link-prompt";

    if (imageUrl) {
      const headerWrapper = document.createElement("div");
      headerWrapper.className = "page-link-header-wrapper";
      const imgEl = document.createElement("img");
      imgEl.src = imageUrl;
      imgEl.className = "page-link-product-img";
      imgEl.alt = "";
      headerWrapper.appendChild(imgEl);
      row.appendChild(headerWrapper);
    }

    const text = document.createElement("div"); text.className = "page-link-text"; text.textContent = UI_TEXT[selectedLang].showOnPage;
    const buttons = document.createElement("div"); buttons.className = "page-link-buttons";
    const btnYes = document.createElement("button"); btnYes.className = "page-link-btn page-link-btn-yes"; btnYes.textContent = UI_TEXT[selectedLang].btnYes; btnYes.dataset.url = pageUrl;
    const btnNo = document.createElement("button"); btnNo.className = "page-link-btn page-link-btn-no"; btnNo.textContent = UI_TEXT[selectedLang].btnNo;
    buttons.appendChild(btnYes); buttons.appendChild(btnNo);
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
    contactCtaShownForFlow = activeFlow || "__generic__";
    const row = document.createElement("div"); row.className = "message bot cta-block";
    row.innerHTML = `<div class="message-avatar"><img src="${BOT_IMG}" alt="Bot" class="bot-img" onerror="this.style.display='none'"></div>
        <div class="bubble-col"><div class="message-content">
        <div style="margin-bottom: 10px; font-size: 14px; line-height: 1.4;">${formatText(introText)}</div>
        <button class="cta-contact-btn" type="button">${UI_TEXT[selectedLang].ctaBtn}</button>
    </div></div>`;
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
    return row;
  }

  function renderContactForm(customPlaceholderText, shouldAutoScroll = true) {
    const row = document.createElement("div"); row.className = "contact-form-container";
    
    let cfHeaderTxt = UI_TEXT[selectedLang].ctaHeader;
    let placeholderTxt = customPlaceholderText || UI_TEXT[selectedLang].cfNote;

    row.innerHTML = `
      <div class="cf-header">👇 ${cfHeaderTxt}</div>
      <input type="text" class="cf-input cf-fname" placeholder="${UI_TEXT[selectedLang].cfFname}">
      <input type="email" class="cf-input cf-email" placeholder="${UI_TEXT[selectedLang].cfEmail}">
      <input type="tel" class="cf-input cf-phone" placeholder="${UI_TEXT[selectedLang].cfPhone}">
      <textarea class="cf-input cf-note" placeholder="${placeholderTxt}" rows="3" style="resize:vertical;"></textarea>
      <button type="button" class="cf-submit-btn">${UI_TEXT[selectedLang].cfBtn}</button>
    `;
    chatBox.appendChild(row);
    if (shouldAutoScroll) {
      scrollToBottom();
      setTimeout(() => {
        row.scrollIntoView({ behavior: "smooth", block: "end" });
      }, 50);
    }
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
        const msg = `[PASIVNÍ ZÁCHYT KONTAKTU] E-mail: ${email}, Jméno: ${fname}.`;
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
      const hiddenMessage = `[KONTAKTNÍ FORMULÁŘ] E-mail: ${email}, Jméno: ${safeFname}, Telefon: ${safePhone}, Poznámka: ${safeNote}.`;
      
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
    return row;
  }

  function addMessage(text, type, showActions = false) {
    const row = document.createElement("div"); row.className = `message ${type}`;
    if (type === "bot") {
      row.innerHTML = `<div class="message-avatar"><img src="${BOT_IMG}" alt="Bot" class="bot-img" onerror="this.style.display='none'"></div>`;
    }
    const bubbleCol = document.createElement("div");
    bubbleCol.className = "bubble-col";
    const bubble = document.createElement("div"); bubble.className = "message-content"; bubble.innerHTML = formatText(text);
    bubbleCol.appendChild(bubble);
    row.appendChild(bubbleCol);
    chatBox.appendChild(row);
    scrollToBottomIfNear();
    if (type === "bot" && showActions && isFirstMessage && !quickActionsShown) showQuickActionsInChat(bubbleCol);
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
    const row = document.createElement("div"); row.className = "message bot searching-row";
    row.innerHTML = `<div class="message-avatar"><img src="${BOT_IMG}" alt="Bot" class="bot-img" onerror="this.style.display='none'"></div><div class="message-content typing-indicator"><span></span><span></span><span></span></div>`;
    chatBox.appendChild(row); searchingEl = row; scrollToBottomIfNear();
  }

  function hideSearching() {
    if (typingInterval) clearInterval(typingInterval);
    if (searchingEl) { searchingEl.remove(); searchingEl = null; }
  }

  launcher.addEventListener("click", () => {
    syncWidgetAssetsFromServer();
    markChatEngaged();
    closeInvite();
    panel.classList.add('open'); sessionStorage.setItem("eniq_is_open", "true");
    if (chatBox.children.length === 0) { isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); }
  });

  document.getElementById("inviteCta").addEventListener("click", () => {
    markChatEngaged();
    closeInvite();
    panel.classList.add('open'); sessionStorage.setItem("eniq_is_open", "true");
    if (chatBox.children.length === 0) { isFirstMessage = true; quickActionsShown = false; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); }
  });

  document.getElementById("inviteClose").addEventListener("click", () => closeInvite(true));

  document.getElementById("closeBtn").addEventListener("click", () => { 
    panel.classList.remove('open'); sessionStorage.setItem("eniq_is_open", "false"); document.getElementById("settingsMenu").classList.remove('active');
    if (emojiPanel) emojiPanel.classList.remove('open');
    if (sessionStorage.getItem("eniq_chat_engaged") === "1") dismissBadge();
    scheduleInvite();
  });
  
  document.getElementById("settingsBtn").addEventListener("click", () => document.getElementById("settingsMenu").classList.toggle('active'));
  document.getElementById("expandToggle").addEventListener("click", () => setExpanded(!isExpanded));
  document.getElementById("themeToggle").addEventListener("click", () => setTheme(!isDark));
  if (emojiBtn) {
    emojiBtn.addEventListener("click", () => {
      if (emojiPanel) emojiPanel.classList.toggle('open');
    });
  }
  if (attachBtn && fileInput) {
    attachBtn.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => { fileInput.value = ""; });
  }
  if (animToggle) animToggle.addEventListener("click", () => setAnim(!animEnabled));
  if (soundToggle) soundToggle.addEventListener("click", () => setSound(!soundEnabled));
  if (fontSelect) fontSelect.addEventListener("change", (e) => setFontSize(e.target.value));
  const clearChatBtn = document.getElementById("clearChatBtn");
  if (clearChatBtn) clearChatBtn.addEventListener("click", clearConversation);
  const consentLink = document.getElementById("consentLink");
  if (consentLink) consentLink.addEventListener("click", () => { if (consentBox) consentBox.classList.toggle("open"); });
  
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
      const quickText = (actionBtn.querySelector(".qa-label") || actionBtn).textContent.trim();
      emitFrontendEvent("message_user", {
        action_key: key,
        query_text: quickText,
        channel: "quick_action"
      });
      const userMessageRow = addMessage(quickText, "user", false);
      ingestClientMessage("user", quickText, { action_key: key, channel: "quick_action" }, "message_user");
      scrollToBottom();
      
      activeFlow = key;
      flowTurnCount = 0;
      contactCtaShownForFlow = null;

      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><img src="${BOT_IMG}" alt="Bot" class="bot-img" onerror="this.style.display='none'"></div>`;
      const bubbleCol = document.createElement("div"); bubbleCol.className = "bubble-col";
      const bubble = document.createElement("div"); bubble.className = "message-content";
      bubbleCol.appendChild(bubble); row.appendChild(bubbleCol); chatBox.appendChild(row);
      
      const instantAnswer = INSTANT_ANSWERS[selectedLang][key];
      streamText(bubble, instantAnswer).then(() => {
        emitFrontendEvent("message_bot", {
          action_key: key,
          channel: "quick_action",
          has_product_url: false,
          show_contact_form: key === "contact" || key === "shipping" || key === "installation" || key === "size" || key === "help_choose" || key === "tech_question"
        });
        ingestClientMessage(
          "bot",
          instantAnswer,
          {
            action_key: key,
            channel: "quick_action",
            has_product_url: false,
            show_contact_form: key === "contact" || key === "shipping" || key === "installation" || key === "size" || key === "help_choose" || key === "tech_question"
          },
          "message_bot"
        );
        if (key === "shipping" || key === "installation" || key === "size") {
           renderContactCTA(CTA_TEXTS[selectedLang][key], FLOW_PLACEHOLDERS[selectedLang][key]);
        } else if (key === "help_choose" || key === "tech_question") {
           renderContactCTA(CTA_TEXTS[selectedLang]["generic"], FLOW_PLACEHOLDERS[selectedLang][key]);
        } else if (key === "contact") {
           renderContactForm(FLOW_PLACEHOLDERS[selectedLang][key], false);
        }
        requestAnimationFrame(() => scrollMessageToTop(userMessageRow));
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
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 55000);
    try {
      const resp = await fetch(`${BASE_URL}/chat`, { 
        method: "POST", headers: { "Content-Type": "application/json", "X-Nadrz-Token": "nadrz-secure-2026" }, 
        body: JSON.stringify({ message: messageText, session_id: sessionId, language: selectedLang }),
        signal: controller.signal
      });
      if (!resp.ok) throw new Error(`Chat request failed: ${resp.status}`);
      const data = await resp.json(); 
      sessionId = data.session_id; localStorage.setItem("session_id", sessionId);
      hideSearching();
      
      const row = document.createElement("div"); row.className = `message bot`;
      row.innerHTML = `<div class="message-avatar"><img src="${BOT_IMG}" alt="Bot" class="bot-img" onerror="this.style.display='none'"></div>`;
      const bubbleCol = document.createElement("div"); bubbleCol.className = "bubble-col";
      const bubble = document.createElement("div"); bubble.className = "message-content";
      bubbleCol.appendChild(bubble); row.appendChild(bubbleCol); chatBox.appendChild(row);
      
      await streamText(bubble, data.response);
      
      flowTurnCount++;

      // Inteligentní zobrazení okna pokud chater je v toku kde má dotaz pošoupnout dál k emailu
      if ((activeFlow === "help_choose" || activeFlow === "tech_question") && flowTurnCount === 1 && contactCtaShownForFlow !== activeFlow) {
          renderContactCTA(CTA_TEXTS[selectedLang]["generic"], FLOW_PLACEHOLDERS[selectedLang][activeFlow]);
      }

      if (data.page_section) showPageLinkButtons(data.page_section, data.image_url);
      
      // Fallback: Pokud backend silně vynutí kontaktní formulář pomocí [SHOW_CONTACT_FORM] stringu
      if (data.show_contact_form && flowTurnCount !== 1) {
          // Použijeme generický placeholder, protože jsme v nespecifickém toku
          renderContactForm(UI_TEXT[selectedLang].cfNote);
      }
      
    } catch (err) {
      addMessage("Omlouváme se, odpověď se nepodařilo načíst. Zkuste dotaz prosím poslat znovu.", "bot", false);
    } finally {
      clearTimeout(timeoutId);
      hideSearching();
    }
  }

  async function sendMessage() {
    if (isRequestInFlight) return;
    const userText = input.value.trim(); if (!userText) return;
    ensureSessionId();
    isRequestInFlight = true;
    sendBtn.disabled = true; input.disabled = true;
    input.value = "";
    autoGrowInput();
    updateSendState();
    isFirstMessage = false;

    addMessage(userText, "user", false);
    scrollToBottom();

    if (isContactIntent(userText)) {
      renderContactForm(FLOW_PLACEHOLDERS[selectedLang][activeFlow] || UI_TEXT[selectedLang].cfNote);
      isRequestInFlight = false;
      sendBtn.disabled = false; input.disabled = false; input.focus();
      return;
    }
    
    try {
      await sendDirectMessageToAPI(userText);
    } finally {
      isRequestInFlight = false;
      sendBtn.disabled = false; input.disabled = false; input.focus();
    }
  }

  sendBtn.addEventListener("click", sendMessage);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  input.addEventListener("input", () => {
    autoGrowInput();
    updateSendState();
  });

  buildEmojiPanel();
  syncWidgetAssetsFromServer();
  setAnim(animEnabled);
  setSound(soundEnabled);
  setFontSize(fontSize);
  updateUI(); setExpanded(isExpanded); setTheme(isDark); updateSendState();
  if (isChatOpen) { 
    panel.classList.add('open'); 
    if (chatBox.children.length === 0) { isFirstMessage = true; addMessage(UI_TEXT[selectedLang].welcome, "bot", true); } 
  } else {
    scheduleInvite();
  }
  window.__ENIQ_WIDGET_BOOTED__ = true;
  }

  function mountWidget() {
    try {
      if (!document.body) return false;
      if (!document.getElementById("chatLauncher")) {
        document.body.insertAdjacentHTML("beforeend", chatHTML);
      }
      bootWidget();
      return Boolean(document.getElementById("chatLauncher"));
    } catch (err) {
      console.error("[Eniq widget] Nepodařilo se načíst launcher:", err);
      return false;
    }
  }

  if (mountWidget()) return;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountWidget, { once: true });
    return;
  }

  const waitForBody = setInterval(() => {
    if (mountWidget()) clearInterval(waitForBody);
  }, 20);
  setTimeout(() => clearInterval(waitForBody), 10000);
})();
