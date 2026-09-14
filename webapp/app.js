/* AutoVless Mini App.
 *
 * Everything here talks to the bot's own API. The only credential is the signed
 * initData Telegram hands the page on launch: it goes out in the X-Init-Data
 * header and the server verifies the HMAC, so there is no token, no session and
 * nothing worth stealing in this file.
 *
 * The app is normally served by that same server, which keeps it same-origin. If
 * it is hosted somewhere else (GitHub Pages, for instance) set window.AUTOVLESS_API
 * or pass ?api=https://host to point it back. Hosting it on Pages without that
 * pointer is a dead end, and the app says so instead of spinning.
 *
 * Three things in here are the answer to a specific bug report, and they are
 * worth finding quickly:
 *
 *   save()      Downloading a config did nothing. The old code built a Blob and
 *               clicked an <a download>, which Telegram's webview refuses
 *               outright - and on iOS refuses silently. Every file now has a real
 *               URL on the server, opened with openLink, so the OS handles it and
 *               the WireGuard app gets offered the tunnel. The Blob is still
 *               there as a last resort for a desktop browser.
 *
 *   call()      Requests had a fifteen second deadline. Applying fresh IPs or
 *               registering a WARP identity legitimately takes longer than that,
 *               so the deadline was not protecting the user from a hung server,
 *               it was cancelling their own work and reporting a timeout that had
 *               not happened. There is no client-side deadline any more. What
 *               replaces it is an escape hatch on the overlay: the spinner can
 *               always be dismissed, so a slow request can never trap the UI -
 *               which was the actual reason the deadline was introduced.
 *
 *   dock()      See the comment above it.
 */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var params = new URLSearchParams(location.search);
  var API_OVERRIDE = (params.get("api") || window.AUTOVLESS_API || "").replace(/\/+$/, "");
  var API = API_OVERRIDE || location.origin.replace(/\/+$/, "");
  var INIT = tg ? tg.initData || "" : "";

  /* A static host can serve this page but never its API. Catch that here rather
   * than letting every request fail one by one. */
  var STATIC_HOST = /(^|\.)github\.io$|(^|\.)pages\.dev$|(^|\.)netlify\.app$|(^|\.)vercel\.app$/i
    .test(location.hostname);
  var API_MISSING = STATIC_HOST && !API_OVERRIDE;

  /* How long before the overlay offers a way out. Not a request deadline: the
   * request keeps running, the user simply stops being held hostage by it. */
  var VEIL_ESCAPE = 12000;

  var TABS = ["home", "panel", "warp", "free", "more"];

  var state = { lang: "fa", theme: "dark", data: null, fmt: "sub", proto: "vless",
                platform: "android", family: "v4", warp: null, free: null, tab: "home" };

  /* --------------------------------------------------------------- i18n */
  var STR = {
    fa: {
      tagline: "تونل اختصاصی خودت",
      loading: "در حال بارگذاری…",
      working: "در حال انجام…",
      "veil.hide": "بستن این پرده",
      "home.title": "شبکه‌ی تو، همیشه تازه",
      "home.text": "آی‌پی‌های تمیز به‌صورت خودکار اسکن، تست و روی کانفیگ‌های تو اعمال می‌شوند.",
      "home.cta": "پنل توربو", "home.cta2": "کانفیگ رایگان",
      "stat.pool": "استخر آی‌پی", "stat.verified": "تاییدشده", "stat.relays": "رله", "stat.warp": "وارپ",
      "proto.title": "🔀 پروتکل‌های فعال",
      "proto.text": "یک آدرس، چند دست‌دادن متفاوت. شبکه‌ای که یکی را بشناسد، معمولاً بقیه را رد می‌کند.",
      "ai.title": "🧠 مسیر هوش مصنوعی",
      "ai.text": "جیمینای، ChatGPT و کلاد از یک آی‌پی ثابت خارج می‌شوند تا حلقه‌ی لاگین و ارور ریجن پیش نیاید.",
      "ai.relay": "رله‌ی پین‌شده",
      "link.support": "پشتیبانی", "link.channel": "کانال", "link.github": "گیت‌هاب",
      "panel.buildTitle": "ساخت پنل توربو",
      "panel.buildText": "توکن Cloudflare خودت را بده؛ ورکر، یوزر و کانفیگ‌ها روی اکانت خودت ساخته می‌شوند.",
      "panel.tokenHelp": "ساخت توکن در داشبورد کلادفلر ↗",
      "panel.build": "ساخت پنل", "panel.title": "پنل توربو", "panel.host": "هاست",
      "panel.uuid": "شناسه", "panel.count": "کانفیگ‌ها", "panel.synced": "آخرین اعمال",
      "panel.mix": "هر سه", "panel.apply": "⚡️ اعمال آی‌پی تازه", "panel.ping": "📶 پینگ",
      "panel.rebuild": "🔄 بازسازی", "panel.fragment": "🧩 فرگمنت", "panel.delete": "🗑 حذف پنل",
      "panel.noise": "🌫 فرگمنت + نویز", "panel.clashFile": "📄 فایل Clash",
      "panel.openSub": "🌐 باز کردن لینک", "panel.showQr": "🔳 کیو‌آر",
      "panel.configs": "کانفیگ‌های تک",
      "gw.title": "لینک اشتراک روی دامنه‌ی خودمان",
      "gw.text": "آدرس workers.dev در ایران رزولوو نمی‌شود، پس لینک ساب از دامنه‌ی خودمان سرو می‌شود. کانفیگ‌ها همان‌هایی هستند که بودند.",
      "warp.title": "وایرگارد / وارپ",
      "warp.text": "اکانت وارپ واقعی روی نام تو ساخته می‌شود و اندپوینت از استخر تست‌شده انتخاب می‌شود.",
      "warp.device": "دستگاه", "warp.network": "شبکه",
      "warp.v4": "همه اپراتورها (IPv4)", "warp.v6": "ایرانسل (IPv6)",
      "warp.build": "ساخت کانفیگ", "warp.endpoint": "اندپوینت", "warp.mode": "حالت",
      "warp.routes": "مسیرها",
      "warp.download": "⬇️ فایل .conf", "warp.copylink": "🔗 لینک wireguard",
      "warp.copyconf": "📋 کپی متن کانفیگ", "warp.qr": "🔳 اسکن با WireGuard",
      "warp.appleTitle": "🍏 روش درست روی آیفون و مک",
      "warp.appleText": "اپلیکیشن رسمی WireGuard فایل دارای کلیدهای مبهم‌سازی را قبول نمی‌کند، پس این کانفیگ تمیز و استاندارد است. سریع‌ترین راه: در اپ WireGuard دکمه‌ی + را بزن، «Create from QR code» را انتخاب کن و همین کیو‌آر را اسکن کن.",
      "free.title": "کانفیگ رایگان",
      "free.text": "روی سرور مشترک ربات، با موتور واقعی: هر آی‌پی قبل از تحویل هندشیک واقعی می‌دهد.",
      "free.mix": "🧩 هر دو", "free.build": "دریافت کانفیگ",
      "invite.title": "🎁 دعوت دوستان",
      "invite.text": "لینک اختصاصی‌ات را بفرست؛ با هر ورود، شمارنده بالا می‌رود.",
      "invite.done": "دعوت‌شده", "invite.goal": "سهمیه", "invite.share": "📤 ارسال به دوستان",
      "settings.title": "⚙️ تنظیمات", "settings.lang": "زبان", "settings.theme": "پوسته",
      "admin.title": "🛠 پنل مدیریت",
      "admin.refCount": "تعداد دعوت لازم برای باز شدن ربات",
      "admin.freeAdd": "سرور رایگان جدید", "admin.usePanel": "🗂 ثبت پنل خودم",
      "admin.check": "🔎 بررسی سلامت", "admin.geo": "🌍 مکان‌یابی رله‌ها",
      save: "ذخیره", add: "افزودن", copy: "کپی",
      "tab.home": "خانه", "tab.panel": "پنل", "tab.warp": "وارپ", "tab.free": "رایگان", "tab.more": "بیشتر",
      healthy: "سالم", unhealthy: "نیاز به بررسی", copied: "کپی شد ✅",
      building: "در حال ساخت…", done: "انجام شد ✅", failed: "ناموفق: ",
      saved: "فایل باز شد؛ اگر پرسید، ذخیره یا Open in را بزن",
      noPanel: "هنوز پنلی نداری", locked: "برای استفاده باید دوستانت را دعوت کنی",
      quota: "سهمیه‌ی رایگانت تمام شده", none: "چیزی پیدا نشد",
      steps: ["بررسی توکن", "زیر‌دامنه", "انتخاب آی‌پی تمیز", "آپلود ورکر", "تست سلامت"],
      confirmDelete: "پنل و ورکرش حذف شود؟",
      "err.network": "وصل شدن به API ممکن نشد",
      "err.title": "اتصال به سرور برقرار نشد",
      "err.tried": "آدرسی که امتحان شد",
      "err.hint": "مطمئن شو ربات بالاست، API روی HTTPS سرو می‌شود و WEBAPP_URL درست است.",
      "err.noapiTitle": "آدرس API تنظیم نشده",
      "err.noapiText": "این صفحه روی یک هاست استاتیک است و API آن‌جا وجود ندارد. آدرس را با پارامتر api باز کن، مثل ?api=https://app.example.com — یا کل مینی‌اپ را از همان دامنه‌ی ربات سرو کن.",
      retry: "تلاش دوباره"
    },
    en: {
      tagline: "your own tunnel",
      loading: "Loading…",
      working: "Working…",
      "veil.hide": "Dismiss this overlay",
      "home.title": "Your network, always fresh",
      "home.text": "Clean IPs are scanned, tested and applied to your configs automatically.",
      "home.cta": "Turbo panel", "home.cta2": "Free config",
      "stat.pool": "IP pool", "stat.verified": "Verified", "stat.relays": "Relays", "stat.warp": "WARP",
      "proto.title": "🔀 Live protocols",
      "proto.text": "One address, several different handshakes. A network that learns one usually still passes the others.",
      "ai.title": "🧠 AI route",
      "ai.text": "Gemini, ChatGPT and Claude all leave through one steady IP, so no login loop and no region error.",
      "ai.relay": "Pinned relay",
      "link.support": "Support", "link.channel": "Channel", "link.github": "GitHub",
      "panel.buildTitle": "Build your turbo panel",
      "panel.buildText": "Paste your Cloudflare token. The worker, the uuid and the configs are created on your own account.",
      "panel.tokenHelp": "Create a token in the Cloudflare dashboard ↗",
      "panel.build": "Build panel", "panel.title": "Turbo panel", "panel.host": "Host",
      "panel.uuid": "UUID", "panel.count": "Configs", "panel.synced": "Last apply",
      "panel.mix": "All three", "panel.apply": "⚡️ Apply fresh IPs", "panel.ping": "📶 Ping",
      "panel.rebuild": "🔄 Rebuild", "panel.fragment": "🧩 Fragment", "panel.delete": "🗑 Delete panel",
      "panel.noise": "🌫 Fragment + noise", "panel.clashFile": "📄 Clash file",
      "panel.openSub": "🌐 Open link", "panel.showQr": "🔳 QR",
      "panel.configs": "Single configs",
      "gw.title": "Subscription served from our own domain",
      "gw.text": "workers.dev does not resolve in Iran, so the subscription comes from our domain instead. The configs themselves are unchanged.",
      "warp.title": "WireGuard / WARP",
      "warp.text": "A real WARP account is registered for you and the endpoint comes from the tested pool.",
      "warp.device": "Device", "warp.network": "Network",
      "warp.v4": "Every carrier (IPv4)", "warp.v6": "Irancell (IPv6)",
      "warp.build": "Build config", "warp.endpoint": "Endpoint", "warp.mode": "Mode",
      "warp.routes": "Routes",
      "warp.download": "⬇️ .conf file", "warp.copylink": "🔗 wireguard link",
      "warp.copyconf": "📋 Copy config text", "warp.qr": "🔳 Scan with WireGuard",
      "warp.appleTitle": "🍏 The right way on iPhone and Mac",
      "warp.appleText": "The official WireGuard app refuses a file carrying obfuscation keys, so this config is clean and standard. Fastest path: in WireGuard tap +, choose \"Create from QR code\", and scan this.",
      "free.title": "Free configs",
      "free.text": "On the shared worker, by the real engine: every address completes a real handshake first.",
      "free.mix": "🧩 Both", "free.build": "Get configs",
      "invite.title": "🎁 Invite friends",
      "invite.text": "Share your personal link. The counter moves as people join.",
      "invite.done": "Invited", "invite.goal": "Required", "invite.share": "📤 Share",
      "settings.title": "⚙️ Settings", "settings.lang": "Language", "settings.theme": "Theme",
      "admin.title": "🛠 Admin",
      "admin.refCount": "Invites required to unlock the bot",
      "admin.freeAdd": "New free server", "admin.usePanel": "🗂 Use my panel",
      "admin.check": "🔎 Health check", "admin.geo": "🌍 Geolocate relays",
      save: "Save", add: "Add", copy: "Copy",
      "tab.home": "Home", "tab.panel": "Panel", "tab.warp": "WARP", "tab.free": "Free", "tab.more": "More",
      healthy: "healthy", unhealthy: "needs a look", copied: "Copied ✅",
      building: "Building…", done: "Done ✅", failed: "Failed: ",
      saved: "Opened. Choose Save or Open in when asked.",
      noPanel: "No panel yet", locked: "Invite your friends to unlock",
      quota: "Your free quota is used up", none: "Nothing found",
      steps: ["Verify token", "Subdomain", "Pick clean IPs", "Upload worker", "Health check"],
      confirmDelete: "Delete the panel and its worker?",
      "err.network": "Could not reach the API",
      "err.title": "No connection to the server",
      "err.tried": "Address tried",
      "err.hint": "Check that the bot is running, that the API is served over HTTPS and that WEBAPP_URL is right.",
      "err.noapiTitle": "API address is not set",
      "err.noapiText": "This page sits on a static host, which has no API on it. Open it with the api parameter, e.g. ?api=https://app.example.com — or serve the whole mini app from the bot's own domain.",
      retry: "Retry"
    }
  };

  function T(key) {
    var pack = STR[state.lang] || STR.fa;
    return pack[key] !== undefined ? pack[key] : (STR.fa[key] !== undefined ? STR.fa[key] : key);
  }

  /* ---------------------------------------------------------- utilities */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function toast(text) {
    var el = $("#toast");
    el.textContent = text;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () { el.classList.remove("show"); }, 3200);
  }

  /* The overlay never outlives the user's patience. It is not a timeout: the
   * request carries on, the escape hatch only gives the screen back. */
  function busy(on, label) {
    var veil = $("#veil");
    var cancel = $("#veilCancel");
    veil.hidden = !on;
    $("#veilText").textContent = label || T("working");
    cancel.hidden = true;
    clearTimeout(busy._t);
    if (on) {
      busy._t = setTimeout(function () { cancel.hidden = false; }, VEIL_ESCAPE);
    }
  }

  function haptic(kind) {
    try { tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) { /* not everywhere */ }
  }

  function copy(text) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(T("copied")); },
        function () { legacyCopy(text); });
    } else {
      legacyCopy(text);
    }
    haptic("light");
  }

  function legacyCopy(text) {
    var box = document.createElement("textarea");
    box.value = text;
    box.setAttribute("readonly", "readonly");
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    try { document.execCommand("copy"); toast(T("copied")); } catch (e) { /* ignore */ }
    box.remove();
  }

  function openOutside(url) {
    if (!url) return false;
    try {
      if (tg && tg.openLink) { tg.openLink(url, { try_instant_view: false }); return true; }
    } catch (e) { /* older clients */ }
    try { window.open(url, "_blank"); return true; } catch (e) { return false; }
  }

  /* Save a file the way the host will actually allow.
   *
   * Order matters. A real URL wins because Telegram hands it to the system
   * browser, which is the only thing that can pass a .conf to WireGuard on iOS.
   * The Blob path is kept for a desktop browser, where it works and is nicer.
   * Copying is the floor: a user who cannot save can always paste. */
  function save(url, name, body) {
    if (url && openOutside(url)) { toast(T("saved")); haptic("medium"); return; }
    if (body && window.Blob && !tg) {
      try {
        var blob = new Blob([body], { type: "text/plain;charset=utf-8" });
        var href = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = href;
        link.download = name || "autovless.txt";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(href); }, 4000);
        return;
      } catch (e) { /* fall through to copy */ }
    }
    if (body) copy(body);
  }

  function ago(ts) {
    if (!ts) return "—";
    var diff = Math.max(0, Math.floor(Date.now() / 1000) - ts);
    if (diff < 90) return state.lang === "fa" ? "همین حالا" : "just now";
    if (diff < 3600) return Math.floor(diff / 60) + (state.lang === "fa" ? " دقیقه پیش" : "m ago");
    if (diff < 86400) return Math.floor(diff / 3600) + (state.lang === "fa" ? " ساعت پیش" : "h ago");
    return Math.floor(diff / 86400) + (state.lang === "fa" ? " روز پیش" : "d ago");
  }

  /* One request. No deadline: see the file header. */
  async function call(path, body, method) {
    if (API_MISSING) throw new Error("noapi");

    var response;
    try {
      response = await fetch(API + path, {
        method: method || "POST",
        headers: { "content-type": "application/json", "x-init-data": INIT },
        body: method === "GET" ? undefined : JSON.stringify(body || {})
      });
    } catch (error) {
      /* fetch only rejects on a transport problem, and with a message no user
       * can act on. Translate it. */
      throw new Error("network");
    }

    var payload = null;
    try { payload = await response.json(); } catch (e) { payload = null; }
    if (!response.ok || !payload || payload.ok === false) {
      throw new Error((payload && payload.error) || response.status);
    }
    return payload;
  }

  function explain(message) {
    if (message === "noapi") return T("err.noapiTitle");
    if (message === "network") return T("err.network");
    return T("failed") + message;
  }

  /* A failure to load state is fatal: the app has nothing to show. Say why, on
   * screen, and keep it there. A toast that fades after two seconds is not an
   * error message. */
  function fatal(message) {
    busy(false);
    var noApi = message === "noapi";
    var card = $("#fatal");
    if (!card) {
      card = document.createElement("div");
      card.className = "card glass";
      card.id = "fatal";
      card.innerHTML =
        '<h2 id="fatalTitle"></h2><p class="muted" id="fatalText"></p>' +
        '<div class="kv"><span id="fatalTriedLabel"></span><code id="fatalApi"></code></div>' +
        '<button class="btn primary block" id="fatalRetry"></button>';
      var home = $('.view[data-view="home"]');
      home.insertBefore(card, home.firstChild);
      $("#fatalRetry").addEventListener("click", function () {
        card.remove();
        load();
      });
    }
    $("#fatalTitle").textContent = noApi ? T("err.noapiTitle") : T("err.title");
    $("#fatalText").textContent = noApi ? T("err.noapiText") : explain(message) + " · " + T("err.hint");
    $("#fatalTriedLabel").textContent = T("err.tried");
    $("#fatalApi").textContent = API + "/api/state";
    $("#fatalRetry").textContent = T("retry");
    $("#fatalRetry").hidden = noApi;
    $("#heroState").textContent = "offline";
    go("home");
  }

  /* --------------------------------------------------------------- theme */
  function applyTheme(theme) {
    state.theme = theme;
    var resolved = theme;
    if (theme === "auto") {
      resolved = tg && tg.colorScheme === "light" ? "light" : "dark";
    }
    document.documentElement.setAttribute("data-theme", resolved);
    $("#themeBtn").textContent = resolved === "light" ? "☀️" : "🌙";
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", resolved === "light" ? "#f4f6fc" : "#080b14");
    $$("#setTheme .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.theme === theme);
    });
  }

  function applyLang(lang) {
    state.lang = lang === "en" ? "en" : "fa";
    document.documentElement.lang = state.lang;
    document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
    $("#langBtn").textContent = state.lang === "fa" ? "EN" : "FA";
    $$("[data-i18n]").forEach(function (node) {
      var value = T(node.getAttribute("data-i18n"));
      if (typeof value === "string") node.textContent = value;
    });
    $$("#setLang .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.lang === state.lang);
    });
    if (state.data) render(state.data);
    /* Direction just changed, so every measurement the dock holds is stale. */
    dock.place(true);
  }

  /* ------------------------------------------------------------ the dock */
  /*
   * The indicator is placed from live geometry rather than computed from an
   * index, and that is the whole fix. Deriving an offset from "button 3 of 5"
   * assumes every button is the same width and that the first one starts at the
   * inline start of the bar - both false once a label wraps, once a font loads
   * late, or once the direction is RTL and the visual order is reversed.
   * getBoundingClientRect knows the truth in every one of those cases.
   *
   * place(instant) is called on tab change, on resize, on direction change, once
   * fonts have loaded and once more on the frame after first paint, because a
   * webview reports a zero-width bar if you ask too early - which is why the old
   * blob used to start life parked in the corner.
   */
  var dock = (function () {
    var bar = null;
    var ind = null;

    function place(instant) {
      bar = bar || $("#dock");
      ind = ind || $("#dockInd");
      if (!bar || !ind) return;
      var active = $(".dock-btn.active", bar);
      var first = $(".dock-btn", bar);
      if (!active || !first) return;
      var box = active.getBoundingClientRect();
      var origin = first.getBoundingClientRect();
      /* A webview asked too early reports zero here. Bail rather than park the
       * indicator in the corner, which is what the old bar did on cold start. */
      if (!box.width || !origin.width) return;
      if (instant) bar.classList.remove("ready");
      /* Measured button to button, and the indicator is anchored to the first
       * button's own edge in CSS, so this is a pure delta owing nothing to the
       * border or the padding.
       *
       * The mirrored edge is used in RTL because that is where the indicator is
       * anchored, but the sign is *not* mirrored: inset-inline-start flips with
       * the direction and translateX does not, so a tab further along an RTL bar
       * is further left on screen and therefore a negative translate. Getting
       * this backwards sends the indicator off the end of the bar, which is
       * exactly what a naive left-to-right offset did here before. */
      var offset = document.documentElement.dir === "rtl"
        ? box.right - origin.right
        : box.left - origin.left;
      bar.style.setProperty("--w", Math.round(box.width) + "px");
      bar.style.setProperty("--x", Math.round(offset) + "px");
      if (instant) {
        /* Skip the transition for this one placement, then re-arm it. */
        void ind.offsetWidth;
        requestAnimationFrame(function () { bar.classList.add("ready"); });
      } else {
        bar.classList.add("ready");
      }
    }

    function bind() {
      $$(".dock-btn").forEach(function (btn) {
        btn.addEventListener("click", function () { go(btn.dataset.tab); });
      });
      window.addEventListener("resize", function () { place(true); });
      window.addEventListener("orientationchange", function () {
        setTimeout(function () { place(true); }, 220);
      });
      if (window.ResizeObserver) {
        try { new ResizeObserver(function () { place(true); }).observe($("#dock")); }
        catch (e) { /* older webview */ }
      }
      if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () { place(true); });
      }
      requestAnimationFrame(function () {
        place(true);
        setTimeout(function () { place(true); }, 120);
      });
      swipe();
    }

    /* Swiping between tabs, which a bottom bar this size invites. Vertical
     * intent wins, and anything inside a horizontally scrollable element is left
     * alone so the format picker and the config box still scroll. */
    function swipe() {
      var x0 = 0, y0 = 0, live = false;
      var main = $("#views");
      main.addEventListener("touchstart", function (event) {
        if (event.touches.length !== 1) { live = false; return; }
        var node = event.target;
        while (node && node !== main) {
          if (node.classList && (node.classList.contains("seg") || node.classList.contains("pre") ||
              node.classList.contains("copybox"))) { live = false; return; }
          node = node.parentNode;
        }
        x0 = event.touches[0].clientX;
        y0 = event.touches[0].clientY;
        live = true;
      }, { passive: true });
      main.addEventListener("touchend", function (event) {
        if (!live) return;
        live = false;
        var touch = event.changedTouches && event.changedTouches[0];
        if (!touch) return;
        var dx = touch.clientX - x0;
        var dy = touch.clientY - y0;
        if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.6) return;
        var forward = document.documentElement.dir === "rtl" ? dx > 0 : dx < 0;
        var index = TABS.indexOf(state.tab) + (forward ? 1 : -1);
        if (index < 0 || index >= TABS.length) return;
        go(TABS[index]);
      }, { passive: true });
    }

    return { place: place, bind: bind };
  })();

  function go(tab) {
    if (TABS.indexOf(tab) < 0) tab = "home";
    state.tab = tab;
    $$(".dock-btn").forEach(function (b) {
      var on = b.dataset.tab === tab;
      b.classList.toggle("active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$(".view").forEach(function (v) { v.classList.toggle("active", v.dataset.view === tab); });
    dock.place(false);
    haptic("light");
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (tab === "more" && state.data && state.data.user.isAdmin) loadAdmin();
  }

  /* -------------------------------------------------------------- render */
  function render(data) {
    state.data = data;
    $("#brandName").textContent = data.brand || "AutoVless";

    var stats = data.stats || {};
    $("#stPool").textContent = stats.pool || 0;
    $("#stVerified").textContent = stats.verified || 0;
    $("#stRelays").textContent = stats.relays || 0;
    $("#stWarp").textContent = stats.warp || 0;
    $("#heroPing").textContent = stats.best ? Math.round(stats.best) + "ms" : "—";
    $("#heroState").textContent = data.user.name || data.brand;

    var protocols = data.protocols || { vless: true, trojan: true, shadowsocks: false };
    var badges = $("#protoBadges");
    badges.innerHTML = "";
    [["VLESS", protocols.vless], ["Trojan", protocols.trojan],
     ["Shadowsocks", protocols.shadowsocks], ["WireGuard", true]].forEach(function (pair) {
      var span = document.createElement("span");
      span.className = "badge" + (pair[1] ? " on" : "");
      span.textContent = pair[0];
      badges.appendChild(span);
    });
    $("#protoCount").textContent = [protocols.vless, protocols.trojan, protocols.shadowsocks, true]
      .filter(Boolean).length + "/4";
    $("#fmtSs").hidden = !protocols.shadowsocks;

    var links = data.links || {};
    [["#lnkSupport", links.support], ["#lnkChannel", links.channel], ["#lnkGithub", links.github]]
      .forEach(function (pair) {
        var node = $(pair[0]);
        if (pair[1]) { node.href = pair[1]; node.hidden = false; } else { node.hidden = true; }
      });

    var panel = data.panel;
    $("#panelEmpty").hidden = !!panel;
    $("#panelCard").hidden = !panel;
    if (panel) {
      $("#panelHost").textContent = panel.host;
      $("#panelUuid").textContent = panel.uuid;
      $("#panelCount").textContent = (panel.endpoints || []).length;
      $("#panelSynced").textContent = ago(panel.syncedAt || panel.updatedAt);
      $("#gwNote").hidden = !panel.gateway;
      var health = $("#panelHealth");
      health.textContent = panel.healthy ? T("healthy") : T("unhealthy");
      health.className = "pill" + (panel.healthy ? "" : " ghost");
      showSub(state.fmt);
      var list = $("#configList");
      list.innerHTML = "";
      (panel.vless || []).concat(panel.trojan || [], panel.ss || []).forEach(function (link) {
        var row = document.createElement("div");
        row.className = "rowitem";
        var code = document.createElement("code");
        code.textContent = link;
        var btn = document.createElement("button");
        btn.className = "btn tiny";
        btn.textContent = T("copy");
        btn.onclick = function () { copy(link); };
        row.appendChild(code); row.appendChild(btn);
        list.appendChild(row);
      });
      $("#aiRelay").textContent = panel.aiRelay || "—";
      $("#aiFlag").textContent = panel.aiCountry || "—";
    } else {
      $("#aiRelay").textContent = "—";
    }

    var free = data.free || {};
    if (free.sub) {
      $("#freeSubBox").hidden = false;
      if (($("#freeSub").textContent || "—") === "—") $("#freeSub").textContent = free.sub;
    }

    var ref = data.referral || {};
    $("#inviteCount").textContent = ref.invited || 0;
    $("#inviteGoal").textContent = ref.required || 0;
    $("#inviteLink").textContent = ref.link || "—";
    var pct = ref.required ? Math.min(100, Math.round((ref.invited / ref.required) * 100)) : 100;
    $("#inviteBar").style.width = pct + "%";

    $("#adminCard").hidden = !data.user.isAdmin;
    $$("#setLang .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.lang === state.lang);
    });
    $$("#setTheme .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.theme === state.theme);
    });
  }

  function subUrl(fmt) {
    var panel = state.data && state.data.panel;
    if (!panel) return "";
    var links = panel.links || {};
    return links[fmt] || links.sub || panel.direct && panel.direct.sub || "";
  }

  function showSub(fmt) {
    state.fmt = fmt;
    var url = subUrl(fmt);
    /* A panel with no links at all used to throw here and take the whole render
     * down with it, leaving a blank panel screen and no explanation. */
    $("#subLink").textContent = url || T("none");
    $("#qrImg").removeAttribute("src");
    $$("#subFormats .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.fmt === fmt);
    });
  }

  /* ---------------------------------------------------------------- boot */
  async function load() {
    try {
      var data = await call("/api/state", {});
      var existing = $("#fatal");
      if (existing) existing.remove();
      applyLang(data.user.lang);
      applyTheme(data.user.theme || "auto");
      render(data);
      dock.place(true);
      if (data.referral && data.referral.enabled && !data.referral.unlocked) {
        toast(T("locked"));
        go("more");
      }
    } catch (error) {
      fatal(error.message);
    }
  }

  /* -------------------------------------------------------------- panel */
  function drawSteps(step) {
    var box = $("#steps");
    box.hidden = false;
    box.innerHTML = "";
    T("steps").forEach(function (label, index) {
      var li = document.createElement("li");
      li.textContent = label;
      li.className = index < step ? "done" : index === step ? "active" : "";
      box.appendChild(li);
    });
  }

  async function pollJob(job) {
    for (var attempt = 0; attempt < 150; attempt++) {
      await new Promise(function (r) { setTimeout(r, 2000); });
      var payload;
      try { payload = await call("/api/job/" + job, null, "GET"); } catch (e) { continue; }
      var info = payload.job || {};
      drawSteps(info.step || 0);
      if (info.state === "done") return info.result;
      if (info.state === "failed") throw new Error(info.error || "build failed");
    }
    throw new Error("the build is taking unusually long; check the bot");
  }

  async function buildPanel(mode) {
    var token = $("#tokenInput").value.trim();
    if (!token && mode !== "rebuild") { toast("token?"); return; }
    busy(true, T("building"));
    drawSteps(0);
    try {
      var started = await call("/api/panel/build", { token: token, mode: mode || "build" });
      await pollJob(started.job);
      toast(T("done"));
      haptic("medium");
      $("#tokenInput").value = "";
      await load();
      go("panel");
    } catch (error) {
      toast(explain(error.message));
    } finally {
      busy(false);
    }
  }

  async function exportFile(format) {
    busy(true);
    try {
      var data = await call("/api/panel/export", { format: format });
      save(data.url, data.filename, data.body);
    } catch (error) { toast(explain(error.message)); } finally { busy(false); }
  }

  /* --------------------------------------------------------------- admin */
  async function loadAdmin() {
    try {
      var data = await call("/api/admin/state", {});
      var stats = data.stats || {};
      $("#adminStats").innerHTML = "";
      [["users", stats.users], ["panels", stats.panels], ["healthy", stats.panels_healthy],
       ["warp", stats.warp_users]].forEach(function (pair) {
        var card = document.createElement("div");
        card.className = "card stat";
        card.innerHTML = "<span>" + pair[0] + "</span><b>" + (pair[1] || 0) + "</b>";
        $("#adminStats").appendChild(card);
      });

      var flags = $("#adminFlags");
      flags.innerHTML = "";
      Object.keys(data.flags || {}).forEach(function (key) {
        var row = document.createElement("div");
        row.className = "rowitem";
        var label = document.createElement("span");
        label.textContent = key;
        var btn = document.createElement("button");
        btn.className = "btn tiny";
        btn.textContent = data.flags[key] ? "ON" : "OFF";
        btn.onclick = async function () {
          try { await call("/api/admin/flag", { key: key }); loadAdmin(); } catch (e) { toast(explain(e.message)); }
        };
        row.appendChild(label); row.appendChild(btn);
        flags.appendChild(row);
      });

      $("#refRequired").value = (data.referral || {}).required || 0;

      var free = $("#adminFree");
      free.innerHTML = "";
      var ai = data.ai || {};
      var note = document.createElement("div");
      note.className = "rowitem";
      note.innerHTML = "<span>AI relays (US / verified)</span><b>" +
        ((ai.relays && ai.relays.us) || 0) + " / " + ((ai.relays && ai.relays.verified) || 0) + "</b>";
      free.appendChild(note);

      var gw = data.gateway || {};
      var gwRow = document.createElement("div");
      gwRow.className = "rowitem";
      gwRow.innerHTML = "<span>sub gateway</span><code>" +
        (gw.enabled ? String(gw.origin) : "off") + "</code>";
      free.appendChild(gwRow);

      var servers = await call("/api/admin/free", { action: "list" });
      (servers.servers || []).forEach(function (server) {
        var row = document.createElement("div");
        row.className = "rowitem";
        var code = document.createElement("code");
        code.textContent = (server.healthy ? "✅ " : "⚠️ ") + server.host;
        var toggle = document.createElement("button");
        toggle.className = "btn tiny";
        toggle.textContent = server.active ? "ON" : "OFF";
        toggle.onclick = async function () {
          try { await call("/api/admin/free", { action: "toggle", id: server.id }); loadAdmin(); }
          catch (e) { toast(explain(e.message)); }
        };
        var kill = document.createElement("button");
        kill.className = "btn tiny danger";
        kill.textContent = "🗑";
        kill.onclick = async function () {
          try { await call("/api/admin/free", { action: "delete", id: server.id }); loadAdmin(); }
          catch (e) { toast(explain(e.message)); }
        };
        row.appendChild(code); row.appendChild(toggle); row.appendChild(kill);
        free.appendChild(row);
      });
    } catch (error) {
      toast(explain(error.message));
    }
  }

  /* --------------------------------------------------------------- events */
  function bind() {
    $$("[data-go]").forEach(function (btn) {
      btn.addEventListener("click", function () { go(btn.dataset.go); });
    });
    $$("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = $(btn.dataset.copy);
        copy(target ? target.textContent : "");
      });
    });

    $("#veilCancel").addEventListener("click", function () { busy(false); });

    $("#langBtn").addEventListener("click", async function () {
      var next = state.lang === "fa" ? "en" : "fa";
      applyLang(next);
      try { await call("/api/settings", { lang: next }); } catch (e) { /* cosmetic */ }
    });

    $("#themeBtn").addEventListener("click", async function () {
      var next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
      applyTheme(next);
      try { await call("/api/settings", { theme: next }); } catch (e) { /* cosmetic */ }
    });

    $$("#setLang .seg-btn").forEach(function (b) {
      b.addEventListener("click", async function () {
        applyLang(b.dataset.lang);
        try { await call("/api/settings", { lang: b.dataset.lang }); } catch (e) { /* cosmetic */ }
      });
    });
    $$("#setTheme .seg-btn").forEach(function (b) {
      b.addEventListener("click", async function () {
        applyTheme(b.dataset.theme);
        try { await call("/api/settings", { theme: b.dataset.theme }); } catch (e) { /* cosmetic */ }
      });
    });

    $$("#subFormats .seg-btn").forEach(function (b) {
      b.addEventListener("click", function () { showSub(b.dataset.fmt); });
    });
    $("#subOpen").addEventListener("click", function () {
      var url = subUrl(state.fmt);
      if (url) openOutside(url); else toast(T("none"));
    });
    $("#subQr").addEventListener("click", function () {
      var url = subUrl(state.fmt);
      if (!url) { toast(T("none")); return; }
      $("#qrImg").src = API + "/api/qr?text=" + encodeURIComponent(url);
    });

    $("#buildBtn").addEventListener("click", function () { buildPanel("build"); });
    $("#rebuildBtn").addEventListener("click", function () { buildPanel("rebuild"); });

    $("#applyBtn").addEventListener("click", async function () {
      busy(true);
      try {
        await call("/api/panel/apply", {});
        toast(T("done"));
        await load();
      } catch (error) { toast(explain(error.message)); } finally { busy(false); }
    });

    $("#pingBtn").addEventListener("click", async function () {
      busy(true);
      try {
        var data = await call("/api/panel/ping", {});
        var box = $("#pingRows");
        box.innerHTML = "";
        (data.rows || []).forEach(function (row) {
          var item = document.createElement("div");
          item.className = "rowitem";
          var code = document.createElement("code");
          code.textContent = row.ip + ":" + row.port;
          var mark = document.createElement("b");
          mark.className = row.latency ? "ok" : "bad";
          mark.textContent = row.latency ? Math.round(row.latency) + "ms" : "✕";
          item.appendChild(code); item.appendChild(mark);
          box.appendChild(item);
        });
      } catch (error) { toast(explain(error.message)); } finally { busy(false); }
    });

    $("#fragBtn").addEventListener("click", function () { exportFile("fragment"); });
    $("#noiseBtn").addEventListener("click", function () { exportFile("noise"); });
    $("#clashBtn").addEventListener("click", function () { exportFile("clash"); });

    $("#deleteBtn").addEventListener("click", function () {
      var run = async function () {
        busy(true);
        try { await call("/api/panel/delete", {}); toast(T("done")); await load(); }
        catch (error) { toast(explain(error.message)); } finally { busy(false); }
      };
      if (tg && tg.showConfirm) tg.showConfirm(T("confirmDelete"), function (ok) { if (ok) run(); });
      else if (confirm(T("confirmDelete"))) run();
    });

    $$("#wgPlatform .seg-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        state.platform = b.dataset.platform;
        $$("#wgPlatform .seg-btn").forEach(function (x) { x.classList.toggle("active", x === b); });
      });
    });
    $$("#wgFamily .seg-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        state.family = b.dataset.family;
        $$("#wgFamily .seg-btn").forEach(function (x) { x.classList.toggle("active", x === b); });
      });
    });

    $("#wgBuild").addEventListener("click", async function () {
      busy(true);
      try {
        var data = await call("/api/warp/build", { platform: state.platform, family: state.family });
        state.warp = data;
        $("#wgResult").hidden = false;
        $("#wgEndpoint").textContent = data.endpoint || "—";
        $("#wgMode").textContent = data.clean ? "WireGuard" : "AmneziaWG";
        $("#wgRoutes").textContent = (data.routes || []).join(", ") || "—";
        $("#wgConf").textContent = data.conf || "";
        var apple = state.platform === "ios" || state.platform === "macos";
        $("#wgApple").hidden = !apple;
        $("#wgQrImg").removeAttribute("src");
        /* On the Apple platforms the QR is the path that works, so show it
         * without being asked. */
        if (apple && data.qr) $("#wgQrImg").src = data.qr;
        haptic("medium");
      } catch (error) { toast(explain(error.message)); } finally { busy(false); }
    });

    $("#wgQr").addEventListener("click", function () {
      if (!state.warp) return;
      if (state.warp.qr) $("#wgQrImg").src = state.warp.qr;
      else $("#wgQrImg").src = API + "/api/qr?text=" + encodeURIComponent(state.warp.conf || "");
    });
    $("#wgDownload").addEventListener("click", function () {
      if (state.warp) save(state.warp.url, state.warp.filename || "warp.conf", state.warp.conf || "");
    });
    $("#wgCopyConf").addEventListener("click", function () {
      if (state.warp) copy(state.warp.conf || "");
    });
    $("#wgCopyLink").addEventListener("click", function () {
      if (state.warp) copy(state.warp.link || "");
    });

    $$("#freeProto .seg-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        state.proto = b.dataset.proto;
        $$("#freeProto .seg-btn").forEach(function (x) { x.classList.toggle("active", x === b); });
      });
    });

    $("#freeBtn").addEventListener("click", async function () {
      busy(true);
      $("#freeMeta").textContent = T("building");
      try {
        var data = await call("/api/free/build", { protocol: state.proto });
        state.free = data;
        $("#freeSubBox").hidden = false;
        $("#freeSub").textContent = data.sub;
        $("#freeMeta").textContent = data.host + " · " + data.count +
          (data.best ? " · " + Math.round(data.best) + "ms" : "");
        var box = $("#freeList");
        box.innerHTML = "";
        (data.links || []).forEach(function (link) {
          var row = document.createElement("div");
          row.className = "rowitem";
          var code = document.createElement("code");
          code.textContent = link;
          var btn = document.createElement("button");
          btn.className = "btn tiny";
          btn.textContent = T("copy");
          btn.onclick = function () { copy(link); };
          row.appendChild(code); row.appendChild(btn);
          box.appendChild(row);
        });
        haptic("medium");
      } catch (error) {
        $("#freeMeta").textContent = "";
        toast(error.message === "quota" ? T("quota") : explain(error.message));
      } finally { busy(false); }
    });

    $("#inviteShare").addEventListener("click", function () {
      var link = ($("#inviteLink").textContent || "").trim();
      if (!link || link === "—") return;
      var url = "https://t.me/share/url?url=" + encodeURIComponent(link);
      if (tg && tg.openTelegramLink) tg.openTelegramLink(url); else window.open(url, "_blank");
    });

    $("#refSave").addEventListener("click", async function () {
      try {
        await call("/api/admin/referral", { required: Number($("#refRequired").value || 0) });
        toast(T("done"));
      } catch (error) { toast(explain(error.message)); }
    });
    $("#freeAdd").addEventListener("click", async function () {
      try {
        await call("/api/admin/free", { action: "add", value: $("#freeServer").value.trim() });
        $("#freeServer").value = "";
        toast(T("done"));
        loadAdmin();
      } catch (error) { toast(explain(error.message)); }
    });
    $("#freePanelBtn").addEventListener("click", async function () {
      try { await call("/api/admin/free", { action: "panel" }); toast(T("done")); loadAdmin(); }
      catch (error) { toast(explain(error.message)); }
    });
    $("#freeCheck").addEventListener("click", async function () {
      busy(true);
      try {
        var data = await call("/api/admin/free", { action: "check" });
        toast(data.healthy + " / " + data.total);
      } catch (error) { toast(explain(error.message)); } finally { busy(false); }
    });
    $("#geoBtn").addEventListener("click", async function () {
      busy(true);
      try { await call("/api/admin/ai", { action: "geo" }); toast(T("done")); loadAdmin(); }
      catch (error) { toast(explain(error.message)); } finally { busy(false); }
    });
  }

  /* ---------------------------------------------------------------- start */
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (e) { /* older clients */ }
    try { tg.setHeaderColor("secondary_bg_color"); } catch (e) { /* optional */ }
    if (tg.onEvent) tg.onEvent("themeChanged", function () { if (state.theme === "auto") applyTheme("auto"); });
  }
  bind();
  dock.bind();
  busy(false);
  applyLang((tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code === "en") ? "en" : "fa");
  applyTheme("auto");
  if (!INIT) {
    toast(state.lang === "fa" ? "این صفحه را از داخل تلگرام باز کن" : "Open this page from inside Telegram");
  } else if (API_MISSING) {
    fatal("noapi");
  } else {
    load();
  }
})();
