"""Strings for the two family pools: the operator picker and the admin screens.

Kept in its own catalogue so the WARP wording can be re-tuned without touching
``locales/warp.py``, and merged last in ``i18n`` so these keys win.

Persian is the default and English is a full peer. Every screen leads with an
emoji because on Telegram that is the only visual hierarchy there is.

The ``pool.note_*`` family is worth a word. A refresh that swept forty-eight
addresses and heard nothing back used to print exactly that and stop, which
reads like nationwide filtering and is usually one of three completely different
problems with three completely different fixes. Each note names the cause and
the fix in one line.
"""

from __future__ import annotations

WARPPOOL: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------------ buttons
        "btn.wg_irancell": "📶 ایرانسل",
        "btn.wg_other": "🌐 سایر اپراتورها",
        "btn.wg_pick_again": "🔁 انتخاب مجدد اپراتور",
        "btn.wg_next_ep": "⚡️ اندپوینت بعدی استخر",
        "btn.amnezia": "⬇️ نصب AmneziaVPN",
        "btn.pool": "🏊 استخر اندپوینت‌ها",
        "btn.pool_refresh": "♻️ تازه‌سازی استخر",
        "btn.pool_refresh_v4": "♻️ تازه‌سازی IPv4",
        "btn.pool_refresh_v6": "♻️ تازه‌سازی IPv6",
        "btn.pool_audit": "🩺 بررسی کامل اندپوینت‌ها",
        "btn.pool_list": "📋 فهرست استخر",

        # ------------------------------------------------------- user screens
        "wg.pick_net": (
            "🧬 <b>ساخت WARP / WireGuard</b>\n{rule}\n"
            "اپراتورت را انتخاب کن تا اندپوینت مناسب همان شبکه را از استخر بردارم.\n\n"
            "📶 <b>ایرانسل</b> ← اندپوینت سالم <b>IPv6</b>\n"
            "🌐 <b>سایر اپراتورها</b> ← اندپوینت سالم <b>IPv4</b>\n\n"
            "🏊 استخر الان: IPv4 <b>{v4}</b>/{target} · IPv6 <b>{v6}</b>/{target}\n"
            "⚡️ همه‌ی اندپوینت‌های استخر با هندشیک واقعی WireGuard تست شده‌اند."
        ),
        "wg.making": "⏳ دارم اندپوینت سالم <b>{family}</b> را از استخر برمی‌دارم...",
        "wg.sent": (
            "✅ <b>کانفیگ آماده شد</b>\n{rule}\n"
            "📶 اپراتور: <b>{operator}</b>\n"
            "🧭 نوع اندپوینت: <b>{family}</b>\n"
            "🌍 اندپوینت: <code>{endpoint}</code>\n"
            "📡 پینگ: <b>{ping}</b> · ❤️ سلامت: <b>{health}</b>\n"
            "🔁 اندپوینت جایگزین: <b>{spares}</b>\n"
            "🎭 جانک: Jc <b>{jc}</b> · Jmin <b>{jmin}</b> · Jmax <b>{jmax}</b> · MTU <b>{mtu}</b>\n"
            "{rule}\n"
            "📲 <b>اجرا در {app}</b>\n"
            "١️⃣ اپ را باز کن و روی <b>+</b> بزن.\n"
            "٢️⃣ گزینه‌ی <b>Import configuration</b> را انتخاب کن.\n"
            "٣️⃣ همین فایل <code>.conf</code> را به اپ بده.\n"
            "٤️⃣ یک اسم دلخواه بگذار و <b>Connect</b> را بزن.\n\n"
            "💡 اگر وصل نشد، دکمه‌ی زیر را بزن تا اندپوینت بعدی استخر را بگیری."
        ),
        "wg.caption": "📄 کانفیگ AmneziaWG با اندپوینت سالم <b>{family}</b>",
        "wg.pool_cold": (
            "🥶 <b>استخر {family} الان خالی است</b>\n{rule}\n"
            "هیچ اندپوینت سالمی برای این خانواده پیدا نشد، و کانفیگ نیمه‌کاره نمی‌سازم.\n"
            "♻️ یک اسکن تازه در پس‌زمینه شروع شد؛ چند لحطه بعد دوباره امتحان کن."
        ),
        "wg.pool_no_route": (
            "⛔️ <b>این سرور اصلاً {family} ندارد</b>\n{rule}\n"
            "پس استخر {family} هرگز پر نمی‌شود و اسکن دوباره فرقی نمی‌کند.\n"
            "🛠 این را به مدیر بگو: روت این خانواده روی سرور باید فعال شود.\n"
            "👉 فعلاً از گزینه‌ی دیگر استفاده کن."
        ),
        "wg.identity_failed": "⛔️ ساخت هویت وارپ ناموفق بود: <code>{reason}</code>",
        "wg.family_v4": "IPv4",
        "wg.family_v6": "IPv6",

        # ------------------------------------------------------ admin screens
        "pool.screen": (
            "🏊 <b>استخر اندپوینت‌های وارپ</b>\n{rule}\n"
            "🧩 منبع اسکن: <code>{source}</code>\n"
            "🔑 هویت اسکن: {identity}\n"
            "🛣 روت این سرور: {routes}\n"
            "🤖 ایجنت: <b>{agent}</b> · هر <b>{interval}</b> ثانیه · پاس: <b>{passes}</b>\n"
            "🔬 تست عبور ترافیک: <b>{deep}</b>\n"
            "❤️ کف سلامت: <b>{floor}</b>\n{rule}\n"
            "🌐 <b>IPv4</b> {v4mark} — سالم <b>{v4}</b>/{target}\n"
            "   ⚡️ بهترین: <b>{v4best}</b> · میانگین: <b>{v4avg}</b>\n"
            "   🌍 <code>{v4ep}</code>\n\n"
            "🧬 <b>IPv6</b> {v6mark} — سالم <b>{v6}</b>/{target}\n"
            "   ⚡️ بهترین: <b>{v6best}</b> · میانگین: <b>{v6avg}</b>\n"
            "   🌍 <code>{v6ep}</code>\n{rule}\n"
            "🕒 آخرین بروزرسانی: {updated}"
        ),
        "pool.identity_ok": "✅ کلاود‌فلر جواب می‌دهد",
        "pool.identity_bad": "⛔️ جواب نمی‌دهد (همه‌ی اندپوینت‌ها مرده دیده می‌شوند)",
        "pool.identity_unknown": "❓ هنوز تست نشده",
        "pool.refresh_started": (
            "♻️ <b>تازه‌سازی استخر شروع شد</b>\n{rule}\n"
            "اسکن در پس‌زمینه اجرا می‌شود، پس ربات قفل نمی‌شود.\n"
            "📝 نتیجه در همین پیام بروز می‌شود."
        ),
        "pool.refresh_done": (
            "✅ <b>استخر {family} تازه شد</b>\n{rule}\n"
            "🔍 آدرس اسکن‌شده: <b>{probed}</b>\n"
            "📞 جواب دادند: <b>{answered}</b>\n"
            "❤️ سالم شناخته شد: <b>{healthy}</b>\n"
            "🔬 عبور ترافیک تأیید شد: <b>{proven}</b>\n"
            "💾 در استخر نوشته شد: <b>{stored}</b>\n"
            "🗑 حذف شد: <b>{dropped}</b>\n"
            "🏊 استخر: <b>{pool}</b>/{target} {mark}\n"
            "⚡️ بهترین پینگ: <b>{best}</b>\n"
            "🔌 پورت‌ها: <b>{ports}</b>\n"
            "⏱ زمان: <b>{secs}</b> ثانیه"
        ),
        "pool.refresh_busy": "⏳ یک تازه‌سازی روی استخر {family} در حال اجراست.",
        "pool.refresh_cooldown": "⏲ خیلی زود بود. <b>{wait}</b> ثانیه دیگر صبر کن.",
        "pool.refresh_failed": "⛔️ تازه‌سازی استخر {family} ناموفق بود: <code>{reason}</code>",
        "pool.refresh_unreachable": (
            "⛔️ <b>استخر {family} قابل اسکن نیست</b>\n{rule}\n"
            "این سرور روت {family} ندارد، پس هیچ بسته‌ای از اینجا بیرون نمی‌رود."
        ),

        # ----------------------------------------- why a sweep found nothing
        "pool.note_no_route": (
            "🛠 <b>علت:</b> روت این خانواده روی سرور وجود ندارد. در داکر معمولاً یعنی کانتینر "
            "روی شبکه‌ی bridge پیش‌فرض است که IPv6 ندارد.\n"
            "👉 در <code>docker-compose.yml</code> گزینه‌ی <code>network_mode: host</code> را فعال کن "
            "(یا IPv6 را روی شبکه‌ی داکر روشن کن) و سرویس را ریستارت کن."
        ),
        "pool.note_identity": (
            "🛠 <b>علت:</b> کلاود‌فلر به کلید اسکن ما جواب نمی‌دهد. وارپ به هندشیک یک دیوایس "
            "ثبت‌نشده <b>بی‌صدا</b> جواب نمی‌دهد، پس همه‌ی اندپوینت‌ها مرده دیده می‌شوند.\n"
            "👉 اگر <code>api.cloudflareclient.com</code> از سرور باز نمی‌شود، بسته‌ی <code>warpep</code> "
            "را نصب کن تا هویت ثبت‌شده‌ی آن به کار بیاید."
        ),
        "pool.note_ports": (
            "🛠 <b>علت:</b> هیچ پورت UDP وارپ از این سرور جواب نداد، پس لیست پیش‌فرض فرض شد.\n"
            "👉 یا UDP خروجی روی سرور بسته است، یا هویت اسکن ثبت‌شده نیست. "
            "فایروال را برای پورت‌های <code>2408 500 1701 4500</code> چک کن."
        ),
        "pool.note_filtered": (
            "🛠 <b>علت:</b> کلید اسکن سالم است و روت هم وجود دارد، پس واقعاً این مسیر دارد وارپ را "
            "دروپ می‌کند.\n"
            "👉 کمی بعد دوباره امتحان کن یا <code>WARP_POOL_SAMPLE</code> را بالاتر ببر."
        ),
        "pool.note_floor": (
            "🛠 <b>علت:</b> اندپوینت‌ها جواب دادند ولی هیچ‌کدام از کف سلامت رد نشد.\n"
            "👉 اگر خط الان شلوغ است، موقتاً <code>WARP_HEALTH_FLOOR</code> را پایین‌تر بگذار."
        ),

        "pool.audit_started": (
            "🩺 <b>بررسی کامل استخر شروع شد</b>\n{rule}\n"
            "همه‌ی اندپوینت‌های هر دو استخر دوباره پینگ می‌شوند، "
            "مرده‌ها حذف و زنده‌ها به ترتیب پینگ مرتب می‌شوند."
        ),
        "pool.audit_done": (
            "{verdict}\n{rule}\n"
            "🔍 بررسی شد: <b>{checked}</b>\n"
            "✅ زنده: <b>{alive}</b>\n"
            "💀 مرده و حذف‌شده: <b>{dead}</b>\n"
            "🧹 پاکسازی اضافی: <b>{removed}</b>\n{rule}\n"
            "🌐 IPv4: <b>{v4}</b>/{target} {v4mark} · بهترین <b>{v4best}</b>\n"
            "🧬 IPv6: <b>{v6}</b>/{target} {v6mark} · بهترین <b>{v6best}</b>\n{rule}\n"
            "⏱ زمان: <b>{secs}</b> ثانیه"
        ),
        "pool.audit_busy": "⏳ یک بررسی کامل همین الان در جریان است.",
        "pool.audit_failed": "⛔️ بررسی کامل ناموفق بود: <code>{reason}</code>",
        "pool.verdict_healthy": "✅ <b>استخر سالم است</b>",
        "pool.verdict_degraded": "⚠️ <b>استخر ناقص است</b>",
        "pool.verdict_empty": "⛔️ <b>استخر خالی است</b>",
        "pool.list": "📋 <b>فهرست استخر</b> · به ترتیب پینگ\n{rule}\n{list}",
        "pool.list_family": "\n<b>{family}</b> · <b>{count}</b>/{target}\n",
        "pool.list_empty": "🕳 استخر هنوز خالی است. دکمه‌ی تازه‌سازی را بزن.",
        "pool.deep_off": "خاموش (بسته‌ی warpep نصب نیست)",
    },
    "en": {
        # ------------------------------------------------------------ buttons
        "btn.wg_irancell": "📶 Irancell",
        "btn.wg_other": "🌐 Other operators",
        "btn.wg_pick_again": "🔁 Pick another operator",
        "btn.wg_next_ep": "⚡️ Next endpoint from the pool",
        "btn.amnezia": "⬇️ Install AmneziaVPN",
        "btn.pool": "🏊 Endpoint pools",
        "btn.pool_refresh": "♻️ Refresh pools",
        "btn.pool_refresh_v4": "♻️ Refresh IPv4",
        "btn.pool_refresh_v6": "♻️ Refresh IPv6",
        "btn.pool_audit": "🩺 Full endpoint check",
        "btn.pool_list": "📋 Pool listing",

        # ------------------------------------------------------- user screens
        "wg.pick_net": (
            "🧬 <b>Build WARP / WireGuard</b>\n{rule}\n"
            "Pick your operator and I will take a matching endpoint out of the pool.\n\n"
            "📶 <b>Irancell</b> → healthy <b>IPv6</b> endpoint\n"
            "🌐 <b>Other operators</b> → healthy <b>IPv4</b> endpoint\n\n"
            "🏊 Pools right now: IPv4 <b>{v4}</b>/{target} · IPv6 <b>{v6}</b>/{target}\n"
            "⚡️ Every endpoint in a pool passed a real WireGuard handshake."
        ),
        "wg.making": "⏳ Taking a healthy <b>{family}</b> endpoint out of the pool...",
        "wg.sent": (
            "✅ <b>Your config is ready</b>\n{rule}\n"
            "📶 Operator: <b>{operator}</b>\n"
            "🧭 Endpoint family: <b>{family}</b>\n"
            "🌍 Endpoint: <code>{endpoint}</code>\n"
            "📡 Ping: <b>{ping}</b> · ❤️ Health: <b>{health}</b>\n"
            "🔁 Spare endpoints: <b>{spares}</b>\n"
            "🎭 Junk: Jc <b>{jc}</b> · Jmin <b>{jmin}</b> · Jmax <b>{jmax}</b> · MTU <b>{mtu}</b>\n"
            "{rule}\n"
            "📲 <b>How to run it in {app}</b>\n"
            "1️⃣ Open the app and tap <b>+</b>.\n"
            "2️⃣ Choose <b>Import configuration</b>.\n"
            "3️⃣ Hand it this <code>.conf</code> file.\n"
            "4️⃣ Name it whatever you like and hit <b>Connect</b>.\n\n"
            "💡 If it will not connect, use the button below to take the next endpoint."
        ),
        "wg.caption": "📄 AmneziaWG config on a healthy <b>{family}</b> endpoint",
        "wg.pool_cold": (
            "🥶 <b>The {family} pool is empty right now</b>\n{rule}\n"
            "No healthy endpoint of that family was found, and I will not ship a config "
            "that cannot work.\n"
            "♻️ A fresh scan just started in the background. Try again in a moment."
        ),
        "wg.pool_no_route": (
            "⛔️ <b>This server has no {family} connectivity at all</b>\n{rule}\n"
            "So the {family} pool can never fill and scanning again will not change that.\n"
            "🛠 Tell the operator: this host needs a working {family} route.\n"
            "👉 Use the other option for now."
        ),
        "wg.identity_failed": "⛔️ WARP identity could not be created: <code>{reason}</code>",
        "wg.family_v4": "IPv4",
        "wg.family_v6": "IPv6",

        # ------------------------------------------------------ admin screens
        "pool.screen": (
            "🏊 <b>WARP endpoint pools</b>\n{rule}\n"
            "🧩 Scan source: <code>{source}</code>\n"
            "🔑 Scan identity: {identity}\n"
            "🛣 Routes on this host: {routes}\n"
            "🤖 Agent: <b>{agent}</b> · every <b>{interval}</b>s · passes: <b>{passes}</b>\n"
            "🔬 Tunnel traffic check: <b>{deep}</b>\n"
            "❤️ Health floor: <b>{floor}</b>\n{rule}\n"
            "🌐 <b>IPv4</b> {v4mark} — healthy <b>{v4}</b>/{target}\n"
            "   ⚡️ best: <b>{v4best}</b> · average: <b>{v4avg}</b>\n"
            "   🌍 <code>{v4ep}</code>\n\n"
            "🧬 <b>IPv6</b> {v6mark} — healthy <b>{v6}</b>/{target}\n"
            "   ⚡️ best: <b>{v6best}</b> · average: <b>{v6avg}</b>\n"
            "   🌍 <code>{v6ep}</code>\n{rule}\n"
            "🕒 Last updated: {updated}"
        ),
        "pool.identity_ok": "✅ Cloudflare answers it",
        "pool.identity_bad": "⛔️ not answered (every endpoint will look dead)",
        "pool.identity_unknown": "❓ not tested yet",
        "pool.refresh_started": (
            "♻️ <b>Pool refresh started</b>\n{rule}\n"
            "The scan runs in the background, so nothing here is blocked.\n"
            "📝 This message is updated with the result."
        ),
        "pool.refresh_done": (
            "✅ <b>{family} pool refreshed</b>\n{rule}\n"
            "🔍 Addresses swept: <b>{probed}</b>\n"
            "📞 Answered: <b>{answered}</b>\n"
            "❤️ Judged healthy: <b>{healthy}</b>\n"
            "🔬 Traffic proven: <b>{proven}</b>\n"
            "💾 Written to the pool: <b>{stored}</b>\n"
            "🗑 Removed: <b>{dropped}</b>\n"
            "🏊 Pool: <b>{pool}</b>/{target} {mark}\n"
            "⚡️ Best ping: <b>{best}</b>\n"
            "🔌 Ports: <b>{ports}</b>\n"
            "⏱ Took: <b>{secs}</b>s"
        ),
        "pool.refresh_busy": "⏳ A refresh of the {family} pool is already running.",
        "pool.refresh_cooldown": "⏲ Too soon. Give it <b>{wait}</b> more seconds.",
        "pool.refresh_failed": "⛔️ Refreshing the {family} pool failed: <code>{reason}</code>",
        "pool.refresh_unreachable": (
            "⛔️ <b>The {family} pool cannot be scanned</b>\n{rule}\n"
            "This host has no {family} route, so not one packet leaves the box."
        ),

        # ----------------------------------------- why a sweep found nothing
        "pool.note_no_route": (
            "🛠 <b>Cause:</b> this host has no route for that family. On Docker that almost "
            "always means the container sits on the default bridge network, which has no "
            "IPv6 at all.\n"
            "👉 Set <code>network_mode: host</code> in <code>docker-compose.yml</code> (or "
            "enable IPv6 on the Docker network) and restart the service."
        ),
        "pool.note_identity": (
            "🛠 <b>Cause:</b> Cloudflare is not answering our scan key. WARP drops a handshake "
            "from an unenrolled device <b>in silence</b>, so every endpoint on earth looks "
            "dead.\n"
            "👉 If <code>api.cloudflareclient.com</code> is blocked from this server, install "
            "the <code>warpep</code> package so its enrolled probing identity can be used."
        ),
        "pool.note_ports": (
            "🛠 <b>Cause:</b> no WARP UDP port answered from this host, so the default list "
            "was assumed.\n"
            "👉 Either outbound UDP is blocked here or the scan identity is not enrolled. "
            "Check the firewall for <code>2408 500 1701 4500</code>."
        ),
        "pool.note_filtered": (
            "🛠 <b>Cause:</b> the scan key works and the route exists, so this path really is "
            "dropping WARP right now.\n"
            "👉 Try again shortly, or raise <code>WARP_POOL_SAMPLE</code> to widen the sweep."
        ),
        "pool.note_floor": (
            "🛠 <b>Cause:</b> endpoints answered but none of them cleared the health floor.\n"
            "👉 If the uplink is congested right now, lower <code>WARP_HEALTH_FLOOR</code> "
            "temporarily."
        ),

        "pool.audit_started": (
            "🩺 <b>Full pool check started</b>\n{rule}\n"
            "Every endpoint in both pools is being re-pinged, the dead are deleted and "
            "the survivors are re-sorted by ping."
        ),
        "pool.audit_done": (
            "{verdict}\n{rule}\n"
            "🔍 Checked: <b>{checked}</b>\n"
            "✅ Alive: <b>{alive}</b>\n"
            "💀 Dead and deleted: <b>{dead}</b>\n"
            "🧹 Extra cleanup: <b>{removed}</b>\n{rule}\n"
            "🌐 IPv4: <b>{v4}</b>/{target} {v4mark} · best <b>{v4best}</b>\n"
            "🧬 IPv6: <b>{v6}</b>/{target} {v6mark} · best <b>{v6best}</b>\n{rule}\n"
            "⏱ Took: <b>{secs}</b>s"
        ),
        "pool.audit_busy": "⏳ A full check is already in progress.",
        "pool.audit_failed": "⛔️ The full check failed: <code>{reason}</code>",
        "pool.verdict_healthy": "✅ <b>The pools are healthy</b>",
        "pool.verdict_degraded": "⚠️ <b>The pools are short of target</b>",
        "pool.verdict_empty": "⛔️ <b>The pools are empty</b>",
        "pool.list": "📋 <b>Pool listing</b> · sorted by ping\n{rule}\n{list}",
        "pool.list_family": "\n<b>{family}</b> · <b>{count}</b>/{target}\n",
        "pool.list_empty": "🕳 The pools are still empty. Press refresh.",
        "pool.deep_off": "off (the warpep package is not installed)",
    },
}
