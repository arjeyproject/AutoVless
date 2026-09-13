"""Copy for the three features added in 2.0: the invite lock, the free pool,
and the AI exit screen. Persian first, English a full peer, same as everywhere
else in this catalogue."""

GROWTH: dict[str, dict[str, str]] = {
    "fa": {
        # ---------------------------------------------------------- invite lock
        "ref.gate": (
            "🔐 <b>یک قدم کوچک، بعد همه‌چیز باز است</b>\n{rule}\n"
            "این ربات را رایگان نگه داشته‌ایم و تنها هزینه‌اش این است که کنارش بمانی:\n\n"
            "🎯 برای باز شدن ربات باید <b>{required}</b> نفر را با لینک اختصاصی خودت دعوت کنی.\n"
            "✅ تا این لحظه: <b>{invited}</b> از <b>{required}</b>\n"
            "{bar}\n\n"
            "🔗 لینک اختصاصی تو:\n<code>{link}</code>\n\n"
            "💡 لینک را برای دوستانت بفرست؛ به‌محض این که وارد ربات شوند، شمارنده بالا می‌رود "
            "و قفل خودکار برداشته می‌شود.\n"
            "پس از باز شدن، ساخت پنل توربو، وایرگارد، تروجان و کانفیگ‌های رایگان بدون هیچ محدودیتی در اختیار توست. 🚀"
        ),
        "ref.card": (
            "🎁 <b>دعوت دوستان</b>\n{rule}\n"
            "🔗 لینک تو:\n<code>{link}</code>\n\n"
            "👥 دعوت‌شده‌ها: <b>{invited}</b>\n"
            "🎯 سهمیه لازم: <b>{required}</b>\n"
            "{bar}\n\n"
            "{state}\n\n"
            "💬 متن پیشنهادی برای ارسال:\n"
            "<blockquote>با این ربات در چند ثانیه کانفیگ اختصاصی خودت را می‌سازی، "
            "روی اکانت خودت، بدون فروشنده و کاملاً رایگان 👇\n{link}</blockquote>"
        ),
        "ref.state_open": "✅ قفل برای تو باز است. نوش جانت!",
        "ref.state_locked": "⏳ <b>{left}</b> نفر دیگر تا باز شدن کامل ربات.",
        "ref.state_off": "🎉 قفل دعوت در حال حاضر خاموش است؛ این آمار فقط برای افتخار خودت است.",
        "ref.checked_ok": "🎉 قفل باز شد، خوش آمدی!",
        "ref.checked_no": "هنوز {left} نفر مانده. لینکت را برای چند نفر دیگر بفرست.",
        "ref.credited": "🎉 <b>{name}</b> با لینک تو وارد ربات شد. مجموع دعوت‌هایت: <b>{invited}</b>",
        "btn.invite": "🎁 دعوت دوستان",
        "btn.ref_check": "🔄 بررسی مجدد",
        "btn.ref_share": "📤 ارسال لینک",
        # -------------------------------------------------------- free configs
        "free.menu": (
            "🎈 <b>کانفیگ‌های رایگان</b>\n{rule}\n"
            "این‌ها روی موتور واقعی همین ربات ساخته می‌شوند: آی‌پی ورودی از استخر تمیزِ "
            "اسکن‌شده انتخاب و قبل از تحویل با هندشیک واقعی تست می‌شود.\n\n"
            "🌐 سرورهای رایگان فعال: <b>{servers}</b>\n"
            "📡 آی‌پی تمیز تاییدشده: <b>{verified}</b>\n"
            "🧬 اندپوینت وارپ سالم: <b>{warp}</b>\n\n"
            "ساخت و مصرف این بخش کاملاً رایگان است و به اکانت کلادفلر نیازی ندارد."
        ),
        "free.none": (
            "🙁 هنوز سرور رایگانی ثبت نشده.\n"
            "اگر مدیر ربات هستی از پنل ادمین → کانفیگ رایگان یک سرور اضافه کن "
            "(می‌توانی پنل توربوی خودت را با یک دکمه به‌عنوان سرور رایگان ثبت کنی)."
        ),
        "free.disabled": "⛔️ بخش رایگان موقتاً بسته است.",
        "free.limit": "⚠️ سهمیه‌ی رایگان تو ({limit} بار) تمام شده. برای کانفیگ اختصاصی، پنل توربو بساز.",
        "free.building": "⏳ دارم کانفیگ‌های رایگان را می‌سازم و تست می‌کنم...",
        "free.empty": "😔 در این لحظه هیچ آی‌پی تمیزی از تست عبور نکرد. چند دقیقه بعد دوباره امتحان کن.",
        "free.ready": (
            "🎈 <b>{title}</b>\n{rule}\n"
            "🌐 سرور: <code>{host}</code>\n"
            "📦 تعداد کانفیگ: <b>{count}</b> · بهترین پینگ: <b>{best}</b>\n"
            "🔄 لینک اشتراک (خودکار به‌روز می‌شود):\n<code>{sub}</code>\n\n"
            "{tip}"
        ),
        "free.tip_vless": "💡 لینک اشتراک را در v2rayNG / Streisand / Hiddify وارد کن؛ آی‌پی‌های تازه خودکار می‌آیند.",
        "free.tip_trojan": "💡 تروجان فقط روی پورت‌های TLS ساخته می‌شود. اگر VLESS روی شبکه‌ات جواب نداد، این را امتحان کن.",
        "free.tip_mix": "💡 این لینک هر دو پروتکل را با هم می‌دهد؛ کلاینت هرکدام که جواب داد را نگه می‌دارد.",
        "btn.free": "🎈 کانفیگ رایگان",
        "btn.free_vless": "⚡️ ولس رایگان",
        "btn.free_trojan": "🎯 تروجان رایگان",
        "btn.free_mix": "🧩 هر دو پروتکل",
        "btn.free_warp": "🧬 وایرگارد رایگان",
        "btn.free_sub": "🔄 لینک اشتراک",
        # ------------------------------------------------------------- mini app
        "btn.miniapp": "🚀 مینی‌اپ",
        "miniapp.card": (
            "🚀 <b>مینی‌اپ {brand}</b>\n{rule}\n"
            "همه‌ی امکانات ربات با ظاهر گرافیکی: پنل توربو، وایرگارد، تروجان، "
            "کانفیگ رایگان، دعوت دوستان و آمار زنده.\n\n"
            "دکمه‌ی پایین را بزن تا باز شود."
        ),
        # ------------------------------------------------------- admin: invite
        "admin.ref": (
            "🔐 <b>قفل دعوت اجباری</b>\n{rule}\n"
            "وضعیت قفل: <b>{state}</b>\n"
            "🎯 تعداد لازم برای هر کاربر: <b>{required}</b> نفر\n\n"
            "👥 کل دعوت‌های ثبت‌شده: <b>{total}</b> (امروز +{today})\n"
            "🏅 تعداد دعوت‌کننده‌ها: <b>{inviters}</b>\n\n"
            "ℹ️ دعوت تکراری، دعوت خودت و اکانت‌هایی که قبلاً در ربات بوده‌اند شمرده نمی‌شوند."
        ),
        "admin.ref_prompt": "🔢 تعداد کاربری که هر نفر باید دعوت کند را بفرست (عدد ۰ تا ۵۰). عدد ۰ یعنی قفل بی‌اثر.",
        "admin.ref_saved": "✅ سهمیه روی <b>{required}</b> نفر تنظیم شد.",
        "admin.ref_bad": "❌ فقط عدد بفرست (۰ تا ۵۰).",
        "admin.ref_top": "🏆 <b>برترین دعوت‌کننده‌ها</b>\n{rule}\n{list}",
        "admin.ref_empty": "هنوز دعوتی ثبت نشده.",
        "btn.ref_lock": "🔐 قفل دعوت",
        "btn.ref_toggle": "🔁 روشن / خاموش",
        "btn.ref_count": "🔢 تعیین تعداد",
        "btn.ref_top": "🏆 برترین‌ها",
        "opt.referral_lock": "قفل دعوت اجباری",
        "opt.free_enabled": "بخش کانفیگ رایگان",
        # --------------------------------------------------------- admin: free
        "admin.free": (
            "🎈 <b>سرورهای کانفیگ رایگان</b>\n{rule}\n"
            "فعال: <b>{servers}</b> · سالم: <b>{healthy}</b>\n"
            "📦 کانفیگ تحویل‌شده: <b>{grants}</b> برای <b>{users}</b> کاربر\n\n{list}\n\n"
            "ℹ️ هر سرور یک ورکر AutoVless است. با دکمه‌ی زیر می‌توانی پنل توربوی خودت را "
            "به‌عنوان سرور رایگان ثبت کنی."
        ),
        "admin.free_empty": "هیچ سروری ثبت نشده.",
        "admin.free_prompt": (
            "📎 اطلاعات سرور را در یک خط بفرست:\n"
            "<code>host uuid [password] [path]</code>\n\n"
            "نمونه:\n<code>myworker.workers.dev 8f0c... </code>\n"
            "یا مستقیم لینک اشتراک ورکر را بفرست:\n"
            "<code>https://myworker.workers.dev/8f0c.../sub</code>"
        ),
        "admin.free_added": "✅ سرور <code>{host}</code> ثبت شد.",
        "admin.free_bad": "❌ ورودی نامعتبر بود: {reason}",
        "admin.free_gone": "🗑 سرور حذف شد.",
        "admin.free_checked": "🔎 بررسی شد: <b>{healthy}</b> سالم از <b>{total}</b>.",
        "admin.free_panel_none": "اول باید خودت یک پنل توربو بسازی.",
        "btn.free_add": "➕ افزودن سرور",
        "btn.free_from_panel": "🗂 ثبت پنل خودم",
        "btn.free_check": "🔎 بررسی سلامت",
        "btn.free_admin": "🎈 کانفیگ رایگان",
        # ------------------------------------------------------------ admin: ai
        "admin.ai": (
            "🧠 <b>مسیر هوش مصنوعی</b>\n{rule}\n"
            "🛡 رله‌ی تاییدشده: <b>{verified}</b> از <b>{total}</b>\n"
            "🌍 مکان‌یابی‌شده: <b>{placed}</b> · 🇺🇸 آمریکا: <b>{us}</b>\n"
            "🗺 کشورها: {countries}\n\n"
            "📌 پنل‌های پین‌شده: <b>{pinned}</b>\n"
            "🎯 توزیع پین‌ها: {pins}\n"
            "🧩 دامنه‌های تحت مسیر AI: <b>{domains}</b>\n\n"
            "ℹ️ هر پنل فقط و فقط یک رله برای ترافیک AI می‌گیرد تا آی‌پی خروجی ثابت بماند؛ "
            "لاگین گوگل و خود جیمینای از یک آی‌پی خارج می‌شوند و حلقه‌ی لاگین تمام می‌شود."
        ),
        "admin.ai_geo": "🌍 در حال مکان‌یابی رله‌ها...",
        "admin.ai_geo_done": "✅ مکان‌یابی تمام شد: <b>{placed}</b> رله شناسایی شد ({us} آمریکا).",
        "btn.ai_relays": "🧠 مسیر AI",
        "btn.ai_geo": "🌍 مکان‌یابی رله‌ها",
    },
    "en": {
        "ref.gate": (
            "🔐 <b>One small step and everything opens</b>\n{rule}\n"
            "This bot is free. The only price is bringing a few people along:\n\n"
            "🎯 Invite <b>{required}</b> people with your own link to unlock the bot.\n"
            "✅ So far: <b>{invited}</b> of <b>{required}</b>\n"
            "{bar}\n\n"
            "🔗 Your personal link:\n<code>{link}</code>\n\n"
            "💡 Send it to your friends. The counter moves the moment they open the bot and "
            "the lock lifts by itself.\n"
            "After that the turbo panel, WireGuard, Trojan and the free configs are all yours. 🚀"
        ),
        "ref.card": (
            "🎁 <b>Invite friends</b>\n{rule}\n"
            "🔗 Your link:\n<code>{link}</code>\n\n"
            "👥 Invited: <b>{invited}</b>\n"
            "🎯 Required: <b>{required}</b>\n"
            "{bar}\n\n"
            "{state}\n\n"
            "💬 Something you can paste:\n"
            "<blockquote>This bot builds your own config in seconds, on your own account, "
            "no reseller, completely free 👇\n{link}</blockquote>"
        ),
        "ref.state_open": "✅ The lock is open for you. Enjoy.",
        "ref.state_locked": "⏳ <b>{left}</b> more to go.",
        "ref.state_off": "🎉 The invite lock is off right now, so this is just bragging rights.",
        "ref.checked_ok": "🎉 Unlocked, welcome in!",
        "ref.checked_no": "Still {left} to go. Send your link to a few more people.",
        "ref.credited": "🎉 <b>{name}</b> joined with your link. Total invites: <b>{invited}</b>",
        "btn.invite": "🎁 Invite friends",
        "btn.ref_check": "🔄 Check again",
        "btn.ref_share": "📤 Share link",
        "free.menu": (
            "🎈 <b>Free configs</b>\n{rule}\n"
            "Built by the same real engine: the entry address comes from the scanned clean-IP "
            "pool and completes a real handshake before it is handed over.\n\n"
            "🌐 Active free servers: <b>{servers}</b>\n"
            "📡 Verified clean IPs: <b>{verified}</b>\n"
            "🧬 Healthy WARP endpoints: <b>{warp}</b>\n\n"
            "Building and using this section is free and needs no Cloudflare account."
        ),
        "free.none": (
            "🙁 No free server registered yet.\n"
            "If you are the admin, open Admin → Free configs and add one. Your own turbo panel "
            "can be registered as a free server with a single tap."
        ),
        "free.disabled": "⛔️ The free section is closed for now.",
        "free.limit": "⚠️ You have used your free quota ({limit}). Build a turbo panel for your own configs.",
        "free.building": "⏳ Building and testing your free configs...",
        "free.empty": "😔 Nothing passed the handshake test right now. Try again in a few minutes.",
        "free.ready": (
            "🎈 <b>{title}</b>\n{rule}\n"
            "🌐 Server: <code>{host}</code>\n"
            "📦 Configs: <b>{count}</b> · best ping: <b>{best}</b>\n"
            "🔄 Subscription (updates itself):\n<code>{sub}</code>\n\n"
            "{tip}"
        ),
        "free.tip_vless": "💡 Paste the subscription into v2rayNG / Streisand / Hiddify and fresh IPs arrive on their own.",
        "free.tip_trojan": "💡 Trojan is TLS-only by design. If VLESS stopped working on your network, try this.",
        "free.tip_mix": "💡 One link, both protocols. The client keeps whichever answers.",
        "btn.free": "🎈 Free config",
        "btn.free_vless": "⚡️ Free VLESS",
        "btn.free_trojan": "🎯 Free Trojan",
        "btn.free_mix": "🧩 Both protocols",
        "btn.free_warp": "🧬 Free WireGuard",
        "btn.free_sub": "🔄 Subscription",
        "btn.miniapp": "🚀 Mini App",
        "miniapp.card": (
            "🚀 <b>{brand} Mini App</b>\n{rule}\n"
            "Everything the bot does, with a real interface: turbo panel, WireGuard, Trojan, "
            "free configs, invites and live stats.\n\n"
            "Tap the button below."
        ),
        "admin.ref": (
            "🔐 <b>Forced invite lock</b>\n{rule}\n"
            "Lock: <b>{state}</b>\n"
            "🎯 Required per user: <b>{required}</b>\n\n"
            "👥 Recorded invites: <b>{total}</b> (today +{today})\n"
            "🏅 Inviters: <b>{inviters}</b>\n\n"
            "ℹ️ Duplicate invites, self-invites and accounts that were already using the bot do not count."
        ),
        "admin.ref_prompt": "🔢 Send how many people each user must invite (0 to 50). Zero disables the lock.",
        "admin.ref_saved": "✅ Quota set to <b>{required}</b>.",
        "admin.ref_bad": "❌ Numbers only (0 to 50).",
        "admin.ref_top": "🏆 <b>Top inviters</b>\n{rule}\n{list}",
        "admin.ref_empty": "No invites recorded yet.",
        "btn.ref_lock": "🔐 Invite lock",
        "btn.ref_toggle": "🔁 On / off",
        "btn.ref_count": "🔢 Set quota",
        "btn.ref_top": "🏆 Top inviters",
        "opt.referral_lock": "Forced invite lock",
        "opt.free_enabled": "Free config section",
        "admin.free": (
            "🎈 <b>Free config servers</b>\n{rule}\n"
            "Active: <b>{servers}</b> · healthy: <b>{healthy}</b>\n"
            "📦 Configs handed out: <b>{grants}</b> to <b>{users}</b> users\n\n{list}\n\n"
            "ℹ️ Every server is an AutoVless worker. The button below registers your own turbo "
            "panel as a free server."
        ),
        "admin.free_empty": "No server registered.",
        "admin.free_prompt": (
            "📎 Send the server on one line:\n"
            "<code>host uuid [password] [path]</code>\n\n"
            "Example:\n<code>myworker.workers.dev 8f0c...</code>\n"
            "Or just paste the worker subscription link:\n"
            "<code>https://myworker.workers.dev/8f0c.../sub</code>"
        ),
        "admin.free_added": "✅ Server <code>{host}</code> registered.",
        "admin.free_bad": "❌ That input was not valid: {reason}",
        "admin.free_gone": "🗑 Server removed.",
        "admin.free_checked": "🔎 Checked: <b>{healthy}</b> healthy of <b>{total}</b>.",
        "admin.free_panel_none": "Build your own turbo panel first.",
        "btn.free_add": "➕ Add server",
        "btn.free_from_panel": "🗂 Use my panel",
        "btn.free_check": "🔎 Health check",
        "btn.free_admin": "🎈 Free configs",
        "admin.ai": (
            "🧠 <b>AI route</b>\n{rule}\n"
            "🛡 Verified relays: <b>{verified}</b> of <b>{total}</b>\n"
            "🌍 Geolocated: <b>{placed}</b> · 🇺🇸 US: <b>{us}</b>\n"
            "🗺 Countries: {countries}\n\n"
            "📌 Pinned panels: <b>{pinned}</b>\n"
            "🎯 Pin spread: {pins}\n"
            "🧩 Domains on the AI route: <b>{domains}</b>\n\n"
            "ℹ️ Each panel gets exactly one AI relay so the exit address never moves: the Google "
            "login and Gemini itself leave through the same IP, which is what ends the login loop."
        ),
        "admin.ai_geo": "🌍 Geolocating relays...",
        "admin.ai_geo_done": "✅ Done: <b>{placed}</b> relays placed ({us} in the US).",
        "btn.ai_relays": "🧠 AI route",
        "btn.ai_geo": "🌍 Geolocate relays",
    },
}
