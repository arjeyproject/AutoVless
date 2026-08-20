"""Bilingual copy. Persian is the default, English is a full peer."""

from __future__ import annotations

from typing import Any

LANGS = ("fa", "en")
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
RULE = "━━━━━━━━━━━━━━"


def num(value: Any, lang: str) -> str:
    """Render digits in the reader's own numerals."""
    text = str(value)
    return text.translate(_PERSIAN_DIGITS) if lang == "fa" else text


TEXTS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ main menu
    "main_menu": {
        "fa": (
            "⚡ <b>{brand}</b> · نسخه توربو ⚡\n"
            "{rule}\n"
            "👋 سلام <b>{name}</b> جان!\n"
            "من روی اکانت کلادفلر خودت یک پنل اختصاصی می‌سازم و سریع‌ترین آی‌پی‌های تمیز را "
            "به صورت خودکار سوار کانفیگ‌هایت می‌کنم.\n\n"
            "🔥 <b>موتور زنده این لحظه</b>\n"
            "📡 آی‌پی تمیز آماده: <b>{pool}</b>\n"
            "🚀 زیر ۷۰۰ میلی‌ثانیه: <b>{fast}</b>\n"
            "🏆 بهترین پینگ: <b>{best}</b>\n"
            "🛡 رله‌های سالم: <b>{healthy}</b>\n\n"
            "👇 از دکمه‌های پایین شروع کن:"
        ),
        "en": (
            "⚡ <b>{brand}</b> · turbo build ⚡\n"
            "{rule}\n"
            "👋 Hey <b>{name}</b>!\n"
            "I build a private panel on your own Cloudflare account and mount the fastest clean IPs "
            "on your configs automatically.\n\n"
            "🔥 <b>Live engine</b>\n"
            "📡 Clean IPs ready: <b>{pool}</b>\n"
            "🚀 Under 700 ms: <b>{fast}</b>\n"
            "🏆 Best ping: <b>{best}</b>\n"
            "🛡 Healthy relays: <b>{healthy}</b>\n\n"
            "👇 Pick an option:"
        ),
    },
    "welcome_note": {
        "fa": (
            "🌱 <b>{brand}</b> رایگان است و برای دسترسی آزاد مردم به اینترنت ساخته شده.\n"
            "هیچ چیزی از تو نمی‌خواهیم؛ فقط اگر کار کرد، به یک نفر دیگر هم معرفی‌اش کن. ❤️"
        ),
        "en": (
            "🌱 <b>{brand}</b> is free and built so people can reach an open internet.\n"
            "We ask for nothing. If it works for you, pass it to one more person. ❤️"
        ),
    },
    "support_us": {
        "fa": (
            "❤️ <b>حمایت از ما</b>\n{rule}\n"
            "{brand} کاملاً رایگان است و هیچ فروش اشتراکی ندارد.\n\n"
            "• ربات را به دوستانت معرفی کن\n"
            "• به پروژه در گیت‌هاب ستاره بده\n"
            "• باگ یا پیشنهادت را به پشتیبانی بگو\n\n"
            "🍊 هر کانفیگی که به دست یک نفر دیگر برسانی، یک پنجره تازه باز کرده‌ای."
        ),
        "en": (
            "❤️ <b>Support us</b>\n{rule}\n"
            "{brand} is free and sells nothing.\n\n"
            "• Share the bot with a friend\n"
            "• Star the project on GitHub\n"
            "• Send bugs and ideas to support\n\n"
            "🍊 Every config you pass on opens one more window."
        ),
    },
    # ---------------------------------------------------------------- build
    "token_intro": {
        "fa": (
            "🚀 <b>ساخت پنل توربو</b>\n{rule}\n"
            "1️⃣ اگر اکانت کلادفلر نداری، اول <b>ثبت نام</b> کن.\n"
            "2️⃣ دکمه <b>دریافت توکن کلادفلر</b> را بزن (دسترسی‌ها از قبل انتخاب شده‌اند).\n"
            "3️⃣ در کلادفلر <code>Continue to summary</code> و بعد <code>Create Token</code>.\n"
            "4️⃣ توکن را کپی کن و همینجا بفرست.\n\n"
            "🔒 توکن فقط روی اکانت خودت کار می‌کند و تنها برای ساخت ورکر لازم است.\n"
            "⏱ میانگین زمان تحویل: ۲۰ تا ۴۵ ثانیه ⚡"
        ),
        "en": (
            "🚀 <b>Build a turbo panel</b>\n{rule}\n"
            "1️⃣ No Cloudflare account yet? <b>Sign up</b> first.\n"
            "2️⃣ Tap <b>Get Cloudflare token</b> (permissions are pre-selected).\n"
            "3️⃣ In Cloudflare press <code>Continue to summary</code>, then <code>Create Token</code>.\n"
            "4️⃣ Copy the token and paste it right here.\n\n"
            "🔒 The token only works on your own account and is only used to create the Worker.\n"
            "⏱ Typical delivery time: 20 to 45 seconds ⚡"
        ),
    },
    "token_bad_format": {
        "fa": "⚠️ این متن شبیه توکن کلادفلر نیست. فقط خود توکن را بفرست، بدون لینک یا توضیح اضافه.",
        "en": "⚠️ That does not look like a Cloudflare token. Send the token only, without links or extra text.",
    },
    "token_rejected": {
        "fa": (
            "❌ کلادفلر این توکن را قبول نکرد.\n\n<b>دلیل:</b> <code>{reason}</code>\n\n"
            "دوباره از دکمه «دریافت توکن کلادفلر» استفاده کن تا دسترسی‌ها درست تنظیم شوند."
        ),
        "en": (
            "❌ Cloudflare rejected this token.\n\n<b>Reason:</b> <code>{reason}</code>\n\n"
            "Use the “Get Cloudflare token” button again so the permissions are set correctly."
        ),
    },
    "build_progress": {
        "fa": "⚙️ <b>در حال ساخت پنل</b>\n{rule}\n{steps}",
        "en": "⚙️ <b>Building your panel</b>\n{rule}\n{steps}",
    },
    "step_verify": {"fa": "بررسی توکن و اکانت", "en": "Verifying token and account"},
    "step_subdomain": {"fa": "آماده‌سازی دامنه workers.dev", "en": "Preparing the workers.dev subdomain"},
    "step_scan": {"fa": "انتخاب آی‌پی تمیز", "en": "Selecting clean IPs"},
    "step_deploy": {"fa": "آپلود ورکر روی اکانت تو", "en": "Uploading the Worker to your account"},
    "step_health": {"fa": "تست سلامت پنل", "en": "Health checking the panel"},
    "no_clean_ip": {
        "fa": "⏳ استخر آی‌پی تمیز خالی است و اسکنر تازه شروع کرده. یک دقیقه دیگر دوباره امتحان کن.",
        "en": "⏳ The clean IP pool is still warming up. Try again in about a minute.",
    },
    "panel_ready": {
        "fa": (
            "🎉 <b>پنل تو آماده شد!</b> 🚀\n{rule}\n"
            "⏱ زمان ساخت: <b>{seconds}</b> ثانیه\n"
            "🏆 بهترین پینگ: <b>{best}</b>\n"
            "🚀 زیر ۷۰۰ms: <b>{fast}</b> اندپوینت\n"
            "📦 تعداد کانفیگ: <b>{count}</b>\n"
            "🧪 پروتکل: <b>VLESS / WS</b>\n"
            "🔌 پورت‌ها: <b>{ports}</b>\n"
            "📶 اپراتور: <b>{operator}</b>\n"
            "🌐 میزبان: <code>{host}</code>\n\n"
            "💡 در کلاینت <b>Real Delay</b> بگیر و سریع‌ترین را انتخاب کن.\n"
            "🔥 گزینه <b>Fragment</b> را روشن کن تا اتصال پایدارتر شود."
        ),
        "en": (
            "🎉 <b>Your panel is ready!</b> 🚀\n{rule}\n"
            "⏱ Build time: <b>{seconds}</b> s\n"
            "🏆 Best ping: <b>{best}</b>\n"
            "🚀 Under 700 ms: <b>{fast}</b> endpoints\n"
            "📦 Configs: <b>{count}</b>\n"
            "🧪 Protocol: <b>VLESS / WS</b>\n"
            "🔌 Ports: <b>{ports}</b>\n"
            "📶 Operator: <b>{operator}</b>\n"
            "🌐 Host: <code>{host}</code>\n\n"
            "💡 Run <b>Real Delay</b> in your client and pick the fastest entry.\n"
            "🔥 Turn <b>Fragment</b> on for a steadier connection."
        ),
    },
    "health_warn": {
        "fa": "⚠️ ورکر ساخته شد ولی هنوز جواب نمی‌دهد. انتشار روی لبه کلادفلر تا یک دقیقه طول می‌کشد؛ بعد از آن کانفیگ‌ها بالا می‌آیند.",
        "en": "⚠️ The Worker was created but is not answering yet. Cloudflare edge propagation can take up to a minute, then the configs come alive.",
    },
    "panel_none": {
        "fa": "📭 هنوز پنلی نساخته‌ای. از دکمه «ساخت پنل توربو» شروع کن.",
        "en": "📭 No panel yet. Start from “Build turbo panel”.",
    },
    "panel_overview": {
        "fa": (
            "🎛 <b>مدیریت پنل من</b>\n{rule}\n"
            "🌐 میزبان: <code>{host}</code>\n"
            "🆔 شناسه کاربر: <code>{uuid}</code>\n"
            "📦 کانفیگ‌ها: <b>{count}</b>\n"
            "🏆 بهترین پینگ: <b>{best}</b>\n"
            "🔄 تعداد بازسازی: <b>{rebuilds}</b>\n"
            "🕒 آخرین به‌روزرسانی: <b>{updated}</b>"
        ),
        "en": (
            "🎛 <b>My panel</b>\n{rule}\n"
            "🌐 Host: <code>{host}</code>\n"
            "🆔 User id: <code>{uuid}</code>\n"
            "📦 Configs: <b>{count}</b>\n"
            "🏆 Best ping: <b>{best}</b>\n"
            "🔄 Rebuilds: <b>{rebuilds}</b>\n"
            "🕒 Updated: <b>{updated}</b>"
        ),
    },
    "sub_links": {
        "fa": (
            "🔗 <b>لینک اشتراک</b>\n{rule}\n"
            "<b>v2rayNG / Streisand / NekoBox</b>\n<code>{sub}</code>\n\n"
            "<b>Clash / Mihomo</b>\n<code>{clash}</code>\n\n"
            "<b>sing-box</b>\n<code>{singbox}</code>\n\n"
            "♻️ لینک ثابت است و بعد از هر بازسازی خودبه‌خود به‌روز می‌شود."
        ),
        "en": (
            "🔗 <b>Subscription links</b>\n{rule}\n"
            "<b>v2rayNG / Streisand / NekoBox</b>\n<code>{sub}</code>\n\n"
            "<b>Clash / Mihomo</b>\n<code>{clash}</code>\n\n"
            "<b>sing-box</b>\n<code>{singbox}</code>\n\n"
            "♻️ The link is permanent and refreshes after every rebuild."
        ),
    },
    "single_configs": {
        "fa": "📝 <b>کانفیگ‌های تکی</b>\n{rule}\nروی هر کانفیگ بزن تا کپی شود.",
        "en": "📝 <b>Individual configs</b>\n{rule}\nTap a config to copy it.",
    },
    "qr_caption": {
        "fa": "📷 بارکد لینک اشتراک {brand}",
        "en": "📷 {brand} subscription QR code",
    },
    "ping_result": {
        "fa": (
            "📡 <b>تست پینگ زنده</b>\n{rule}\n{rows}\n\n"
            "ℹ️ این عددها از سرور ربات گرفته شده‌اند. پینگ واقعی خودت را در کلاینت بگیر."
        ),
        "en": (
            "📡 <b>Live ping test</b>\n{rule}\n{rows}\n\n"
            "ℹ️ Measured from the bot server. Check real delay in your own client as well."
        ),
    },
    "delete_confirm": {
        "fa": "🗑 مطمئنی؟ ورکر <code>{script}</code> از اکانت کلادفلر تو پاک می‌شود و کانفیگ‌ها از کار می‌افتند.",
        "en": "🗑 Are you sure? Worker <code>{script}</code> will be removed from your Cloudflare account and the configs will stop working.",
    },
    "deleted": {"fa": "✅ پنل حذف شد.", "en": "✅ Panel deleted."},
    "rebuilding": {"fa": "♻️ دارم آی‌پی‌های تازه را سوار می‌کنم...", "en": "♻️ Mounting fresh clean IPs..."},
    "rebuilt": {"fa": "✅ پنل با آی‌پی‌های تازه به‌روز شد.", "en": "✅ Panel updated with fresh clean IPs."},
    "token_missing": {
        "fa": "🔑 برای این کار باید دوباره توکن کلادفلرت را بفرستی. همین الان بفرست.",
        "en": "🔑 I need your Cloudflare token again for this. Send it now.",
    },
    "scan_started": {
        "fa": "⚡ اسکن تازه شروع شد، چند لحظه صبر کن...",
        "en": "⚡ A fresh scan started, hold on a moment...",
    },
    # ----------------------------------------------------------------- info
    "network_status": {
        "fa": (
            "📊 <b>وضعیت زنده شبکه</b>\n{rule}\n"
            "📡 استخر آی‌پی: <b>{total}</b>\n"
            "✅ تاییدشده: <b>{verified}</b>\n"
            "🚀 زیر ۷۰۰ms: <b>{fast}</b>\n"
            "🏆 بهترین پینگ: <b>{best}</b>\n"
            "🔌 پورت‌های فعال: <b>{ports}</b>\n"
            "⏳ آخرین اسکن: <b>{updated}</b>\n"
            "⚙️ وضعیت اسکنر: <b>{state}</b>\n\n"
            "📍 دیتاسنترهای برتر: {colos}"
        ),
        "en": (
            "📊 <b>Live network status</b>\n{rule}\n"
            "📡 IP pool: <b>{total}</b>\n"
            "✅ Verified: <b>{verified}</b>\n"
            "🚀 Under 700 ms: <b>{fast}</b>\n"
            "🏆 Best ping: <b>{best}</b>\n"
            "🔌 Active ports: <b>{ports}</b>\n"
            "⏳ Last scan: <b>{updated}</b>\n"
            "⚙️ Scanner: <b>{state}</b>\n\n"
            "📍 Top datacenters: {colos}"
        ),
    },
    "apps": {
        "fa": (
            "📱 <b>برنامه‌ها و لینک دانلود</b>\n{rule}\n"
            "• <b>اندروید:</b> v2rayNG · NekoBox · Hiddify\n"
            "• <b>آی‌اواس:</b> Streisand · Shadowrocket · FoXray\n"
            "• <b>ویندوز:</b> v2rayN · Hiddify · Nekoray\n"
            "• <b>مک:</b> V2Box · Streisand · Hiddify\n\n"
            "💡 لینک اشتراک را در بخش Subscription برنامه وارد کن، نه در بخش کانفیگ دستی."
        ),
        "en": (
            "📱 <b>Apps and downloads</b>\n{rule}\n"
            "• <b>Android:</b> v2rayNG · NekoBox · Hiddify\n"
            "• <b>iOS:</b> Streisand · Shadowrocket · FoXray\n"
            "• <b>Windows:</b> v2rayN · Hiddify · Nekoray\n"
            "• <b>macOS:</b> V2Box · Streisand · Hiddify\n\n"
            "💡 Paste the subscription link into the app's Subscription section, not the manual config field."
        ),
    },
    "guide": {
        "fa": (
            "📖 <b>راهنمای اتصال</b>\n{rule}\n"
            "1️⃣ یکی از برنامه‌های معرفی‌شده را نصب کن.\n"
            "2️⃣ لینک اشتراک را در بخش Subscription اضافه کن و Update بزن.\n"
            "3️⃣ تست تاخیر (Real Delay) بگیر و سریع‌ترین کانفیگ را انتخاب کن.\n"
            "4️⃣ اگر وصل نشد: Fragment را روشن کن، بعد کانفیگ پورت ۸۰ را امتحان کن.\n