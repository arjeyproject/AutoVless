/* AutoVless Mini App.
 *
 * Everything here talks to the bot's own API. The only credential is the signed
 * initData Telegram hands the page on launch: it goes out in the X-Init-Data
 * header and the server verifies the HMAC, so there is no token, no session and
 * nothing worth stealing in this file.
 *
 * The app is normally served by that same server, which keeps it same-origin. If
 * it is hosted somewhere else (GitHub Pages, for instance) set window.AUTOVLESS_API
 * or pass ?api=https://host to point it back.
 */
(function () {
  "use strict";

  var tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  var params = new URLSearchParams(location.search);
  var API =
    (params.get("api") || window.AUTOVLESS_API || location.origin).replace(/\/+$/, "");
  var INIT = tg ? tg.initData || "" : "";

  var state = { lang: "fa", theme: "dark", data: null, fmt: "sub", proto: "vless",
                platform: "ios", family: "v4", warp: null, free: null };

  /* --------------------------------------------------------------- i18n */
  var STR = {
    fa: {
      tagline: "تونل اختصاصی خودت",
      loading: "در حال بارگذاری…",
      "home.title": "شبکه‌ی تو، همیشه تازه",
      "home.text": "آی‌پی‌های تمیز به‌صورت خودکار اسکن، تست و روی کانفیگ‌های تو اعمال می‌شوند.",
      "home.cta": "پنل توربو", "home.cta2": "کانفیگ رایگان",
      "stat.pool": "استخر آی‌پی", "stat.verified": "تاییدشده", "stat.relays": "رله", "stat.warp": "وارپ",
      "ai.title": "🧠 مسیر هوش مصنوعی",
      "ai.text": "جیمینای، ChatGPT و کلاد از یک آی‌پی ثابت خارج می‌شوند تا حلقه‌ی لاگین و ارور ریجن پیش نیاید.",
      "ai.relay": "رله‌ی پین‌شده",
      "link.support": "پشتیبانی", "link.channel": "کانال", "link.github": "گیت‌هاب",
      "panel.buildTitle": "ساخت پنل توربو",
      "panel.buildText": "توکن Cloudflare خودت را بده؛ ورکر، یوزر و کانفیگ‌ها روی اکانت خودت ساخته می‌شوند.",
      "panel.tokenHelp": "ساخت توکن در داشبورد کلادفلر ↗",
      "panel.build": "ساخت پنل", "panel.title": "پنل توربو", "panel.host": "هاست",
      "panel.uuid": "شناسه", "panel.count": "کانفیگ‌ها", "panel.synced": "آخرین اعمال",
      "panel.mix": "هر دو", "panel.apply": "⚡️ اعمال آی‌پی تازه", "panel.ping": "📶 پینگ",
      "panel.rebuild": "🔄 بازسازی", "panel.fragment": "🧩 فرگمنت", "panel.delete": "🗑 حذف پنل",
      "panel.configs": "کانفیگ‌های تک",
      "warp.title": "وایرگارد / وارپ",
      "warp.text": "اکانت وارپ واقعی روی نام تو ساخته می‌شود و اندپوینت از استخر تست‌شده انتخاب می‌شود.",
      "warp.device": "دستگاه", "warp.network": "شبکه",
      "warp.v4": "همه اپراتورها (IPv4)", "warp.v6": "ایرانسل (IPv6)",
      "warp.build": "ساخت کانفیگ", "warp.endpoint": "اندپوینت", "warp.mode": "حالت",
      "warp.download": "⬇️ فایل .conf", "warp.copylink": "🔗 لینک wireguard",
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
      noPanel: "هنوز پنلی نداری", locked: "برای استفاده باید دوستانت را دعوت کنی",
      quota: "سهمیه‌ی رایگانت تمام شده", none: "چیزی پیدا نشد",
      steps: ["بررسی توکن", "زیر‌دامنه", "انتخاب آی‌پی تمیز", "آپلود ورکر", "تست سلامت"],
      confirmDelete: "پنل و ورکرش حذف شود؟"
    },
    en: {
      tagline: "your own tunnel",
      loading: "Loading…",
      "home.title": "Your network, always fresh",
      "home.text": "Clean IPs are scanned, tested and applied to your configs automatically.",
      "home.cta": "Turbo panel", "home.cta2": "Free config",
      "stat.pool": "IP pool", "stat.verified": "Verified", "stat.relays": "Relays", "stat.warp": "WARP",
      "ai.title": "🧠 AI route",
      "ai.text": "Gemini, ChatGPT and Claude all leave through one steady IP, so no login loop and no region error.",
      "ai.relay": "Pinned relay",
      "link.support": "Support", "link.channel": "Channel", "link.github": "GitHub",
      "panel.buildTitle": "Build your turbo panel",
      "panel.buildText": "Paste your Cloudflare token. The worker, the uuid and the configs are created on your own account.",
      "panel.tokenHelp": "Create a token in the Cloudflare dashboard ↗",
      "panel.build": "Build panel", "panel.title": "Turbo panel", "panel.host": "Host",
      "panel.uuid": "UUID", "panel.count": "Configs", "panel.synced": "Last apply",
      "panel.mix": "Both", "panel.apply": "⚡️ Apply fresh IPs", "panel.ping": "📶 Ping",
      "panel.rebuild": "🔄 Rebuild", "panel.fragment": "🧩 Fragment", "panel.delete": "🗑 Delete panel",
      "panel.configs": "Single configs",
      "warp.title": "WireGuard / WARP",
      "warp.text": "A real WARP account is registered for you and the endpoint comes from the tested pool.",
      "warp.device": "Device", "warp.network": "Network",
      "warp.v4": "Every carrier (IPv4)", "warp.v6": "Irancell (IPv6)",
      "warp.build": "Build config", "warp.endpoint": "Endpoint", "warp.mode": "Mode",
      "warp.download": "⬇️ .conf file", "warp.copylink": "🔗 wireguard link",
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
      noPanel: "No panel yet", locked: "Invite your friends to unlock",
      quota: "Your free quota is used up", none: "Nothing found",
      steps: ["Verify token", "Subdomain", "Pick clean IPs", "Upload worker", "Health check"],
      confirmDelete: "Delete the panel and its worker?"
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
    toast._t = setTimeout(function () { el.classList.remove("show"); }, 2600);
  }

  function busy(on) { $("#veil").hidden = !on; }

  function haptic(kind) {
    try { tg.HapticFeedback.impactOccurred(kind || "light"); } catch (e) { /* not everywhere */ }
  }

  function copy(text) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(T("copied")); });
    } else {
      var box = document.createElement("textarea");
      box.value = text; document.body.appendChild(box); box.select();
      try { document.execCommand("copy"); toast(T("copied")); } catch (e) { /* ignore */ }
      box.remove();
    }
    haptic("light");
  }

  function ago(ts) {
    if (!ts) return "—";
    var diff = Math.max(0, Math.floor(Date.now() / 1000) - ts);
    if (diff < 90) return state.lang === "fa" ? "همین حالا" : "just now";
    if (diff < 3600) return Math.floor(diff / 60) + (state.lang === "fa" ? " دقیقه پیش" : "m ago");
    if (diff < 86400) return Math.floor(diff / 3600) + (state.lang === "fa" ? " ساعت پیش" : "h ago");
    return Math.floor(diff / 86400) + (state.lang === "fa" ? " روز پیش" : "d ago");
  }

  async function call(path, body, method) {
    var response = await fetch(API + path, {
      method: method || "POST",
      headers: { "content-type": "application/json", "x-init-data": INIT },
      body: method === "GET" ? undefined : JSON.stringify(body || {})
    });
    var payload = null;
    try { payload = await response.json(); } catch (e) { payload = null; }
    if (!response.ok || !payload || payload.ok === false) {
      var reason = (payload && payload.error) || response.status;
      throw new Error(reason);
    }
    return payload;
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
    positionDrop(true);
  }

  /* ----------------------------------------------------- the water drop */
  function positionDrop(instant) {
    var active = $(".dock-btn.active");
    var drop = $("#drop");
    if (!active || !drop) return;
    var dock = $("#dock").getBoundingClientRect();
    var box = active.getBoundingClientRect();
    var centre = box.left + box.width / 2 - dock.left;
    var offset = centre - drop.offsetWidth / 2;
    if (!instant) {
      drop.classList.add("moving");
      setTimeout(function () { drop.classList.remove("moving"); }, 560);
    }
    drop.style.transform = "translateX(" + offset + "px)";
  }

  function go(tab) {
    $$(".dock-btn").forEach(function (b) { b.classList.toggle("active", b.dataset.tab === tab); });
    $$(".view").forEach(function (v) { v.classList.toggle("active", v.dataset.view === tab); });
    positionDrop(false);
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
      var health = $("#panelHealth");
      health.textContent = panel.healthy ? T("healthy") : T("unhealthy");
      health.className = "pill" + (panel.healthy ? "" : " ghost");
      showSub(state.fmt);
      var list = $("#configList");
      list.innerHTML = "";
      (panel.vless || []).concat(panel.trojan || []).forEach(function (link) {
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

    var ref = data.referral || {};
    $("#inviteCount").textContent = ref.invited || 0;
    $("#inviteGoal").textContent = ref.required || 0;
    $("#inviteLink").textContent = ref.link || "—";
    var pct = ref.required ? Math.min(100, Math.round((ref.invited / ref.required) * 100)) : 100;
    $("#inviteBar").style.width = pct + "%";

    $("#adminCard").hidden = !data.user.isAdmin;
    applyThemeButtons(data.user);
  }

  function applyThemeButtons(user) {
    $$("#setLang .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.lang === state.lang);
    });
    if (user && user.theme) {
      $$("#setTheme .seg-btn").forEach(function (b) {
        b.classList.toggle("active", b.dataset.theme === state.theme);
      });
    }
  }

  function showSub(fmt) {
    state.fmt = fmt;
    var panel = state.data && state.data.panel;
    if (!panel) return;
    var url = panel.links[fmt] || panel.links.sub;
    $("#subLink").textContent = url;
    $("#qrImg").src = API + "/api/qr?text=" + encodeURIComponent(url);
    $$("#subFormats .seg-btn").forEach(function (b) {
      b.classList.toggle("active", b.dataset.fmt === fmt);
    });
  }

  /* ---------------------------------------------------------------- boot */
  async function load() {
    try {
      var data = await call("/api/state", {});
      applyLang(data.user.lang);
      applyTheme(data.user.theme || "auto");
      render(data);
      if (data.referral && data.referral.enabled && !data.referral.unlocked) {
        toast(T("locked"));
        go("more");
      }
    } catch (error) {
      toast(T("failed") + error.message);
      $("#heroState").textContent = "offline";
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
    for (var attempt = 0; attempt < 90; attempt++) {
      await new Promise(function (r) { setTimeout(r, 2000); });
      var payload;
      try { payload = await call("/api/job/" + job, null, "GET"); } catch (e) { continue; }
      var info = payload.job || {};
      drawSteps(info.step || 0);
      if (info.state === "done") return info.result;
      if (info.state === "failed") throw new Error(info.error || "build failed");
    }
    throw new Error("timeout");
  }

  async function buildPanel(mode) {
    var token = $("#tokenInput").value.trim();
    if (!token && mode !== "rebuild") { toast("token?"); return; }
    busy(true);
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
      toast(T("failed") + error.message);
    } finally {
      busy(false);
    }
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
          try { await call("/api/admin/flag", { key: key }); loadAdmin(); } catch (e) { toast(e.message); }
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
          catch (e) { toast(e.message); }
        };
        var kill = document.createElement("button");
        kill.className = "btn tiny danger";
        kill.textContent = "🗑";
        kill.onclick = async function () {
          try { await call("/api/admin/free", { action: "delete", id: server.id }); loadAdmin(); }
          catch (e) { toast(e.message); }
        };
        row.appendChild(code); row.appendChild(toggle); row.appendChild(kill);
        free.appendChild(row);
      });
    } catch (error) {
      toast(T("failed") + error.message);
    }
  }

  /* --------------------------------------------------------------- events */
  function bind() {
    $$(".dock-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { go(btn.dataset.tab); });
    });
    $$("[data-go]").forEach(function (btn) {
      btn.addEventListener("click", function () { go(btn.dataset.go); });
    });
    $$("[data-copy]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = $(btn.dataset.copy);
        copy(target ? target.textContent : "");
      });
    });

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

    $("#buildBtn").addEventListener("click", function () { buildPanel("build"); });
    $("#rebuildBtn").addEventListener("click", function () { buildPanel("rebuild"); });

    $("#applyBtn").addEventListener("click", async function () {
      busy(true);
      try {
        await call("/api/panel/apply", {});
        toast(T("done"));
        await load();
      } catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
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
          item.innerHTML = "<code>" + row.ip + ":" + row.port + "</code><b class='" +
            (row.latency ? "ok" : "bad") + "'>" + (row.latency ? Math.round(row.latency) + "ms" : "✕") + "</b>";
          box.appendChild(item);
        });
      } catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
    });

    $("#fragBtn").addEventListener("click", async function () {
      busy(true);
      try {
        var data = await call("/api/panel/export", { format: "fragment" });
        download(data.filename, data.body);
      } catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
    });

    $("#deleteBtn").addEventListener("click", function () {
      var run = async function () {
        busy(true);
        try { await call("/api/panel/delete", {}); toast(T("done")); await load(); }
        catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
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
        $("#wgConf").textContent = data.conf || "";
        haptic("medium");
      } catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
    });

    $("#wgDownload").addEventListener("click", function () {
      if (state.warp) download(state.warp.filename || "warp.conf", state.warp.conf || "");
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
        toast(error.message === "quota" ? T("quota") : T("failed") + error.message);
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
      } catch (error) { toast(T("failed") + error.message); }
    });
    $("#freeAdd").addEventListener("click", async function () {
      try {
        await call("/api/admin/free", { action: "add", value: $("#freeServer").value.trim() });
        $("#freeServer").value = "";
        toast(T("done"));
        loadAdmin();
      } catch (error) { toast(T("failed") + error.message); }
    });
    $("#freePanelBtn").addEventListener("click", async function () {
      try { await call("/api/admin/free", { action: "panel" }); toast(T("done")); loadAdmin(); }
      catch (error) { toast(T("failed") + error.message); }
    });
    $("#freeCheck").addEventListener("click", async function () {
      busy(true);
      try {
        var data = await call("/api/admin/free", { action: "check" });
        toast(data.healthy + " / " + data.total);
      } catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
    });
    $("#geoBtn").addEventListener("click", async function () {
      busy(true);
      try { await call("/api/admin/ai", { action: "geo" }); toast(T("done")); loadAdmin(); }
      catch (error) { toast(T("failed") + error.message); } finally { busy(false); }
    });

    window.addEventListener("resize", function () { positionDrop(true); });
  }

  function download(name, body) {
    var blob = new Blob([body], { type: "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url; a.download = name || "autovless.txt";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  /* ---------------------------------------------------------------- start */
  if (tg) {
    try { tg.ready(); tg.expand(); } catch (e) { /* older clients */ }
    try { tg.setHeaderColor("secondary_bg_color"); } catch (e) { /* optional */ }
    if (tg.onEvent) tg.onEvent("themeChanged", function () { if (state.theme === "auto") applyTheme("auto"); });
  }
  bind();
  applyLang((tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.language_code === "en") ? "en" : "fa");
  applyTheme("auto");
  setTimeout(function () { positionDrop(true); }, 60);
  if (!INIT) {
    toast(state.lang === "fa" ? "این صفحه را از داخل تلگرام باز کن" : "Open this page from inside Telegram");
  } else {
    load();
  }
})();
