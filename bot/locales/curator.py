"""Copy for the pool curator: its block on the engine screen and its controls."""

CURATOR: dict[str, dict[str, str]] = {
    "fa": {
        "admin.curator": (
            "🧹 <b>نگهبان استخر</b>\n"
            "وضعیت: <b>{state}</b> · هر <b>{interval}</b> ثانیه\n"
            "آخرین دور: بررسی <b>{checked}</b> · سالم <b>{kept}</b> · حذف‌شده <b>{dropped}</b>\n"
            "اعمال روی پنل کاربران: <b>{pushed}</b> · رله حذف‌شده: <b>{relays}</b>\n"
            "آی‌پی تازه: <b>{fresh}</b> از <b>{verified}</b> تاییدشده · هدف هر پورت: <b>{target}</b>\n"
            "پورت‌های کم‌عمق: <b>{thin}</b>\n"
            "قانون حذف: <b>{strikes}</b> خطای پشت‌سرهم یا اعتبار زیر <b>{floor}</b>\n"
            "مجموع حذف‌شده‌ها تا حالا: <b>{total}</b>"
        ),
        "admin.curate_started": "🧹 پاکسازی استخر شروع شد، چند لحظه طول می‌کشد...",
        "admin.curate_done": (
            "✅ یک دور پاکسازی تمام شد.\n"
            "بررسی: <b>{checked}</b> · سالم: <b>{kept}</b>\n"
            "حذف قطعی: <b>{dropped}</b> آی‌پی · رله: <b>{relays}</b>\n"
            "پنل‌های به‌روزشده: <b>{pushed}</b> · آی‌پی تازه‌ی اضافه‌شده: <b>{grown}</b>"
        ),
        "admin.curate_idle": "⏳ نگهبان همین حالا مشغول است یا خاموش شده.",
        "btn.curate": "🧹 پاکسازی و رشد استخر",
        "opt.curator": "حذف خودکار آی‌پی‌های مرده",
    },
    "en": {
        "admin.curator": (
            "🧹 <b>Pool curator</b>\n"
            "State: <b>{state}</b> · every <b>{interval}</b> s\n"
            "Last cycle: checked <b>{checked}</b> · kept <b>{kept}</b> · deleted <b>{dropped}</b>\n"
            "Panels re-pointed: <b>{pushed}</b> · relays deleted: <b>{relays}</b>\n"
            "Fresh IPs: <b>{fresh}</b> of <b>{verified}</b> verified · target per port: <b>{target}</b>\n"
            "Thin ports: <b>{thin}</b>\n"
            "Delete rule: <b>{strikes}</b> misses in a row, or reliability under <b>{floor}</b>\n"
            "Deleted all time: <b>{total}</b>"
        ),
        "admin.curate_started": "🧹 Curation pass started, this takes a moment...",
        "admin.curate_done": (
            "✅ Curation pass finished.\n"
            "Checked: <b>{checked}</b> · kept: <b>{kept}</b>\n"
            "Deleted: <b>{dropped}</b> IPs · relays: <b>{relays}</b>\n"
            "Panels refreshed: <b>{pushed}</b> · fresh IPs added: <b>{grown}</b>"
        ),
        "admin.curate_idle": "⏳ The curator is already running, or switched off.",
        "btn.curate": "🧹 Curate and grow the pool",
        "opt.curator": "Auto-delete dead IPs",
    },
}
