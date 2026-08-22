"""WARP and WireGuard copy, kept apart from the rest of the catalogue.

The scan messages are deliberately one short block each. A user who pressed a
button wants to know whether it worked, not to read an essay about UDP.
"""

WARP: dict[str, dict[str, str]] = {
    "fa": {
        # ----------------------------------------------------------- buttons
        "btn.warp_build": "⚡ ساخت خودکار وارپ",
        "btn.warp_rebuild": "♻️ به‌روزرسانی اندپوینت‌ها",
        "btn.warp_awg": "🛡 AmneziaWG (پیشنهاد اول)",
        "btn.warp_awg2": "🧬 AmneziaWG نسخه ۲",
        "btn.warp_plain": "📄 وایرگارد ساده",
        "btn.warp_link": "🔗 لینک v2rayNG و Hiddify",
        "btn.warp_singbox": "📦 خروجی sing-box",
        "btn.warp_clash": "🧩 خروجی Clash",
        "btn.warp_eps": "📡 اندپوینت‌های سالم",
        "btn.warp_rescan": "⚡ اسکن فوری اندپوینت",
        "btn.warp_license": "💎 ثبت لایسنس WARP+",
        "btn.warp_delete": "🗑 حذف هویت وارپ",
        "btn.warp_apps": "📱 برنامه‌های سازگار",
        "btn.warp_why": "🧠 چرا AmneziaWG؟",
        # -------------------------------------------------------------- menu
        "warp.menu": "🛡 <b>وارپ و وایرگارد</b>\n{rule}\nموتور من مدام اندپوینت‌های کلادفلر را با <b>هندشیک واقعی</b> تست می‌کند و پینگ، جیتر و افت بسته هر کدام را می‌سنجد. هر اندپوینتی که فیلتر شود در چند دقیقه از استخر بیرون می‌رود.\n\n📡 پایدار: <b>{stable}</b> از <b>{total}</b>\n🏆 بهترین پینگ: <b>{best}</b>\n🔌 پورت‌های باز: <b>{ports}</b>\n⏳ آخرین اسکن: <b>{updated}</b>\n⚙️ در حال اسکن: <b>{state}</b>\n{rule}\n{status}",
        "warp.status_none": "🔓 هنوز هویت وارپ نساخته‌ای. دکمه ساخت خودکار را بزن؛ کمتر از ۱۰ ثانیه کار دارد.",
        "warp.status_ready": "✅ <b>هویت وارپ تو آماده است</b>\n💎 اکانت: <b>{account}</b>\n📡 اندپوینت: <code>{endpoint}</code>\n🔢 داخل کانفیگ: <b>{count}</b>\n🕒 به‌روزرسانی: <b>{updated}</b>",
        "warp.dpi_note": "🧠 <b>چرا AmneziaWG؟</b>\n{rule}\nوایرگارد ساده امضای ثابتی دارد و فیلترینگ ایران بلافاصله بعد از هندشیک آن را بلک‌هول می‌کند؛ یعنی وصل می‌شوی ولی چند ثانیه بعد هیچ بسته‌ای رد و بدل نمی‌شود.\n\nAmneziaWG قبل از هندشیک چند بسته پوششی می‌فرستد و اندازه و ترتیب بسته‌ها را به‌هم می‌ریزد، ولی هسته رمزنگاری دست‌نخورده می‌ماند. به همین دلیل همان سرور وارپ کلادفلر بدون هیچ تغییری آن را می‌پذیرد.\n\n🔒 پارامترهای پوششی برای هر کاربر یکتا ساخته می‌شود، پس یک قاعده DPI نمی‌تواند همه را با هم بگیرد.",
        # ------------------------------------------------------------- build
        "warp.building": "⚙️ دارم هویت تازه وارپ می‌سازم و سالم‌ترین اندپوینت‌ها را سوارش می‌کنم...",
        "warp.ready": "🎉 <b>وارپ تو آماده شد!</b>\n{rule}\n💎 اکانت: <b>{account}</b>\n📡 اندپوینت: <code>{endpoint}</code>\n🏆 پینگ: <b>{ping}</b>\n🔢 جایگزین: <b>{count}</b>\n🧬 آبفاسکیشن: <b>Jc={jc} · Jmin={jmin} · Jmax={jmax}</b>\n📶 MTU: <b>{mtu}</b>\n\n👇 خروجی مورد نظرت را بگیر. اگر نمی‌دانی کدام، همان AmneziaWG را بزن.",
        "warp.failed": "❌ ساخت هویت وارپ ناموفق بود: <code>{reason}</code>\nکمی بعد دوباره امتحان کن.",
        "warp.refreshed": "✅ اندپوینت عوض شد.\n📡 جدید: <code>{endpoint}</code> · {ping}\n\n⚠️ کانفیگ قبلی‌ات آدرس قدیمی را دارد؛ یک خروجی تازه بگیر.",
        "warp.refreshed_same": "✅ اندپوینت فعلی‌ات هنوز سالم است، پس دست‌نخورده ماند و فقط جایگزین‌ها تازه شدند.\n📡 <code>{endpoint}</code> · {ping}",
        "warp.none": "📭 هنوز هویت وارپی نداری. اول ساخت خودکار وارپ را بزن.",
        "warp.no_endpoint": "⏳ استخر فعلاً اندپوینت تاییدشده ندارد و از آدرس‌های پیش‌فرض استفاده کردم.\nیک اسکن فوری بزن یا چند دقیقه بعد به‌روزرسانی اندپوینت‌ها را امتحان کن.",
        # --------------------------------------------------------- endpoints
        "warp.eps": "📡 <b>اندپوینت‌های سالم</b>\n{rule}\n{list}\n\nℹ️ هر آدرس چند بار با هندشیک واقعی تست شده؛ ✅ یعنی پایدار و ⚪️ یعنی زیر نظر است.",
        "warp.eps_empty": "📭 استخر خالی است. یک اسکن فوری بزن.",
        "warp.loss": "افت {pct}٪",
        # ------------------------------------------------------------- scan
        "warp.rescanning": "⚡ اسکن شروع شد",
        "warp.rescan_started": "⚡ <b>اسکن اندپوینت</b>\nدارم آدرس‌ها را با هندشیک واقعی تست می‌کنم. نتیجه در همین پیام می‌آید و لازم نیست منتظر بمانی.",
        "warp.rescan_done": "✅ <b>اسکن تمام شد</b>\n📡 پایدار: <b>{count}</b>\n🔍 جواب دادند: <b>{alive}</b>\n🏆 بهترین: <b>{ping}</b>\n🔌 پورت: <b>{ports}</b>\n⏱ <b>{secs}</b> ثانیه",
        "warp.rescan_joined": "✅ <b>اسکن تمام شد</b> (به اسکنی که در جریان بود وصل شدی)\n📡 پایدار: <b>{count}</b>\n🏆 بهترین: <b>{ping}</b>\n🔌 پورت: <b>{ports}</b>",
        "warp.rescan_empty": "📭 این دور هیچ آدرس تازه‌ای جواب نداد. اندپوینت‌های قبلی سرجایشان هستند؛ چند دقیقه بعد دوباره بزن.",
        "warp.rescan_cooldown": "⏳ <b>{wait}</b> ثانیه دیگر می‌توانی اسکن بزنی.",
        "warp.rescan_failed": "❌ اسکن نیمه‌کاره ماند: <code>{reason}</code>\nچند دقیقه بعد دوباره امتحان کن.",
        "warp.rescan_wait": "⏳ یک اسکن در حال اجراست. کمی بعد دوباره بزن.",
        # ----------------------------------------------------------- license
        "warp.license_prompt": "💎 <b>لایسنس WARP+</b>\n{rule}\nکلید لایسنس (همان کد ۲۶ کاراکتری) را بفرست تا روی هویت تو اعمال شود و حجم WARP+ بگیری.\n✖️ برای لغو /cancel را بزن.",
        "warp.license_ok": "✅ لایسنس اعمال شد. اکانت: <b>{account}</b>\nیک خروجی تازه بگیر تا اعمال شود.",
        "warp.license_bad": "❌ کلادفلر این لایسنس را قبول نکرد: <code>{reason}</code>",
        # ------------------------------------------------------------ delete
        "warp.delete_confirm": "🗑 مطمئنی؟ هویت وارپ تو پاک می‌شود و کانفیگ‌های قبلی از کار می‌افتند.",
        "warp.deleted": "✅ هویت وارپ حذف شد.",
        # ----------------------------------------------------------- exports
        "warp.caption_awg": "🛡 <b>AmneziaWG</b> · پیشنهاد اول برای ایران\nفایل را در AmneziaVPN یا Hiddify یا WG Tunnel وارد کن. اگر برنامه فایل را قبول نکرد، از منوی Import و گزینه فایل کانفیگ استفاده کن.",
        "warp.caption_awg2": "🧬 <b>AmneziaWG نسخه ۲</b> · با بسته پوششی شبه QUIC\nاگر کلاینتت پارامتر I1 را پشتیبانی کند این نسخه مقاوم‌تر است. اگر خطا داد، همان فایل نسخه اول را استفاده کن.",
        "warp.caption_plain": "📄 <b>وایرگارد ساده</b>\n⚠️ بدون آبفاسکیشن است و روی اینترنت داخل ایران معمولا چند ثانیه بعد از اتصال قطع می‌شود. فقط برای جایی که فیلترینگ نیست یا برای تست استفاده کن.",
        "warp.caption_link": "🔗 <b>لینک‌های وارپ</b>\n{rule}\n{links}\n\nروی هر لینک بزن تا کپی شود، بعد در v2rayNG یا Hiddify از گزینه Import from clipboard اضافه‌اش کن.\n🔊 نویز UDP داخل لینک تنظیم شده تا هندشیک لو نرود.",
        "warp.caption_singbox": "📦 <b>sing-box</b> · برای Hiddify و NekoBox",
        "warp.caption_clash": "🧩 <b>Clash / Mihomo</b> · شامل گروه انتخاب خودکار سریع‌ترین اندپوینت",
        "warp.apps": "📱 <b>برنامه‌های سازگار با AmneziaWG</b>\n{rule}\n• <b>اندروید:</b> AmneziaVPN · WG Tunnel · Hiddify\n• <b>آی‌اواس:</b> AmneziaVPN · Streisand · Hiddify\n• <b>ویندوز:</b> AmneziaVPN · Hiddify\n• <b>مک:</b> AmneziaVPN · Hiddify\n\n💡 برنامه رسمی WireGuard پارامترهای آبفاسکیشن را نمی‌فهمد؛ برای ایران AmneziaVPN یا Hiddify نصب کن.\n🔧 اگر وصل شد ولی سایت باز نشد، MTU را روی ۱۲۰۰ کم کن و از به‌روزرسانی اندپوینت‌ها یک آدرس دیگر بگیر.",
        "warp.off": "🚧 بخش وارپ موقتاً غیرفعال است. کمی بعد سر بزن.",
    },
    "en": {
        # ----------------------------------------------------------- buttons
        "btn.warp_build": "⚡ Build WARP automatically",
        "btn.warp_rebuild": "♻️ Refresh endpoints",
        "btn.warp_awg": "🛡 AmneziaWG (recommended)",
        "btn.warp_awg2": "🧬 AmneziaWG v2",
        "btn.warp_plain": "📄 Plain WireGuard",
        "btn.warp_link": "🔗 v2rayNG / Hiddify link",
        "btn.warp_singbox": "📦 sing-box export",
        "btn.warp_clash": "🧩 Clash export",
        "btn.warp_eps": "📡 Healthy endpoints",
        "btn.warp_rescan": "⚡ Scan endpoints now",
        "btn.warp_license": "💎 Apply WARP+ license",
        "btn.warp_delete": "🗑 Delete WARP identity",
        "btn.warp_apps": "📱 Compatible apps",
        "btn.warp_why": "🧠 Why AmneziaWG?",
        # -------------------------------------------------------------- menu
        "warp.menu": "🛡 <b>WARP and WireGuard</b>\n{rule}\nThe engine keeps probing Cloudflare endpoints with a <b>real handshake</b>, measuring latency, jitter and loss on each one. Anything that gets filtered leaves the pool within minutes.\n\n📡 Stable: <b>{stable}</b> of <b>{total}</b>\n🏆 Best ping: <b>{best}</b>\n🔌 Open ports: <b>{ports}</b>\n⏳ Last scan: <b>{updated}</b>\n⚙️ Scanning: <b>{state}</b>\n{rule}\n{status}",
        "warp.status_none": "🔓 No WARP identity yet. Hit build and it takes under 10 seconds.",
        "warp.status_ready": "✅ <b>Your WARP identity is ready</b>\n💎 Account: <b>{account}</b>\n📡 Endpoint: <code>{endpoint}</code>\n🔢 In the config: <b>{count}</b>\n🕒 Updated: <b>{updated}</b>",
        "warp.dpi_note": "🧠 <b>Why AmneziaWG?</b>\n{rule}\nPlain WireGuard has a fixed signature and Iranian DPI blackholes it moments after the handshake: you connect, then nothing moves.\n\nAmneziaWG sends decoy packets first and scrambles packet sizes and ordering, while the crypto core stays untouched. That is why Cloudflare's own unmodified WARP peer still accepts it.\n\n🔒 The obfuscation profile is unique per user, so one DPI rule cannot catch everyone at once.",
        # ------------------------------------------------------------- build
        "warp.building": "⚙️ Registering a fresh WARP identity and mounting the healthiest endpoints...",
        "warp.ready": "🎉 <b>Your WARP is ready!</b>\n{rule}\n💎 Account: <b>{account}</b>\n📡 Endpoint: <code>{endpoint}</code>\n🏆 Ping: <b>{ping}</b>\n🔢 Spares: <b>{count}</b>\n🧬 Obfuscation: <b>Jc={jc} · Jmin={jmin} · Jmax={jmax}</b>\n📶 MTU: <b>{mtu}</b>\n\n👇 Grab the export you need. If in doubt, take AmneziaWG.",
        "warp.failed": "❌ WARP registration failed: <code>{reason}</code>\nTry again in a moment.",
        "warp.refreshed": "✅ Endpoint switched.\n📡 New: <code>{endpoint}</code> · {ping}\n\n⚠️ Your old config still points at the previous address, so grab a fresh export.",
        "warp.refreshed_same": "✅ Your current endpoint is still healthy, so it stayed put and only the spares were refreshed.\n📡 <code>{endpoint}</code> · {ping}",
        "warp.none": "📭 No WARP identity yet. Build one first.",
        "warp.no_endpoint": "⏳ The pool has no confirmed endpoint yet, so the defaults were used.\nRun a scan now, or refresh the endpoints in a few minutes.",
        # --------------------------------------------------------- endpoints
        "warp.eps": "📡 <b>Healthy endpoints</b>\n{rule}\n{list}\n\nℹ️ Each address was probed several times with a real handshake. ✅ means stable, ⚪️ means it is being watched.",
        "warp.eps_empty": "📭 The pool is empty. Run a scan.",
        "warp.loss": "loss {pct}%",
        # ------------------------------------------------------------- scan
        "warp.rescanning": "⚡ Scan started",
        "warp.rescan_started": "⚡ <b>Endpoint scan</b>\nProbing addresses with a real handshake. The result lands in this message, so no need to wait around.",
        "warp.rescan_done": "✅ <b>Scan finished</b>\n📡 Stable: <b>{count}</b>\n🔍 Answered: <b>{alive}</b>\n🏆 Best: <b>{ping}</b>\n🔌 Ports: <b>{ports}</b>\n⏱ <b>{secs}</b>s",
        "warp.rescan_joined": "✅ <b>Scan finished</b> (you joined the one already running)\n📡 Stable: <b>{count}</b>\n🏆 Best: <b>{ping}</b>\n🔌 Ports: <b>{ports}</b>",
        "warp.rescan_empty": "📭 Nothing new answered this round. Your existing endpoints are untouched, try again in a few minutes.",
        "warp.rescan_cooldown": "⏳ <b>{wait}</b>s until you can scan again.",
        "warp.rescan_failed": "❌ The scan did not finish: <code>{reason}</code>\nTry again in a few minutes.",
        "warp.rescan_wait": "⏳ A scan is already running. Try again shortly.",
        # ----------------------------------------------------------- license
        "warp.license_prompt": "💎 <b>WARP+ license</b>\n{rule}\nSend the license key (the 26 character code) to apply it to your identity.\n✖️ Send /cancel to abort.",
        "warp.license_ok": "✅ License applied. Account: <b>{account}</b>\nGrab a fresh export so it takes effect.",
        "warp.license_bad": "❌ Cloudflare rejected that license: <code>{reason}</code>",
        # ------------------------------------------------------------ delete
        "warp.delete_confirm": "🗑 Sure? Your WARP identity is wiped and the old configs stop working.",
        "warp.deleted": "✅ WARP identity deleted.",
        # ----------------------------------------------------------- exports
        "warp.caption_awg": "🛡 <b>AmneziaWG</b> · first choice for Iran\nImport into AmneziaVPN, Hiddify or WG Tunnel. If the app refuses the file, add it from Import and pick config file.",
        "warp.caption_awg2": "🧬 <b>AmneziaWG v2</b> · with a QUIC-shaped decoy packet\nStronger if your client understands the I1 parameter. If it errors out, use the v1 file.",
        "warp.caption_plain": "📄 <b>Plain WireGuard</b>\n⚠️ No obfuscation, so on a filtered network it usually dies seconds after connecting. Use it where nothing filters, or for testing.",
        "warp.caption_link": "🔗 <b>WARP links</b>\n{rule}\n{links}\n\nTap a link to copy it, then add it in v2rayNG or Hiddify with Import from clipboard.\n🔊 UDP noise is baked into the link so the handshake does not stand out.",
        "warp.caption_singbox": "📦 <b>sing-box</b> · for Hiddify and NekoBox",
        "warp.caption_clash": "🧩 <b>Clash / Mihomo</b> · includes a group that auto-picks the fastest endpoint",
        "warp.apps": "📱 <b>Apps that speak AmneziaWG</b>\n{rule}\n• <b>Android:</b> AmneziaVPN · WG Tunnel · Hiddify\n• <b>iOS:</b> AmneziaVPN · Streisand · Hiddify\n• <b>Windows:</b> AmneziaVPN · Hiddify\n• <b>macOS:</b> AmneziaVPN · Hiddify\n\n💡 The official WireGuard app ignores obfuscation parameters. For Iran install AmneziaVPN or Hiddify.\n🔧 Connected but nothing loads? Drop MTU to 1200 and refresh the endpoints.",
        "warp.off": "🚧 The WARP section is off for now. Check back soon.",
    },
}
