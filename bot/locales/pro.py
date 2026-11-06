"""Copy for the 3.0 pro layer: WARP tuning, identity backup, the benchmark,
the stronger admin console and the scheduled digest. Persian first, English a
full peer. Multi-line Persian screens carry the right-to-left mark, exactly
like every other catalogue here."""

PRO: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------ WARP settings
        "pro.settings": (
            "\u200f⚙️ <b>تنظیمات حرفه‌ای وایرگارد</b>\n{rule}\n"
            "این تنظیم‌ها روی <b>همه</b> فایل‌ها و لینک‌هایی که از این پس می‌گیری اعمال می‌شوند؛ "
            "لازم نیست دوباره بسازی، فقط دکمهٔ خروجی را بزن.\n\n"
            "🧬 شدت ضد فیلتر: <b>{intensity}</b>\n<i>{intensity_desc}</i>\n"
            "📦 MTU: <b>{mtu}</b>\n"
            "🌐 DNS تونل: <b>{dns}</b>\n\n"
            "💡 اگر کانفیگ وصل می‌شود اما سایت‌ها باز نمی‌شوند، MTU را «امن» بگذار؛ "
            "اگر روی اینترنت همراه یا وای‌فای فیلترینگ سخت داری، شدت را «سنگین» یا «فوق‌سنگین» کن."
        ),
        "pro.intensity_normal": "🟢 عادی",
        "pro.intensity_strong": "🟡 سنگین",
        "pro.intensity_ultra": "🔴 فوق‌سنگین",
        "pro.intensity_desc_normal": "جریان نویز استاندارد؛ مناسب اکثر اپراتورها و کم‌ترین مصرف باتری.",
        "pro.intensity_desc_strong": "بسته‌های نویز پرتراکم‌تر؛ برای دور زدن فیلترینگ تندتر روی همراه اول و ایرانسل.",
        "pro.intensity_desc_ultra": "نویز حداکثری + بستهٔ فریب QUIC (امنزیا ۱.۵ به بالا)؛ اگر دو حالت قبل پاسخ ندادند این را امتحان کن.",
        "pro.mtu_auto": "خودکار (بر اساس دستگاه)",
        "pro.mtu_safe": "امن ۱۲۸۰",
        "pro.mtu_balanced": "متعادل ۱۳۸۰",
        "pro.mtu_max": "حداکثر ۱۴۲۰",
        "pro.dns_cf": "کلادفلر ۱.۱.۱.۱",
        "pro.dns_google": "گوگل ۸.۸.۸.۸",
        "pro.dns_shecan": "شکن",
        "pro.dns_electro": "الکترو",
        "pro.dns_radar": "رادار گیم",
        "btn.wg_set": "⚙️ تنظیمات وایرگارد",
        "btn.wg_backup": "💾 پشتیبان‌گیری هویت",
        "btn.wg_restore": "📥 بازگردانی پشتیبان",
        "btn.wg_bench": "⚡ تست سرعت اندپوینت‌ها",
        "pro.backup_caption": (
            "💾 پشتیبان هویت WARP شما.\n"
            "این فایل کلید خصوصی تونل شماست — با کسی به اشتراک نگذارید.\n"
            "در هر گفتگوی دیگری با «بازگردانی پشتیبان» همین تونل را بدون ثبت‌نام مجدد برگردانید."
        ),
        "pro.backup_none": "هنوز هویتی نساخته‌ای؛ اول یک کانفیگ WARP بگیر.",
        "pro.restore_prompt": (
            "📥 فایل پشتیبان را بفرست (JSON) یا محتوایش را به‌صورت متن بفرست.\n"
            "برای لغو /cancel بزن."
        ),
        "pro.restore_ok": "✅ هویت از پشتیبان بازگردانی شد. تنظیمات شما هم برگشت.\nاندپوینت‌ها با بهترین‌های فعلی به‌روزرسانی می‌شوند.",
        "pro.restore_bad": "❌ فایل قابل قبول نبود: {reason}",
        "pro.bench_started": "⚡ تست دست‌به‌دست‌شدن واقعی روی {count} اندپوینت سالم شروع شد… حدود {secs} ثانیه.",
        "pro.bench_done": (
            "\u200f⚡ <b>نتیجهٔ تست زندهٔ اندپوینت‌ها</b>\n{rule}\n{table}\n\n"
            "✅ ترتیب اندپوینت‌های شما بر اساس پینگ واقعی همین لحظه به‌روزرسانی شد."
        ),
        "pro.bench_empty": "هیچ اندپوینتی از این شبکه جواب نداد. احتمالاً مسیر UDP همین لحظه فیلتر است؛ چند دقیقه دیگر دوباره امتحان کن یا از «اندپوینت بعدی» استفاده کن.",
        "pro.bench_no_pool": "استخر اندپوینت خالی است. اول یک اسکن انجام بده یا صبر کن موتور خودکار پرش کند.",
        # ------------------------------------------------------ admin: pro home
        "pro.admin_home": (
            "\u200f🛠 <b>کنسول مدیریت حرفه‌ای</b>\n{rule}\n"
            "🖥 مانیتور زندهٔ سرویس‌ها، 📣 ارسال هدفمند، 👥 ابزار کاربر، "
            "🛡 کنسول WARP و 🧰 پشتیبان تنظیمات — همه در همین صفحه."
        ),
        "btn.pro_console": "🛠 کنسول حرفه‌ای",
        "btn.pro_sys": "🖥 مانیتور سرویس",
        "btn.pro_selftest": "🚀 تست سلامت",
        "btn.pro_bcast": "📣 ارسال هدفمند",
        "btn.pro_users": "👥 ابزار کاربر",
        "btn.pro_wg": "🛡 کنسول WARP",
        "btn.pro_cfg": "🧰 پشتیبان تنظیمات",
        # ------------------------------------------------------------ monitor
        "pro.sys": (
            "\u200f🖥 <b>مانیتور زندهٔ سرویس</b>\n{rule}\n"
            "⏱ کارکرد این اجرا: <b>{uptime}</b>\n"
            "🧠 حافظهٔ مصرفی: <b>{mem}</b>\n"
            "🗄 حجم دیتابیس: <b>{dbsize}</b>\n"
            "👤 کاربران: <b>{users}</b> (+{today} امروز) · فعال هفته: <b>{week}</b>\n"
            "🎛 پنل‌ها: <b>{panels}</b> (سالم {healthy})\n"
            "📡 استخر IP: <b>{pool}</b> (تأییدشده {verified})\n"
            "🛡 اندپوینت وارپ: <b>{warp}</b> پایدار (سریع‌ترین {best})\n"
            "🏊 استخرها: IPv4 <b>{v4}</b> · IPv6 <b>{v6}</b>\n"
            "🤖 اتوپایلوت: {pilot} · 🧹 نگهبان: {curator}\n"
            "🎫 تیکت‌های باز: <b>{tickets}</b>\n"
            "⚙️ حالت تعمیر: {maintenance} · ساخت: {builds}"
        ),
        "pro.selftest_started": "🚀 در حال اجرای تست سلامت…",
        "pro.selftest_done": "\u200f🚀 <b>گزارش تست سلامت</b>\n{rule}\n{lines}\n\n{verdict}",
        "pro.selftest_ok": "✅ {name} — {detail}",
        "pro.selftest_fail": "❌ {name} — {detail}",
        "pro.selftest_pass": "🎉 همه‌چیز سالم است. {ok}/{total} چک سبز شد.",
        "pro.selftest_partial": "⚠️ {fail} مورد مشکل دارد ({ok}/{total} سبز). جزئیات در لیست بالا.",
        # ------------------------------------------------------- broadcast pro
        "pro.bcast": (
            "\u200f📣 <b>ارسال هدفمند</b>\n{rule}\n"
            "اول مخاطب را انتخاب کن، بعد پیام را بفرست (متن، عکس یا ویدیو). "
            "پیش‌نمایش می‌بینی و با تأیید ارسال می‌شود."
        ),
        "pro.bcast_seg_all": "👥 همه ({count})",
        "pro.bcast_seg_panel": "🎛 صاحبان پنل ({count})",
        "pro.bcast_seg_nopanel": "🚫 بدون پنل ({count})",
        "pro.bcast_seg_today": "🆕 امروز ({count})",
        "pro.bcast_seg_banned": "⛔ مسدودها ({count})",
        "pro.bcast_prompt": "📣 پیام را بفرست (متن، عکس با کپشن یا ویدیو). برای لغو /cancel بزن.",
        "pro.bcast_preview": (
            "\u200f📨 <b>پیش‌نمایش</b>\n{rule}\n"
            "مخاطب: <b>{segment}</b>\n"
            "تعداد: <b>{count}</b>\n\n"
            "همین پیام ارسال می‌شود؛ تأیید کن."
        ),
        "pro.bcast_done": "✅ ارسال کامل شد. موفق: <b>{sent}</b> · ناموفق: <b>{failed}</b>",
        "pro.bcast_cancel": "ارسال لغو شد.",
        # ------------------------------------------------------- user pro tools
        "pro.users_prompt": "👥 شناسهٔ عددی، یوزرنیم یا بخشی از نام را بفرست. برای لغو /cancel بزن.",
        "pro.users_none": "👤 کاربری پیدا نشد.",
        "pro.user_card": (
            "\u200f👤 <b>کاربر {tg}</b>\n{rule}\n"
            "نام: <b>{name}</b> · @{username}\n"
            "زبان: {lang} · اپراتور: {operator}\n"
            "پنل: {panel}\n"
            "بازسازی‌ها: {rebuilds} · ساخت‌ها: {builds}\n"
            "وایرگارد: {wg}\n"
            "وضعیت: {banned} · آخرین فعالیت: {seen}"
        ),
        "pro.wg_none": "ندارد",
        "btn.pro_force_rebuild": "🔁 بازسازی اجباری پنل",
        "btn.pro_del_panel": "🗑 حذف پنل",
        "btn.pro_dm": "✉️ پیام به کاربر",
        "btn.pro_ban": "🚫 مسدودسازی",
        "btn.pro_unban": "✅ رفع مسدودی",
        "pro.rebuild_queued": "✅ بازسازی به صف اتوپایلوت اضافه شد.",
        "pro.panel_deleted": "🗑 پنل حذف شد.",
        "pro.dm_prompt": "✉️ پیامت را بفرست تا مستقیم برای کاربر {tg} برود. /cancel برای لغو.",
        "pro.dm_sent": "✅ پیام به کاربر {tg} ارسال شد.",
        # ------------------------------------------------------- WARP console
        "pro.wg_title": (
            "\u200f🛡 <b>کنسول WARP</b>\n{rule}\n"
            "مجموع: <b>{total}</b> · پایدار: <b>{stable}</b> · سریع: <b>{fast}</b>\n"
            "IPv4: <b>{v4}</b> · IPv6: <b>{v6}</b> · دستی: <b>{manual}</b>\n"
            "سریع‌ترین: <b>{best}</b> ({best_score} امتیاز)\n"
            "میانگین اتلاف: <b>{loss}</b> · کاربران وارپ: <b>{users}</b>\n"
            "استخرها: v4 <b>{pool_v4}</b> · v6 <b>{pool_v6}</b> از {target}\n"
            "آخرین اسکن: {updated}\n\n"
            "🧪 اسکن عمیق: بررسی کامل همهٔ خانواده‌ها + اثبات عبور ترافیک (کمی طول می‌کشد)."
        ),
        "pro.wg_top": (
            "\u200f📊 <b>{count} اندپوینت برتر</b>\n{rule}\n{table}"
        ),
        "pro.wg_purged": "🧹 پاکسازی انجام شد: {retired} بازنشسته، {purged} ناسالم حذف شد.",
        "pro.wg_pub_done": "📤 فایل seed نوشته شد: {path} ({count} اندپوینت).",
        "pro.wg_pub_fail": "❌ نوشتن فایل seed ناموفق بود: {reason}",
        "btn.pro_deep_scan": "🧪 اسکن عمیق",
        "btn.pro_purge": "🧹 پاکسازی استخر",
        "btn.pro_pub_seed": "📤 انتشار seed",
        "btn.pro_wg_top": "📊 بهترین‌ها",
        # ------------------------------------------------- settings backup/restore
        "pro.cfg_title": (
            "\u200f🧰 <b>پشتیبان تنظیمات</b>\n{rule}\n"
            "📤 «خروجی JSON» همهٔ تنظیم‌های ربات (کلیدهای محرمانه ماسک می‌شوند) را می‌دهد؛ "
            "📥 «بازگردانی» فایل JSON را می‌گیرد و فقط کلیدهای مجاز را اعمال می‌کند."
        ),
        "btn.pro_cfg_export": "📤 خروجی JSON",
        "btn.pro_cfg_import": "📥 بازگردانی",
        "pro.cfg_export_caption": "🧰 تنظیمات فعلی ربات. مقادیر محرمانه ماسک شده‌اند.",
        "pro.cfg_import_prompt": "📥 فایل JSON تنظیمات را بفرست. فقط کلیدهای مجاز اعمال می‌شوند. /cancel برای لغو.",
        "pro.cfg_import_done": "✅ اعمال شد: {applied} کلید · نادیده: {skipped}.",
        "pro.cfg_import_bad": "❌ فایل نامعتبر: {reason}",
        # ------------------------------------------------------------ digest
        "pro.digest_text": (
            "\u200f📮 <b>گزارش دوره‌ای {brand}</b>\n{rule}\n"
            "👥 کاربران: <b>{users}</b> (+{today} جدید)\n"
            "🎛 پنل‌ها: <b>{panels}</b> (سالم {healthy})\n"
            "📡 استخر IP: <b>{pool}</b> (تأییدشده {verified})\n"
            "🛡 وارپ پایدار: <b>{warp}</b> · استخر v4 <b>{v4}</b> / v6 <b>{v6}</b>\n"
            "🎁 سرورهای رایگان سالم: <b>{free}</b>\n"
            "🎫 تیکت باز: <b>{tickets}</b>\n"
            "🤖 اتوپایلوت: {pilot} · 🧹 نگهبان: {curator}"
        ),
        "opt.digest": "گزارش دوره‌ای مدیریت",
        "pro.common_error": "❌ خطا: {reason}",
        # ---------------------------------------------- console additions (3.0.1)
        "pro.bcast_running": "📣 در حال ارسال به {count} کاربر…",
        "pro.users_pick": "👥 چند کاربر پیدا شد؛ یکی را انتخاب کن:",
        "pro.panel_missing": "این کاربر پنل ندارد.",
        "pro.wg_scan_running": "اسکن در حال اجراست؛ صبر کن تمام شود.",
        "pro.wg_deep_started": "🧪 اسکن عمیق شروع شد؛ نتیجه در استخر ذخیره می‌شود.",
        "pro.chk_db": "پایگاه داده",
        "pro.chk_opts": "تنظیمات",
        "pro.chk_crypto": "رمزنگاری",
        "pro.chk_pool": "استخر IP پاک",
        "pro.chk_warp": "اندپوینت‌های وارپ",
        "pro.chk_warpool": "استخرهای خانواده وارپ",
        "pro.chk_free": "سرورهای رایگان",
        "pro.chk_worker": "بستهٔ ورکر",
        "pro.chk_panels": "پنل‌های فعال",
        "pro.chk_scanner": "تازگی اسکن",
        "pro.chk_webapp": "مینی‌اپ",
    },
    "en": {
        "pro.settings": (
            "⚙️ <b>WireGuard pro settings</b>\n{rule}\n"
            "These apply to <b>every</b> file and link you export from now on - "
            "no rebuild needed, just tap an export button again.\n\n"
            "🧬 Anti-DPI intensity: <b>{intensity}</b>\n<i>{intensity_desc}</i>\n"
            "📦 MTU: <b>{mtu}</b>\n"
            "🌐 Tunnel DNS: <b>{dns}</b>\n\n"
            "💡 If the tunnel connects but pages will not load, set MTU to \"Safe\". "
            "If your carrier filters hard on mobile data or Wi-Fi, try \"Strong\" or \"Ultra\"."
        ),
        "pro.intensity_normal": "🟢 Normal",
        "pro.intensity_strong": "🟡 Strong",
        "pro.intensity_ultra": "🔴 Ultra",
        "pro.intensity_desc_normal": "Standard noise train; suits most carriers and costs the least battery.",
        "pro.intensity_desc_strong": "Denser junk packets for harder live-network filtering.",
        "pro.intensity_desc_ultra": "Maximum noise plus a QUIC-shaped decoy (AmneziaWG 1.5+); the last resort.",
        "pro.mtu_auto": "Auto (per device)",
        "pro.mtu_safe": "Safe 1280",
        "pro.mtu_balanced": "Balanced 1380",
        "pro.mtu_max": "Max 1420",
        "pro.dns_cf": "Cloudflare 1.1.1.1",
        "pro.dns_google": "Google 8.8.8.8",
        "pro.dns_shecan": "Shecan",
        "pro.dns_electro": "Electro",
        "pro.dns_radar": "Radar Game",
        "btn.wg_set": "⚙️ WireGuard settings",
        "btn.wg_backup": "💾 Identity backup",
        "btn.wg_restore": "📥 Restore backup",
        "btn.wg_bench": "⚡ Speed-test endpoints",
        "pro.backup_caption": (
            "💾 Your WARP identity backup.\n"
            "This file holds your tunnel's private key - do not share it.\n"
            "Send it to \"Restore backup\" in any other chat to rebuild the same tunnel, "
            "no re-registration needed."
        ),
        "pro.backup_none": "No identity yet; build a WARP config first.",
        "pro.restore_prompt": (
            "📥 Send the backup file (JSON) or paste its text.\n"
            "Send /cancel to stop."
        ),
        "pro.restore_ok": "✅ Identity restored from the backup, settings included. Endpoints refreshed from the current pool.",
        "pro.restore_bad": "❌ That file was rejected: {reason}",
        "pro.bench_started": "⚡ Running real handshakes against {count} healthy endpoints… about {secs}s.",
        "pro.bench_done": (
            "⚡ <b>Live endpoint benchmark</b>\n{rule}\n{table}\n\n"
            "✅ Your endpoint order now follows this real, current ping."
        ),
        "pro.bench_empty": "No endpoint answered from this network. The UDP path may be filtered right now - retry in a few minutes or use \"next endpoint\".",
        "pro.bench_no_pool": "The endpoint pool is empty. Run a scan first, or wait for the automatic engine to fill it.",
        "pro.admin_home": (
            "🛠 <b>Pro management console</b>\n{rule}\n"
            "🖥 Live service monitor, 📣 targeted broadcast, 👥 user tools, "
            "🛡 WARP console and 🧰 settings backup - all from this screen."
        ),
        "btn.pro_console": "🛠 Pro console",
        "btn.pro_sys": "🖥 Service monitor",
        "btn.pro_selftest": "🚀 Health test",
        "btn.pro_bcast": "📣 Targeted broadcast",
        "btn.pro_users": "👥 User tools",
        "btn.pro_wg": "🛡 WARP console",
        "btn.pro_cfg": "🧰 Settings backup",
        "pro.sys": (
            "🖥 <b>Live service monitor</b>\n{rule}\n"
            "⏱ Uptime: <b>{uptime}</b>\n"
            "🧠 Memory: <b>{mem}</b>\n"
            "🗄 Database size: <b>{dbsize}</b>\n"
            "👤 Users: <b>{users}</b> (+{today} today) · active week: <b>{week}</b>\n"
            "🎛 Panels: <b>{panels}</b> (healthy {healthy})\n"
            "📡 Clean IP pool: <b>{pool}</b> (verified {verified})\n"
            "🛡 WARP endpoints: <b>{warp}</b> stable (fastest {best})\n"
            "🏊 Pools: IPv4 <b>{v4}</b> · IPv6 <b>{v6}</b>\n"
            "🤖 Autopilot: {pilot} · 🧹 Curator: {curator}\n"
            "🎫 Open tickets: <b>{tickets}</b>\n"
            "⚙️ Maintenance: {maintenance} · builds: {builds}"
        ),
        "pro.selftest_started": "🚀 Running the health test…",
        "pro.selftest_done": "🚀 <b>Health test report</b>\n{rule}\n{lines}\n\n{verdict}",
        "pro.selftest_ok": "✅ {name} — {detail}",
        "pro.selftest_fail": "❌ {name} — {detail}",
        "pro.selftest_pass": "🎉 All green: {ok}/{total} checks passed.",
        "pro.selftest_partial": "⚠️ {fail} check(s) failed ({ok}/{total} green). Details above.",
        "pro.bcast": (
            "📣 <b>Targeted broadcast</b>\n{rule}\n"
            "Pick an audience first, then send the message (text, photo or video). "
            "You will see a preview and confirm before anything is sent."
        ),
        "pro.bcast_seg_all": "👥 Everyone ({count})",
        "pro.bcast_seg_panel": "🎛 Panel owners ({count})",
        "pro.bcast_seg_nopanel": "🚫 Without panel ({count})",
        "pro.bcast_seg_today": "🆕 New today ({count})",
        "pro.bcast_seg_banned": "⛔ Banned ({count})",
        "pro.bcast_prompt": "📣 Send the message now (text, photo with caption or video). /cancel to stop.",
        "pro.bcast_preview": (
            "📨 <b>Preview</b>\n{rule}\n"
            "Audience: <b>{segment}</b>\n"
            "Recipients: <b>{count}</b>\n\n"
            "This exact message goes out on confirm."
        ),
        "pro.bcast_done": "✅ Broadcast finished. Sent: <b>{sent}</b> · failed: <b>{failed}</b>",
        "pro.bcast_cancel": "Broadcast cancelled.",
        "pro.users_prompt": "👥 Send a numeric ID, @username or part of a name. /cancel to stop.",
        "pro.users_none": "👤 No user matched.",
        "pro.user_card": (
            "👤 <b>User {tg}</b>\n{rule}\n"
            "Name: <b>{name}</b> · @{username}\n"
            "Language: {lang} · operator: {operator}\n"
            "Panel: {panel}\n"
            "Rebuilds: {rebuilds} · builds: {builds}\n"
            "WireGuard: {wg}\n"
            "Status: {banned} · last seen: {seen}"
        ),
        "pro.wg_none": "none",
        "btn.pro_force_rebuild": "🔁 Force panel rebuild",
        "btn.pro_del_panel": "🗑 Delete panel",
        "btn.pro_dm": "✉️ Message user",
        "btn.pro_ban": "🚫 Ban",
        "btn.pro_unban": "✅ Unban",
        "pro.rebuild_queued": "✅ Added to the autopilot rebuild queue.",
        "pro.panel_deleted": "🗑 Panel deleted.",
        "pro.dm_prompt": "✉️ Send your message; it goes straight to user {tg}. /cancel to stop.",
        "pro.dm_sent": "✅ Delivered to user {tg}.",
        "pro.wg_title": (
            "🛡 <b>WARP console</b>\n{rule}\n"
            "Total: <b>{total}</b> · stable: <b>{stable}</b> · fast: <b>{fast}</b>\n"
            "IPv4: <b>{v4}</b> · IPv6: <b>{v6}</b> · manual: <b>{manual}</b>\n"
            "Fastest: <b>{best}</b> (score {best_score})\n"
            "Average loss: <b>{loss}</b> · WARP users: <b>{users}</b>\n"
            "Pools: v4 <b>{pool_v4}</b> · v6 <b>{pool_v6}</b> of {target}\n"
            "Last scan: {updated}\n\n"
            "🧪 Deep scan: full sweep of both families with traffic proof (takes a while)."
        ),
        "pro.wg_top": "📊 <b>Top {count} endpoints</b>\n{rule}\n{table}",
        "pro.wg_purged": "🧹 Purge done: {retired} retired, {purged} unhealthy removed.",
        "pro.wg_pub_done": "📤 Seed file written: {path} ({count} endpoints).",
        "pro.wg_pub_fail": "❌ Could not write the seed file: {reason}",
        "btn.pro_deep_scan": "🧪 Deep scan",
        "btn.pro_purge": "🧹 Purge pool",
        "btn.pro_pub_seed": "📤 Publish seed",
        "btn.pro_wg_top": "📊 Top list",
        "pro.cfg_title": (
            "🧰 <b>Settings backup</b>\n{rule}\n"
            "📤 \"Export JSON\" downloads every bot setting (secret values masked); "
            "📥 \"Restore\" accepts a JSON file and applies only whitelisted keys."
        ),
        "btn.pro_cfg_export": "📤 Export JSON",
        "btn.pro_cfg_import": "📥 Restore",
        "pro.cfg_export_caption": "🧰 Current bot settings. Secret values are masked.",
        "pro.cfg_import_prompt": "📥 Send the settings JSON file. Only whitelisted keys are applied. /cancel to stop.",
        "pro.cfg_import_done": "✅ Applied {applied} key(s) · skipped {skipped}.",
        "pro.cfg_import_bad": "❌ Invalid file: {reason}",
        "pro.digest_text": (
            "📮 <b>{brand} periodic report</b>\n{rule}\n"
            "👤 Users: <b>{users}</b> (+{today} new)\n"
            "🎛 Panels: <b>{panels}</b> (healthy {healthy})\n"
            "📡 Clean IP pool: <b>{pool}</b> (verified {verified})\n"
            "🛡 WARP stable: <b>{warp}</b> · pools v4 <b>{v4}</b> / v6 <b>{v6}</b>\n"
            "🎁 Healthy free servers: <b>{free}</b>\n"
            "🎫 Open tickets: <b>{tickets}</b>\n"
            "🤖 Autopilot: {pilot} · 🧹 Curator: {curator}"
        ),
        "opt.digest": "Scheduled admin digest",
        "pro.common_error": "❌ Error: {reason}",
        # ---------------------------------------------- console additions (3.0.1)
        "pro.bcast_running": "📣 Sending to {count} users…",
        "pro.users_pick": "👥 Several matches; pick one:",
        "pro.panel_missing": "This user has no panel.",
        "pro.wg_scan_running": "A scan is already running; wait for it to finish.",
        "pro.wg_deep_started": "🧪 Deep scan started; results land in the pool.",
        "pro.chk_db": "Database",
        "pro.chk_opts": "Options",
        "pro.chk_crypto": "Crypto",
        "pro.chk_pool": "Clean IP pool",
        "pro.chk_warp": "WARP endpoints",
        "pro.chk_warpool": "WARP family pools",
        "pro.chk_free": "Free servers",
        "pro.chk_worker": "Worker bundle",
        "pro.chk_panels": "Live panels",
        "pro.chk_scanner": "Scan freshness",
        "pro.chk_webapp": "Mini app",
    },
}
