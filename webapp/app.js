/* AutoVless Mini App - client logic.
 *
 * Fixes in this version
 *  - A stray ")" in bind() was a SyntaxError: the whole script never ran, so the
 *    page sat forever on the skeleton with "در حال بارگذاری…". That is the
 *    stuck screen users reported.
 *  - telegram-web-app.js is served from telegram.org, which is filtered in Iran
 *    for anyone whose system VPN is off (Telegram's own proxy does not cover the
 *    webview). Without it initData was empty and the app said "open me inside
 *    Telegram". initData is now read straight from the launch URL fragment as a
 *    fallback, and ready/expand/openLink are sent over the native bridge.
 *  - Every request has a timeout, so a dead API shows the error card instead of
 *    an endless spinner.
 *  - Panel build now polls the job, and every button in the markup is wired
 *    (apply, ping, rebuild, fragment, noise, clash, delete, WARP QR/link,
 *    invite share, settings, admin).
 */
(function () {
  "use strict";

  // ------------------------------------------------------------ Telegram bridge
  function hashParams() {
    var out = {};
    var raw = (location.hash || "").replace(/^#/, "");
    raw.split("&").forEach(function (pair) {
      if (!pair) return;
      var i = pair.indexOf("=");
      var k = i < 0 ? pair : pair.slice(0, i);
      var v = i < 0 ? "" : pair.slice(i + 1);
      try { out[decodeURIComponent(k)] = decodeURIComponent(v); } catch (e) { out[k] = v; }
    });
    return out;
  }
  var HASH = hashParams();
  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  function postEvent(type, data) {
    var payload = JSON.stringify(data || {});
    try {
      if (window.TelegramWebviewProxy && window.TelegramWebviewProxy.postEvent) {
        window.TelegramWebviewProxy.postEvent(type, payload); return true;
      }
      if (window.external && "notify" in window.external) {
        window.external.notify(JSON.stringify({ eventType: type, eventData: data || {} })); return true;
      }
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(JSON.stringify({ eventType: type, eventData: data || {} }), "*"); return true;
      }
    } catch (e) {}
    return false;
  }
  function initData() {
    if (tg && tg.initData) return tg.initData;
    return HASH.tgWebAppData || "";
  }
  function initUserLang() {
    try {
      var p = new URLSearchParams(initData());
      var u = JSON.parse(p.get("user") || "{}");
      return u.language_code === "fa" ? "fa" : (u.language_code ? "en" : "fa");
    } catch (e) { return "fa"; }
  }
  function tgReady() {
    if (tg) { try { tg.ready(); tg.expand(); } catch (e) {} return; }
    postEvent("web_app_ready"); postEvent("web_app_expand");
  }
  function colorScheme() {
    if (tg && tg.colorScheme) return tg.colorScheme;
    try {
      var th = JSON.parse(HASH.tgWebAppThemeParams || "{}");
      var bg = String(th.bg_color || "#000000").replace("#", "");
      var n = parseInt(bg.length === 3 ? bg.replace(/./g, "$&$&") : bg, 16);
      var lum = ((n >> 16) & 255) * 0.299 + ((n >> 8) & 255) * 0.587 + (n & 255) * 0.114;
      return lum > 150 ? "light" : "dark";
    } catch (e) { return "dark"; }
  }

  // ------------------------------------------------------------ config
  var params = new URLSearchParams(location.search);
  var API_OVERRIDE = (params.get("api") || window.AUTOVLESS_API || "").replace(/\/+$/, "");
  var API = API_OVERRIDE || location.origin.replace(/\/+$/, "");
  var STATIC_HOST = /(^|\.)github\.io$|(^|\.)pages\.dev$|(^|\.)netlify\.app$|(^|\.)vercel\.app$/i.test(location.hostname);
  var API_MISSING = STATIC_HOST && !API_OVERRIDE;
  var REQUEST_TIMEOUT = 25000;
  var VEIL_ESCAPE = 12000;
  var TABS = ["home", "panel", "warp", "free", "more"];
  var APPLE = { ios: true, macos: true };
  var state = { lang: "fa", theme: "auto", data: null, fmt: "sub", proto: "vless", platform: "android", family: "v4", warp: null, tab: "home", admin: null };

  var STR = { fa: {
    tagline:"تونل اختصاصی خودت",loading:"در حال بارگذاری…",working:"در حال انجام…","veil.hide":"بستن این پرده","home.title":"شبکه‌ی تو، همیشه تازه","home.text":"آی‌پی‌های تمیز خودکار اسکن، تست و روی کانفیگ‌هایت اعمال می‌شوند.","home.cta":"⚡️ پنل توربو","home.cta2":"🎁 کانفیگ رایگان","stat.pool":"استخر آی‌پی","stat.verified":"تاییدشده","stat.relays":"رله","stat.warp":"وارپ","proto.title":"🔀 پروتکل‌های فعال","proto.text":"یک آدرس، چند دست‌دادن متفاوت. شبکه‌ای که یکی را بشناسد معمولاً بقیه را رد می‌کند.","ai.title":"🧠 مسیر هوش مصنوعی","ai.text":"جیمینای، ChatGPT و کلاد خودکار از یک پروکسی‌آی‌پی ثابت در کشور مجاز خارج می‌شوند؛ این ترافیک روی ورکر خودت است و از سرور ما رد نمی‌شود.","ai.relay":"رله‌ی پین‌شده","ai.none":"بعد از ساخت پنل خودکار تنظیم می‌شود","link.support":"💬 پشتیبانی","link.channel":"📣 کانال","link.github":"🐙 گیت‌هاب","pay.title":"🔐 اشتراک ورود","pay.text":"برای استفاده از امکانات، یک‌بار پرداخت کن. بعد از پرداخت، همه‌چیز خودکار باز می‌شود.","pay.price":"مبلغ","pay.period":"اعتبار","pay.forever":"دائمی","pay.days":" روز","pay.zp":"💳 پرداخت با کارت بانکی","pay.stars":"⭐️ پرداخت با استارز تلگرام","pay.check":"🔄 پرداخت کردم، بررسی کن","pay.none":"درگاه پرداخت هنوز تنظیم نشده.","pay.done":"پرداخت تأیید شد 🎉","pay.pending":"هنوز پرداختی ثبت نشده؛ چند ثانیه دیگر دوباره بزن.","pay.opened":"درگاه باز شد؛ بعد از پرداخت برگرد و «بررسی» را بزن.","pay.toman":" تومان","pay.starsUnit":" ⭐️","panel.buildTitle":"ساخت پنل توربو","panel.buildText":"توکن Cloudflare خودت را بده؛ ورکر و کانفیگ‌ها روی اکانت خودت ساخته می‌شوند و ترافیک از سرور ما عبور نمی‌کند.","panel.tokenHelp":"ساخت توکن در داشبورد کلادفلر ↗","panel.build":"ساخت پنل","panel.title":"پنل توربو","panel.host":"هاست","panel.uuid":"شناسه","panel.count":"کانفیگ‌ها","panel.synced":"آخرین اعمال","panel.mix":"همه","panel.apply":"⚡️ آی‌پی تازه","panel.ping":"📶 پینگ","panel.rebuild":"🔄 بازسازی","panel.fragment":"🧩 فرگمنت","panel.delete":"🗑 حذف پنل","panel.noise":"🌫 فرگمنت + نویز","panel.clashFile":"📄 فایل Clash","panel.openSub":"🌐 باز کردن","panel.showQr":"🔳 کیوآر","panel.configs":"کانفیگ‌های تک","panel.locked":"پنل بعد از فعال شدن اشتراک در دسترس است.","gw.title":"لینک اشتراک روی دامنه‌ی خودمان","gw.text":"workers.dev در ایران رزولوو نمی‌شود، پس ساب از دامنه‌ی ما سرو می‌شود.","warp.title":"وایرگارد / وارپ","warp.text":"اکانت وارپ واقعی برایت ساخته می‌شود و اندپوینت از استخر تست‌شده انتخاب می‌شود.","warp.device":"دستگاه","warp.network":"شبکه","warp.v4":"همه اپراتورها (IPv4)","warp.v6":"ایرانسل (IPv6)","warp.build":"ساخت کانفیگ","warp.endpoint":"اندپوینت","warp.mode":"حالت","warp.routes":"مسیرها","warp.download":"⬇️ فایل .conf","warp.copylink":"🔗 لینک v2ray","warp.copyconf":"📋 کپی متن","warp.qr":"🔳 کیوآر","warp.appleTitle":"🍏 آیفون و مک: اول AmneziaWG","warp.appleText":"اپ رسمی WireGuard مبهم‌سازی ندارد و روی اغلب اپراتورها فیلتر می‌شود. اپ رایگان AmneziaWG را از App Store نصب کن و فایل یا کیوآر زیر را در آن وارد کن.","warp.awgDownload":"⬇️ فایل AmneziaWG","warp.awgQr":"🔳 کیوآر AmneziaWG","warp.awgStore":"🍏 نصب AmneziaWG","warp.hiddify":"🚀 لینک Hiddify (نویز دار)","warp.plainTitle":"فایل استاندارد (اپ رسمی WireGuard)","warp.clean":"استاندارد","warp.amnezia":"AmneziaWG","free.title":"کانفیگ رایگان","free.text":"روی سرور مشترک ربات، با موتور واقعی: هر آی‌پی قبل از تحویل هندشیک واقعی می‌دهد.","free.mix":"🧩 هر دو","free.build":"دریافت کانفیگ","invite.title":"🎁 دعوت دوستان","invite.text":"لینک اختصاصی‌ات را بفرست؛ با هر ورود شمارنده بالا می‌رود.","invite.done":"دعوت‌شده","invite.goal":"سهمیه","invite.share":"📤 ارسال به دوستان","settings.title":"⚙️ تنظیمات","settings.lang":"زبان","settings.theme":"پوسته","admin.title":"🛠 پنل مدیریت","admin.refCount":"تعداد دعوت لازم برای باز شدن ربات","admin.freeAdd":"سرور رایگان جدید","admin.usePanel":"🗂 ثبت پنل خودم","admin.check":"🔎 بررسی سلامت","admin.geo":"🌍 مکان‌یابی رله‌ها","admin.pay":"💳 درگاه پرداخت ورود","admin.payOn":"پرداخت اجباری","admin.gateway":"درگاه","admin.amount":"مبلغ (تومان)","admin.starsPrice":"مبلغ (استارز)","admin.days":"اعتبار (روز، ۰=دائمی)","admin.merchant":"مرچنت زرین‌پال","admin.sandbox":"حالت تست","admin.revenue":"درآمد","admin.subs":"مشترک فعال","admin.callback":"آدرس بازگشت","admin.users":"کاربران","admin.panels":"پنل‌ها","admin.pins":"پین AI",save:"ذخیره",add:"افزودن",copy:"کپی",on:"روشن",off:"خاموش","tab.home":"خانه","tab.panel":"پنل","tab.warp":"وارپ","tab.free":"رایگان","tab.more":"بیشتر",healthy:"سالم",unhealthy:"نیاز به بررسی",copied:"کپی شد ✅",building:"در حال ساخت…",done:"انجام شد ✅",failed:"ناموفق: ",saved:"فایل باز شد؛ اگر پرسید Save یا Open in را بزن",noPanel:"هنوز پنلی نداری",locked:"برای استفاده باید دوستانت را دعوت کنی",needPay:"برای استفاده، اشتراک لازم است",cooldown:"کمی صبر کن و دوباره امتحان کن",quota:"سهمیه‌ی رایگانت تمام شده",none:"چیزی پیدا نشد",steps:["بررسی توکن","زیر‌دامنه","انتخاب آی‌پی تمیز","آپلود ورکر","تست سلامت"],confirmDelete:"پنل و ورکرش حذف شود؟",token:"اول توکن را وارد کن","err.network":"وصل شدن به API ممکن نشد","err.timeout":"سرور جواب نداد (تایم‌اوت)","err.unauth":"امضای تلگرام رد شد؛ ساعت سرور را چک کن یا مینی‌اپ را از نو باز کن","err.title":"اتصال به سرور برقرار نشد","err.tried":"آدرسی که امتحان شد","err.hint":"مطمئن شو ربات روشن است، API روی HTTPS سرو می‌شود و WEBAPP_URL درست است.","err.noapiTitle":"آدرس API تنظیم نشده","err.noapiText":"این صفحه روی هاست استاتیک است و API آن‌جا نیست. با ?api=https://your-domain باز کن یا مینی‌اپ را از دامنه‌ی ربات سرو کن.","err.outsideTitle":"این صفحه را از داخل تلگرام باز کن","err.outsideText":"مینی‌اپ فقط داخل تلگرام کار می‌کند. در ربات /app را بزن.",retry:"تلاش دوباره" }, en: {} };
  STR.en = Object.assign({}, STR.fa, { tagline:"your own tunnel", loading:"Loading…", working:"Working…", "veil.hide":"Dismiss", "home.title":"Your network, always fresh", "home.text":"Clean IPs are scanned, tested and applied to your configs automatically.", "home.cta":"⚡️ Turbo panel", "home.cta2":"🎁 Free config", "stat.pool":"IP pool", "stat.verified":"Verified", "stat.relays":"Relays", "stat.warp":"WARP", "proto.title":"🔀 Active protocols", "proto.text":"One address, several handshakes.", "ai.title":"🧠 AI route", "ai.text":"Gemini, ChatGPT and Claude leave automatically through one pinned proxyIP in an allowed country. It runs on your own Worker, not on our server.", "ai.relay":"Pinned relay", "ai.none":"Set automatically once your panel is built", "link.support":"💬 Support", "link.channel":"📣 Channel", "link.github":"🐙 GitHub", "pay.title":"🔐 Access pass", "pay.text":"Pay once to use everything. Access unlocks automatically after payment.", "pay.price":"Price", "pay.period":"Validity", "pay.forever":"Lifetime", "pay.days":" days", "pay.zp":"💳 Pay by bank card", "pay.stars":"⭐️ Pay with Telegram Stars", "pay.check":"🔄 I paid, check it", "pay.none":"No payment gateway is configured yet.", "pay.done":"Payment confirmed 🎉", "pay.pending":"No payment yet; try again in a few seconds.", "pay.opened":"Payment page opened. Come back and tap Check.", "pay.toman":" Toman", "panel.buildTitle":"Build a turbo panel", "panel.buildText":"Paste your Cloudflare token; the Worker is built on your own account and traffic never touches our server.", "panel.tokenHelp":"Create a token on Cloudflare ↗", "panel.title":"Turbo panel", "panel.build":"Build panel", "panel.host":"Host", "panel.uuid":"UUID", "panel.count":"Configs", "panel.synced":"Last applied", "panel.mix":"All", "panel.apply":"⚡️ Fresh IPs", "panel.ping":"📶 Ping", "panel.rebuild":"🔄 Rebuild", "panel.fragment":"🧩 Fragment", "panel.delete":"🗑 Delete panel", "panel.noise":"🌫 Fragment + noise", "panel.clashFile":"📄 Clash file", "panel.openSub":"🌐 Open", "panel.showQr":"🔳 QR", "panel.configs":"Single configs", "panel.locked":"The panel unlocks once your access is active.", "warp.title":"WireGuard / WARP", "warp.build":"Build config", "warp.device":"Device", "warp.network":"Network", "warp.v4":"All carriers (IPv4)", "warp.v6":"Irancell (IPv6)", "warp.endpoint":"Endpoint", "warp.mode":"Mode", "warp.routes":"Routes", "free.title":"Free configs", "free.build":"Get configs", "free.mix":"🧩 Both", "invite.title":"🎁 Invite friends", "invite.text":"Share your link; every join counts.", "invite.done":"Invited", "invite.goal":"Goal", "invite.share":"📤 Share", "settings.title":"⚙️ Settings", "settings.lang":"Language", "settings.theme":"Theme", "admin.title":"🛠 Admin", save:"Save", add:"Add", copy:"Copy", on:"On", off:"Off", "tab.home":"Home", "tab.panel":"Panel", "tab.warp":"WARP", "tab.free":"Free", "tab.more":"More", healthy:"Healthy", unhealthy:"Needs a look", copied:"Copied ✅", done:"Done ✅", failed:"Failed: ", none:"Nothing found", noPanel:"No panel yet", locked:"Invite friends to unlock", needPay:"An access pass is required", cooldown:"Wait a moment and retry", quota:"Free quota used up", steps:["Checking token","Subdomain","Picking clean IPs","Uploading worker","Health check"], confirmDelete:"Delete the panel and its worker?", token:"Enter your token first", "err.network":"Could not reach the API", "err.timeout":"The server did not answer (timeout)", "err.unauth":"Telegram signature rejected; check the server clock or reopen the app", "err.title":"Could not connect to the server", "err.tried":"Tried", "err.hint":"Make sure the bot is running, the API is on HTTPS and WEBAPP_URL is right.", "err.outsideTitle":"Open this inside Telegram", "err.outsideText":"The mini app only works inside Telegram. Send /app to the bot.", retry:"Retry" });

  // ------------------------------------------------------------ helpers
  function T(key) { var p = STR[state.lang] || STR.fa; return p[key] !== undefined ? p[key] : (STR.fa[key] !== undefined ? STR.fa[key] : key); }
  function digits(v) { var s = String(v); return state.lang !== "fa" ? s : s.replace(/[0-9]/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹".charAt(Number(d)); }); }
  function money(v) { return digits(Number(v || 0).toLocaleString("en-US")); }
  function $(s, r) { return (r || document).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function on(sel, fn) { var n = typeof sel === "string" ? $(sel) : sel; if (n) n.onclick = fn; return n; }
  function txt(sel, v) { var n = $(sel); if (n) n.textContent = v; return n; }
  function show(sel, yes) { var n = $(sel); if (n) n.hidden = !yes; return n; }
  function el(t, c, x) { var n = document.createElement(t); if (c) n.className = c; if (x !== undefined) n.textContent = x; return n; }
  function toast(x, k) { var n = $("#toast"); if (!n) return; n.textContent = x; n.className = "toast show" + (k ? " " + k : ""); clearTimeout(toast._t); toast._t = setTimeout(function () { n.className = "toast"; }, 3200); }
  function busy(onoff, label) { var v = $("#veil"), c = $("#veilCancel"); if (!v) return; v.hidden = !onoff; txt("#veilText", label || T("working")); if (c) c.hidden = true; clearTimeout(busy._t); if (onoff) busy._t = setTimeout(function () { if (c) c.hidden = false; }, VEIL_ESCAPE); }
  function haptic(k) { try { tg.HapticFeedback.impactOccurred(k || "light"); } catch (e) { postEvent("web_app_trigger_haptic_feedback", { type: "impact", impact_style: k || "light" }); } }
  function notify(k) { try { tg.HapticFeedback.notificationOccurred(k || "success"); } catch (e) { postEvent("web_app_trigger_haptic_feedback", { type: "notification", notification_type: k || "success" }); } }
  function copy(x) { if (!x) return; if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(x).then(function () { toast(T("copied"), "ok"); }, function () { legacyCopy(x); }); else legacyCopy(x); haptic("light"); }
  function legacyCopy(x) { var b = document.createElement("textarea"); b.value = x; b.style.position = "fixed"; b.style.opacity = "0"; document.body.appendChild(b); b.select(); try { document.execCommand("copy"); toast(T("copied"), "ok"); } catch (e) {} b.remove(); }
  function openOutside(u) {
    if (!u) return false;
    try { if (tg && tg.openLink) { tg.openLink(u, { try_instant_view: false }); return true; } } catch (e) {}
    if (postEvent("web_app_open_link", { url: u })) return true;
    try { window.open(u, "_blank"); return true; } catch (e) { return false; }
  }
  function openTgLink(u) {
    try { if (tg && tg.openTelegramLink) { tg.openTelegramLink(u); return; } } catch (e) {}
    var path = u.replace(/^https?:\/\/t\.me/, "");
    if (!postEvent("web_app_open_tg_link", { path_full: path })) openOutside(u);
  }
  function save(u, n, b) { if (u && openOutside(u)) { toast(T("saved")); return; } if (b && !tg) { try { var o = URL.createObjectURL(new Blob([b], { type: "text/plain;charset=utf-8" })), a = document.createElement("a"); a.href = o; a.download = n || "autovless.txt"; a.click(); setTimeout(function () { URL.revokeObjectURL(o); }, 4000); return; } catch (e) {} } if (b) copy(b); }
  function qrSrc(text) { return API + "/api/qr?text=" + encodeURIComponent(text || ""); }
  function ago(ts) { if (!ts) return "—"; var d = Math.max(0, Math.floor(Date.now() / 1000) - ts); if (d < 90) return state.lang === "fa" ? "همین حالا" : "just now"; if (d < 3600) return digits(Math.floor(d / 60)) + (state.lang === "fa" ? " دقیقه پیش" : "m ago"); if (d < 86400) return digits(Math.floor(d / 3600)) + (state.lang === "fa" ? " ساعت پیش" : "h ago"); return digits(Math.floor(d / 86400)) + (state.lang === "fa" ? " روز پیش" : "d ago"); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  // ------------------------------------------------------------ API
  function ApiError(m, s, p) { var e = new Error(m); e.status = s; e.payload = p; return e; }
  async function call(path, body, method) {
    if (API_MISSING) throw ApiError("noapi", 0, null);
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, REQUEST_TIMEOUT) : null;
    var r;
    try {
      r = await fetch(API + path, {
        method: method || "POST",
        headers: { "content-type": "application/json", "x-init-data": initData() },
        body: method === "GET" ? undefined : JSON.stringify(body || {}),
        cache: "no-store",
        signal: ctl ? ctl.signal : undefined
      });
    } catch (e) {
      throw ApiError(e && e.name === "AbortError" ? "timeout" : "network", 0, null);
    } finally { if (timer) clearTimeout(timer); }
    var p = null; try { p = await r.json(); } catch (e) {}
    if (!r.ok || !p || p.ok === false) {
      var m = (p && p.error) || String(r.status);
      if ((m === "payment_required" || m === "locked") && path !== "/api/state") setTimeout(function () { load(true); }, 0);
      throw ApiError(m, r.status, p);
    }
    return p;
  }
  function explain(e) {
    var m = e && e.message ? e.message : String(e);
    var map = { noapi: "err.noapiTitle", network: "err.network", timeout: "err.timeout", unauthorised: "err.unauth", payment_required: "needPay", locked: "locked", cooldown: "cooldown", quota: "quota", "no panel": "noPanel" };
    return map[m] ? T(map[m]) : T("failed") + m;
  }

  // ------------------------------------------------------------ chrome
  function fatal(k, d) {
    busy(false); document.body.classList.remove("booting");
    var c = $("#fatal");
    if (!c) {
      c = el("div", "card glass fatal"); c.id = "fatal";
      c.innerHTML = '<div class="fatal-icon">!</div><h2 id="fatalTitle"></h2><p class="muted" id="fatalText"></p><div class="kv"><span id="fatalTriedLabel"></span><code id="fatalApi"></code></div><button class="btn primary block" id="fatalRetry" type="button"></button>';
      var home = $(".view[data-view=home]"); if (home) home.prepend(c);
      on("#fatalRetry", function () { c.remove(); load(); });
    }
    var ti = { noapi: "err.noapiTitle", outside: "err.outsideTitle" }, tx = { noapi: "err.noapiText", outside: "err.outsideText" };
    txt("#fatalTitle", T(ti[k] || "err.title"));
    txt("#fatalText", tx[k] ? T(tx[k]) : (d || "") + " · " + T("err.hint"));
    txt("#fatalTriedLabel", T("err.tried"));
    txt("#fatalApi", API + "/api/state");
    txt("#fatalRetry", T("retry"));
    show("#fatalRetry", !tx[k] || k === "noapi");
    txt("#heroState", "⚠️");
    $$(".skeleton").forEach(function (n) { n.classList.remove("skeleton"); });
    go("home");
  }
  function applyTheme(t) {
    state.theme = t; var r = t; if (t === "auto") r = colorScheme() === "light" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", r);
    txt("#themeBtn", r === "light" ? "☀️" : "🌙");
    var m = document.querySelector('meta[name="theme-color"]'); if (m) m.setAttribute("content", r === "light" ? "#f4f6fc" : "#070a13");
    $$("#setTheme .seg-btn").forEach(function (b) { b.classList.toggle("active", b.dataset.theme === t); });
    try { if (tg && tg.setHeaderColor) tg.setHeaderColor(r === "light" ? "#f4f6fc" : "#070a13"); } catch (e) {}
  }
  function applyLang(l) {
    state.lang = l === "en" ? "en" : "fa";
    document.documentElement.lang = state.lang; document.documentElement.dir = state.lang === "fa" ? "rtl" : "ltr";
    txt("#langBtn", state.lang === "fa" ? "EN" : "FA");
    $$("[data-i18n]").forEach(function (n) { var v = T(n.getAttribute("data-i18n")); if (typeof v === "string") n.textContent = v; });
    $$("#setLang .seg-btn").forEach(function (b) { b.classList.toggle("active", b.dataset.lang === state.lang); });
    if (state.data) render(state.data);
    dock.place();
  }
  function persist(body) { call("/api/settings", body).catch(function () {}); }

  var dock = {
    place: function () {
      var b = $("#dock"), i = $("#dockInd"); if (!b || !i) return;
      var a = $(".dock-btn.active", b), f = $(".dock-btn", b); if (!a || !f) return;
      var ar = a.getBoundingClientRect(), fr = f.getBoundingClientRect();
      var x = document.documentElement.dir === "rtl" ? ar.right - fr.right : ar.left - fr.left;
      b.style.setProperty("--w", Math.round(ar.width) + "px"); b.style.setProperty("--x", Math.round(x) + "px"); b.classList.add("ready");
    },
    bind: function () { $$(".dock-btn").forEach(function (b) { b.onclick = function () { go(b.dataset.tab); }; }); window.addEventListener("resize", function () { dock.place(); }); requestAnimationFrame(dock.place); }
  };
  function go(t) {
    if (TABS.indexOf(t) < 0) t = "home"; state.tab = t;
    $$(".dock-btn").forEach(function (b) { var yes = b.dataset.tab === t; b.classList.toggle("active", yes); b.setAttribute("aria-selected", yes ? "true" : "false"); });
    $$(".view").forEach(function (v) { v.classList.toggle("active", v.dataset.view === t); });
    dock.place();
    try { if (tg && tg.BackButton) { if (t === "home") tg.BackButton.hide(); else tg.BackButton.show(); } else postEvent("web_app_setup_back_button", { is_visible: t !== "home" }); } catch (e) {}
    if (t === "more" && state.data && state.data.user && state.data.user.isAdmin && !state.admin) loadAdmin();
    window.scrollTo(0, 0);
  }

  // ------------------------------------------------------------ render
  function isOpen(d) { var p = d.payment || {}, r = d.referral || {}; return (!p.enabled || p.paid) && (!r.enabled || r.unlocked); }
  function renderPaywall(d) {
    var p = d.payment || {}, yes = !!(p.enabled && !p.paid), c = $("#payCard"); if (!c) return;
    c.hidden = !yes; document.body.classList.toggle("unpaid", yes); if (!yes) return;
    var z = []; if (p.zarinpal) z.push(money(p.amount) + T("pay.toman")); if (p.stars) z.push(digits(p.starsPrice) + T("pay.starsUnit"));
    txt("#payPrice", z.join(state.lang === "fa" ? " یا " : " or ") || "—");
    txt("#payPeriod", p.days ? digits(p.days) + T("pay.days") : T("pay.forever"));
    show("#payZp", !!p.zarinpal); show("#payStars", !!p.stars); show("#payNone", !(p.zarinpal || p.stars));
  }
  function copyRow(t) { var r = el("div", "rowitem"); r.appendChild(el("code", "", t)); var b = el("button", "btn tiny", T("copy")); b.type = "button"; b.onclick = function () { copy(t); }; r.appendChild(b); return r; }
  function render(d) {
    state.data = d;
    txt("#brandName", d.brand || "AutoVless"); txt("#logoMark", (d.brand || "A").charAt(0).toUpperCase());
    var s = d.stats || {};
    txt("#stPool", digits(s.pool || 0)); txt("#stVerified", digits(s.verified || 0)); txt("#stRelays", digits(s.relays || 0)); txt("#stWarp", digits(s.warp || 0));
    $$(".skeleton").forEach(function (n) { n.classList.remove("skeleton"); });
    txt("#heroPing", s.best ? digits(Math.round(s.best)) + "ms" : "—");
    txt("#heroState", (state.lang === "fa" ? "سلام " : "Hi ") + ((d.user && d.user.name) || ""));
    renderPaywall(d);

    var p = d.protocols || { vless: true, trojan: true, shadowsocks: false }, badges = $("#protoBadges");
    if (badges) { badges.innerHTML = ""; [["VLESS", p.vless], ["Trojan", p.trojan], ["Shadowsocks", p.shadowsocks], ["WireGuard", true]].forEach(function (x) { badges.appendChild(el("span", "badge" + (x[1] ? " on" : ""), x[0])); }); }
    txt("#protoCount", digits([p.vless, p.trojan, p.shadowsocks, true].filter(Boolean).length) + "/" + digits(4));
    show("#fmtSs", !!p.shadowsocks);

    var links = d.links || {};
    [["#lnkSupport", links.support], ["#lnkChannel", links.channel], ["#lnkGithub", links.github]].forEach(function (x) {
      var n = $(x[0]); if (!n) return;
      if (x[1]) { n.href = x[1]; n.hidden = false; n.onclick = function (ev) { ev.preventDefault(); if (/^https?:\/\/t\.me\//.test(x[1])) openTgLink(x[1]); else openOutside(x[1]); }; } else n.hidden = true;
    });

    var open = isOpen(d), pan = d.panel;
    show("#panelLocked", !open); show("#panelEmpty", open && !pan); show("#panelCard", open && !!pan);
    if (pan) {
      txt("#panelHost", pan.host); txt("#panelUuid", pan.uuid);
      txt("#panelCount", digits((pan.endpoints || []).length)); txt("#panelSynced", ago(pan.syncedAt || pan.updatedAt));
      show("#gwNote", !!pan.gateway);
      var h = $("#panelHealth"); if (h) { h.textContent = pan.healthy ? T("healthy") : T("unhealthy"); h.className = "pill " + (pan.healthy ? "good" : "warn"); }
      showSub(state.fmt);
      var list = $("#configList"); if (list) { list.innerHTML = ""; (pan.vless || []).concat(pan.trojan || [], pan.ss || []).forEach(function (l) { list.appendChild(copyRow(l)); }); }
      txt("#aiRelay", pan.aiRelay || T("ai.none")); txt("#aiFlag", pan.aiCountry || "—");
    } else { txt("#aiRelay", T("ai.none")); txt("#aiFlag", "—"); }

    var f = d.free || {};
    if (f.sub) { show("#freeSubBox", true); var fs = $("#freeSub"); if (fs && fs.textContent === "—") fs.textContent = f.sub; }

    var r = d.referral || {};
    show("#inviteCard", !!(r.enabled || r.link));
    txt("#inviteCount", digits(r.invited || 0)); txt("#inviteGoal", digits(r.required || 0)); txt("#inviteLink", r.link || "—");
    var bar = $("#inviteBar"); if (bar) bar.style.width = (r.required ? Math.min(100, Math.round((r.invited || 0) / r.required * 100)) : 100) + "%";
    show("#adminCard", !!(d.user && d.user.isAdmin));
  }
  function subUrl(f) { var p = state.data && state.data.panel; if (!p) return ""; var l = p.links || {}, d = p.direct || {}; return l[f] || d[f] || (f === "sub" ? (d.sub || "") : ""); }
  function showSub(f) { state.fmt = f; txt("#subLink", subUrl(f) || T("none")); var q = $("#qrImg"); if (q) q.removeAttribute("src"); $$("#subFormats .seg-btn").forEach(function (b) { b.classList.toggle("active", b.dataset.fmt === f); }); }

  // ------------------------------------------------------------ actions
  async function load(quiet) {
    try {
      var d = await call("/api/state", {});
      var f = $("#fatal"); if (f) f.remove();
      if (!quiet) { applyLang(d.user && d.user.lang); applyTheme((d.user && d.user.theme) || "auto"); }
      render(d); document.body.classList.remove("booting"); dock.place(); return d;
    } catch (e) {
      document.body.classList.remove("booting");
      if (!quiet) fatal(e.message === "noapi" ? "noapi" : "network", explain(e)); else toast(explain(e), "bad");
      return null;
    }
  }
  async function payWith(g) {
    busy(true);
    try {
      var d = await call("/api/pay/start", { gateway: g }); busy(false);
      if (g === "stars" && tg && tg.openInvoice) { tg.openInvoice(d.url, function (s) { if (s === "paid") { notify("success"); toast(T("pay.done"), "ok"); pollPaid(10); } }); return; }
      if (g === "stars") { openTgLink(d.url); pollPaid(40); return; }
      openOutside(d.url); toast(T("pay.opened")); pollPaid(40);
    } catch (e) { busy(false); toast(explain(e), "bad"); }
  }
  async function pollPaid(n) { for (var i = 0; i < n; i++) { await sleep(3000); var d = await load(true); if (d && d.payment && d.payment.paid) { toast(T("pay.done"), "ok"); return true; } } return false; }
  async function checkPaid() { busy(true); var d = await load(true); busy(false); if (d && d.payment && d.payment.paid) toast(T("pay.done"), "ok"); else toast(T("pay.pending")); }

  function renderSteps(names, step, failed) {
    var ol = $("#steps"); if (!ol) return; ol.hidden = false; ol.innerHTML = "";
    var labels = T("steps"); if (!Array.isArray(labels)) labels = names || [];
    (names && names.length ? names : labels).forEach(function (_, i) {
      var li = el("li", i < step ? "done" : (i === step ? (failed ? "fail" : "run") : ""), (i < step ? "✅ " : i === step ? (failed ? "❌ " : "⏳ ") : "• ") + (labels[i] || names[i]));
      ol.appendChild(li);
    });
  }
  async function runBuild(body) {
    busy(true, T("building"));
    try {
      var start = await call("/api/panel/build", body);
      var names = start.steps || [];
      renderSteps(names, 0, false);
      for (var i = 0; i < 120; i++) {
        await sleep(2000);
        var j = (await call("/api/job/" + encodeURIComponent(start.job), null, "GET")).job || {};
        renderSteps(names, j.step || 0, j.state === "failed");
        if (j.state === "done") { notify("success"); toast(T("done"), "ok"); await load(true); go("panel"); return; }
        if (j.state === "failed") throw ApiError(j.error || "build failed", 0, j);
      }
      throw ApiError("timeout", 0, null);
    } catch (e) { notify("error"); toast(explain(e), "bad"); }
    finally { busy(false); }
  }
  function buildPanel() { var t = ($("#tokenInput") || {}).value; t = (t || "").trim(); if (!t) { toast(T("token")); return; } runBuild({ token: t, mode: "build" }); }
  function rebuildPanel() { runBuild({ mode: "rebuild" }); }
  async function applyPanel() { busy(true); try { await call("/api/panel/apply", {}); notify("success"); toast(T("done"), "ok"); await load(true); } catch (e) { toast(explain(e), "bad"); } finally { busy(false); } }
  async function pingPanel() {
    busy(true);
    try {
      var d = await call("/api/panel/ping", {}), box = $("#pingRows"); if (!box) return; box.innerHTML = "";
      (d.rows || []).forEach(function (r) { var row = el("div", "rowitem"); row.appendChild(el("code", "", r.ip + ":" + r.port)); row.appendChild(el("b", r.latency ? "good" : "bad", r.latency ? digits(Math.round(r.latency)) + "ms" : "✕")); box.appendChild(row); });
    } catch (e) { toast(explain(e), "bad"); } finally { busy(false); }
  }
  async function exportFile(fmt) { busy(true); try { var d = await call("/api/panel/export", { format: fmt }); busy(false); save(d.url, d.filename, d.body); } catch (e) { busy(false); toast(explain(e), "bad"); } }
  async function deletePanel() {
    var ask = function (cb) { try { if (tg && tg.showConfirm) { tg.showConfirm(T("confirmDelete"), cb); return; } } catch (e) {} cb(window.confirm(T("confirmDelete"))); };
    ask(async function (yes) { if (!yes) return; busy(true); try { await call("/api/panel/delete", {}); toast(T("done"), "ok"); await load(true); } catch (e) { toast(explain(e), "bad"); } finally { busy(false); } });
  }
  async function buildWarp() {
    busy(true);
    try {
      var w = state.warp = await call("/api/warp/build", { platform: state.platform, family: state.family });
      show("#wgResult", true);
      txt("#wgConf", w.conf || ""); txt("#wgEndpoint", w.endpoint || "—");
      txt("#wgMode", w.clean ? T("warp.clean") : T("warp.amnezia"));
      txt("#wgRoutes", Array.isArray(w.routes) ? w.routes.join(", ") : (w.routes || "—"));
      var apple = !!(APPLE[state.platform] && w.awg);
      show("#wgApple", apple); show("#wgPlainTitle", apple);
      var a = $("#wgAwgQrImg"); if (a) a.removeAttribute("src");
      var q = $("#wgQrImg"); if (q) q.removeAttribute("src");
      notify("success");
    } catch (e) { toast(explain(e), "bad"); } finally { busy(false); }
  }
  async function buildFree() {
    busy(true);
    try {
      var d = await call("/api/free/build", { protocol: state.proto });
      txt("#freeSub", d.sub); show("#freeSubBox", true);
      txt("#freeMeta", d.best ? (digits(d.count || 0) + " · " + digits(Math.round(d.best)) + "ms") : "");
      var list = $("#freeList"); if (list) { list.innerHTML = ""; (d.links || []).forEach(function (x) { list.appendChild(copyRow(x)); }); }
    } catch (e) { toast(explain(e), "bad"); } finally { busy(false); }
  }
  function shareInvite() {
    var r = (state.data && state.data.referral) || {}; if (!r.link) return;
    var text = state.lang === "fa" ? "تونل اختصاصی و رایگان 🚀" : "Your own free tunnel 🚀";
    openTgLink("https://t.me/share/url?url=" + encodeURIComponent(r.link) + "&text=" + encodeURIComponent(text));
  }

  // ------------------------------------------------------------ admin
  var FLAG_LABEL = { maintenance: "🚧 تعمیرات", builds_enabled: "🏗 ساخت پنل", force_join: "📣 عضویت اجباری", warp_enabled: "🌀 وارپ", support_enabled: "💬 پشتیبانی", autopilot: "🤖 اتوپایلوت", curator: "🧹 کیوریتور", referral_lock: "🔐 قفل دعوت", free_enabled: "🎁 رایگان", miniapp_enabled: "📱 مینی‌اپ" };
  async function loadAdmin() {
    try { state.admin = await call("/api/admin/state", {}); renderAdmin(state.admin); } catch (e) { toast(explain(e), "bad"); }
  }
  function renderAdmin(a) {
    var st = $("#adminStats");
    if (st) {
      st.innerHTML = ""; var g = a.stats || {}, ai = a.ai || {}, pins = ai.pins || {};
      [[T("admin.users"), g.users], [T("admin.panels"), g.panels], [T("admin.subs"), (a.payment && a.payment.stats && a.payment.stats.active)], [T("admin.pins"), pins.total !== undefined ? pins.total : pins.count]].forEach(function (x) {
        var c = el("div", "card stat"); c.appendChild(el("span", "", x[0])); c.appendChild(el("b", "", digits(x[1] === undefined || x[1] === null ? "—" : x[1]))); st.appendChild(c);
      });
    }
    var fl = $("#adminFlags");
    if (fl) {
      fl.innerHTML = "";
      Object.keys(a.flags || {}).forEach(function (k) {
        var row = el("div", "rowitem"); row.appendChild(el("span", "", FLAG_LABEL[k] || k));
        var b = el("button", "btn tiny " + (a.flags[k] ? "primary" : "ghost"), a.flags[k] ? T("on") : T("off")); b.type = "button";
        b.onclick = async function () { try { var r = await call("/api/admin/flag", { key: k }); a.flags[k] = r.value; renderAdmin(a); } catch (e) { toast(explain(e), "bad"); } };
        row.appendChild(b); fl.appendChild(row);
      });
    }
    var rr = $("#refRequired"); if (rr && a.referral) rr.value = a.referral.required !== undefined ? a.referral.required : "";
    renderAdminPay((a.payment || {}).config || {}, (a.payment || {}).callback);
    renderAdminFree(a.free && a.free.servers ? a.free.servers : null);
  }
  function renderAdminPay(cfg, callback) {
    var box = $("#adminPay"); if (!box) return; box.innerHTML = "";
    function toggleRow(label, key, val) { var row = el("div", "rowitem"); row.appendChild(el("span", "", label)); var b = el("button", "btn tiny " + (val ? "primary" : "ghost"), val ? T("on") : T("off")); b.type = "button"; b.onclick = function () { setPay(key, !val); }; row.appendChild(b); box.appendChild(row); }
    function inputRow(label, key, val, type) { var row = el("div", "row gap"); var i = el("input", "input"); i.type = type || "number"; i.value = val === undefined || val === null ? "" : val; i.placeholder = label; var b = el("button", "btn tiny", T("save")); b.type = "button"; b.onclick = function () { setPay(key, i.value); }; var lab = el("label", "label", label); box.appendChild(lab); row.appendChild(i); row.appendChild(b); box.appendChild(row); }
    toggleRow(T("admin.payOn"), "enabled", !!cfg.enabled);
    toggleRow(T("admin.sandbox"), "sandbox", !!cfg.sandbox);
    inputRow(T("admin.gateway") + " (zarinpal / stars / both)", "gateway", cfg.gateway, "text");
    inputRow(T("admin.amount"), "amount", cfg.amount);
    inputRow(T("admin.starsPrice"), "stars", cfg.stars);
    inputRow(T("admin.days"), "days", cfg.days);
    inputRow(T("admin.merchant") + (cfg.merchant ? " ✅" : ""), "merchant", "", "text");
    if (callback) { var kv = el("div", "kv"); kv.appendChild(el("span", "", T("admin.callback"))); kv.appendChild(el("code", "", callback)); box.appendChild(kv); }
  }
  async function setPay(key, value) { try { var r = await call("/api/admin/pay", { action: "set", key: key, value: value }); toast(T("done"), "ok"); if (state.admin) { state.admin.payment = { config: r.config, stats: r.stats, callback: r.callback }; renderAdminPay(r.config || {}, r.callback); } } catch (e) { toast(explain(e), "bad"); } }
  function renderAdminFree(servers) {
    var box = $("#adminFree"); if (!box || !servers) return; box.innerHTML = "";
    servers.forEach(function (s) {
      var row = el("div", "rowitem"); row.appendChild(el("code", "", (s.healthy ? "🟢 " : "🔴 ") + (s.host || s.id)));
      var t = el("button", "btn tiny", s.active ? T("on") : T("off")); t.type = "button"; t.onclick = function () { adminFree({ action: "toggle", id: s.id }); };
      var d = el("button", "btn tiny danger", "🗑"); d.type = "button"; d.onclick = function () { adminFree({ action: "delete", id: s.id }); };
      row.appendChild(t); row.appendChild(d); box.appendChild(row);
    });
  }
  async function adminFree(body) { busy(true); try { var r = await call("/api/admin/free", body); if (r.servers) renderAdminFree(r.servers); else if (body.action === "check") toast(digits(r.healthy) + "/" + digits(r.total) + " " + T("healthy"), "ok"); else { toast(T("done"), "ok"); var l = await call("/api/admin/free", { action: "list" }); renderAdminFree(l.servers); } } catch (e) { toast(explain(e), "bad"); } finally { busy(false); } }

  // ------------------------------------------------------------ wiring
  function seg(sel, attr, fn) { $$(sel + " .seg-btn").forEach(function (b) { b.onclick = function () { $$(sel + " .seg-btn").forEach(function (x) { x.classList.toggle("active", x === b); }); fn(b.dataset[attr]); }; }); }
  function bind() {
    $$("[data-go]").forEach(function (b) { b.onclick = function () { go(b.dataset.go); }; });
    $$("[data-copy]").forEach(function (b) { b.onclick = function () { var n = $(b.dataset.copy); if (n && n.textContent !== "—") copy(n.textContent); }; });
    on("#veilCancel", function () { busy(false); });
    on("#refreshBtn", function () { haptic(); load(true).then(function (d) { if (d) toast(T("done"), "ok"); }); });
    on("#langBtn", function () { var l = state.lang === "fa" ? "en" : "fa"; applyLang(l); persist({ lang: l }); });
    on("#themeBtn", function () { var t = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light"; applyTheme(t); persist({ theme: t }); });
    $$("#setLang .seg-btn").forEach(function (b) { b.onclick = function () { applyLang(b.dataset.lang); persist({ lang: b.dataset.lang }); }; });
    $$("#setTheme .seg-btn").forEach(function (b) { b.onclick = function () { applyTheme(b.dataset.theme); persist({ theme: b.dataset.theme }); }; });

    on("#payZp", function () { payWith("zarinpal"); });
    on("#payStars", function () { payWith("stars"); });
    on("#payCheck", checkPaid);

    $$("#subFormats .seg-btn").forEach(function (b) { b.onclick = function () { showSub(b.dataset.fmt); }; });
    on("#subOpen", function () { openOutside(subUrl(state.fmt)); });
    on("#subQr", function () { var u = subUrl(state.fmt); if (u) $("#qrImg").src = qrSrc(u); });
    on("#buildBtn", buildPanel);
    on("#applyBtn", applyPanel);
    on("#pingBtn", pingPanel);
    on("#rebuildBtn", rebuildPanel);
    on("#fragBtn", function () { exportFile("fragment"); });
    on("#noiseBtn", function () { exportFile("noise"); });
    on("#clashBtn", function () { exportFile("clash"); });
    on("#deleteBtn", deletePanel);

    seg("#wgPlatform", "platform", function (v) { state.platform = v; });
    seg("#wgFamily", "family", function (v) { state.family = v; });
    on("#wgBuild", buildWarp);
    on("#wgDownload", function () { if (state.warp) save(state.warp.url, state.warp.filename || "warp.conf", state.warp.conf); });
    on("#wgCopyConf", function () { if (state.warp) copy(state.warp.conf); });
    on("#wgCopyLink", function () { if (state.warp) copy(state.warp.link || state.warp.hiddify || ""); });
    on("#wgQr", function () { if (state.warp) $("#wgQrImg").src = state.warp.qr || qrSrc(state.warp.conf); });
    on("#wgAwgDownload", function () { if (state.warp) save(state.warp.awgUrl, state.warp.awgFilename || "warp-awg.conf", state.warp.awg); });
    on("#wgAwgQr", function () { if (state.warp) $("#wgAwgQrImg").src = state.warp.awgQr || qrSrc(state.warp.awg); });
    on("#wgAwgStore", function () { openOutside("https://apps.apple.com/app/amneziawg/id6478942365"); });
    on("#wgHiddify", function () { if (state.warp) copy(state.warp.hiddify || ""); });

    seg("#freeProto", "proto", function (v) { state.proto = v; });
    on("#freeBtn", buildFree);
    on("#inviteShare", shareInvite);

    on("#refSave", async function () { try { await call("/api/admin/referral", { required: $("#refRequired").value }); toast(T("done"), "ok"); } catch (e) { toast(explain(e), "bad"); } });
    on("#freeAdd", function () { var v = ($("#freeServer") || {}).value; if (v) adminFree({ action: "add", value: v }); });
    on("#freePanelBtn", function () { adminFree({ action: "panel" }); });
    on("#freeCheck", function () { adminFree({ action: "check" }); });
    on("#geoBtn", async function () { busy(true); try { await call("/api/admin/ai", { action: "geo" }); toast(T("done"), "ok"); } catch (e) { toast(explain(e), "bad"); } finally { busy(false); } });

    try { if (tg && tg.BackButton) tg.BackButton.onClick(function () { go("home"); }); } catch (e) {}
    window.addEventListener("message", function (ev) { try { var m = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data; if (m && m.eventType === "back_button_pressed") go("home"); if (m && m.eventType === "theme_changed" && state.theme === "auto") applyTheme("auto"); } catch (e) {} });
    window.Telegram = window.Telegram || {};
    window.Telegram.WebView = window.Telegram.WebView || {};
    var prev = window.Telegram.WebView.receiveEvent;
    window.Telegram.WebView.receiveEvent = function (name, data) { if (name === "back_button_pressed") go("home"); if (typeof prev === "function") try { prev(name, data); } catch (e) {} };
  }

  // ------------------------------------------------------------ boot
  // telegram-web-app.js is loaded async (a filtered telegram.org must never
  // block first paint). Give it a moment, then carry on with or without it.
  function waitForTelegram(cb) {
    var waited = 0;
    (function poll() {
      if (window.Telegram && window.Telegram.WebApp) { tg = window.Telegram.WebApp; cb(); return; }
      if (waited >= 1500) { cb(); return; }
      waited += 100; setTimeout(poll, 100);
    })();
  }
  function boot() { waitForTelegram(start); }
  function start() {
    tgReady();
    try { bind(); dock.bind(); } catch (e) { if (window.console) console.error("bind failed", e); }
    applyLang(initUserLang()); applyTheme("auto");
    if (!initData()) { fatal("outside"); return; }
    if (API_MISSING) { fatal("noapi"); return; }
    load();
  }
  window.addEventListener("error", function (ev) { if (document.body.classList.contains("booting")) fatal("network", String(ev.message || "script error")); });
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
