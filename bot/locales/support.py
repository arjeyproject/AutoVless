"""Support desk copy: the user side and the admin inbox, in both languages."""

SUPPORT: dict[str, dict[str, str]] = {
    "fa": {
        # ----------------------------------------------------------- buttons
        "btn.support_new": "✍️ ارسال پیام به ادمین",
        "btn.support_thread": "🧵 گفتگوی من",
        "btn.support_direct": "🔗 تماس مستقیم",
        "btn.tickets": "📬 پیام‌های پشتیبانی",
        "btn.tickets_open": "🟠 فقط بازها",
        "btn.tickets_all": "🗂 همه گفتگوها",
        "btn.reply": "✍️ پاسخ به کاربر",
        "btn.close_ticket": "✅ بستن گفتگو",
        "btn.reopen_ticket": "♻️ باز کردن گفتگو",
        # -------------------------------------------------------- user side
        "support_menu": (
            "💬 <b>پشتیبانی</b>\n{rule}\n"
            "هر سوال، باگ یا پیشنهادی داری همینجا برای ادمین بنویس. پیامت مستقیم می‌رسد و "
            "پاسخ را داخل همین ربات می‌گیری. لازم نیست جایی بروی.\n\n"
            "🧵 وضعیت گفتگو: <b>{state}</b>\n"
            "✉️ پیام‌های ردوبدل شده: <b>{count}</b>{note}"
        ),
        "support_state_none": "شروع نشده",
        "support_state_open": "در انتطار پاسخ",
        "support_state_answered": "پاسخ داده شده",
        "support_state_closed": "بسته شده",
        "support_prompt": (
            "✍️ <b>پیام به ادمین</b>\n{rule}\n"
            "پیامت را در یک متن بنویس و بفرست. تا <b>{limit}</b> کاراکتر جا داری.\n\n"
            "💡 هر چه دقیق‌تر بنویسی زودتر حل می‌شود: اپراتور، نام برنامه و متن خطا.\n"
            "✖️ برای لغو /cancel را بزن."
        ),
        "support_too_long": "⚠️ پیام خیلی بلند است. کوتاه‌ترش کن (حداکثر {limit} کاراکتر).",
        "support_too_fast": "⏳ کمی صبر کن. هر <b>{seconds}</b> ثانیه یک پیام می‌توانی بفرستی.",
        "support_off": "🚧 پشتیبانی موقتاً بسته است. کمی بعد دوباره امتحان کن.",
        "support_sent": (
            "✅ <b>پیامت به دست ادمین رسید</b>\n{rule}\n"
            "🎫 شماره گفتگو: <code>{ticket}</code>\n\n"
            "پاسخ را همینجا در ربات دریافت می‌کنی؛ لازم نیست دوباره بفرستی."
        ),
        "support_no_admin": "⚠️ پیامت ذخیره شد ولی الان نتوانستم به ادمین اطلاع بدهم. به محض برگشتنش می‌بیند.",
        "support_thread": "🧵 <b>گفتگوی شماره {ticket}</b>\n{rule}\n{list}",
        "support_thread_empty": "📭 هنوز پیامی به پشتیبانی نفرستاده‌ای.",
        "support_you": "👤 تو",
        "support_admin": "🛠 پشتیبانی",
        "support_incoming": (
            "📩 <b>پاسخ پشتیبانی</b>\n{rule}\n{body}\n\n"
            "🎫 گفتگو: <code>{ticket}</code>"
        ),
        "support_closed_user": (
            "🔒 گفتگوی <code>{ticket}</code> بسته شد.\n"
            "اگر باز هم مشکلی داشتی یک پیام جدید بفرست."
        ),
        # ------------------------------------------------------- admin side
        "support.list": (
            "📬 <b>میز پشتیبانی</b>\n{rule}\n"
            "🟠 باز: <b>{open}</b> · ✅ پاسخ‌داده: <b>{answered}</b> · 🔒 بسته: <b>{closed}</b>\n"
            "🔔 منتطر پاسخ تو: <b>{waiting}</b>\n\n{list}"
        ),
        "support.list_empty": "فعلاً پیامی در این فهرست نیست.",
        "support.card": (
            "🎫 <b>گفتگو {ticket}</b>\n{rule}\n"
            "👤 {name} · {username}\n"
            "🆔 <code>{tg_id}</code>\n"
            "📌 وضعیت: <b>{state}</b> · 🕒 {updated}\n{rule}\n{list}"
        ),
        "support.reply_prompt": (
            "✍️ پاسخت را برای <b>{name}</b> بنویس. تگ‌های HTML مجاز است.\n"
            "پیام در همین ربات برای او ارسال می‌شود.\n✖️ لغو: /cancel"
        ),
        "support.reply_sent": "✅ پاسخ برای <b>{name}</b> ارسال شد.",
        "support.reply_failed": "❌ نتوانستم پیام را برسانم: <code>{reason}</code>",
        "support.new_ticket": (
            "📨 <b>پیام جدید پشتیبانی</b>\n{rule}\n"
            "👤 {name} · {username}\n"
            "🆔 <code>{tg_id}</code>\n"
            "🎫 گفتگو: <code>{ticket}</code>\n{rule}\n{body}"
        ),
        "support.closed": "🔒 گفتگو بسته شد.",
        "support.reopened": "♻️ گفتگو دوباره باز شد.",
        "support.gone": "این گفتگو پیدا نشد.",
        "support.toggle_on": "🔔 پشتیبانی: روشن",
        "support.toggle_off": "🔕 پشتیبانی: خاموش",
        "support.empty_body": "⚠️ متن خالی است.",
    },
    "en": {
        # ----------------------------------------------------------- buttons
        "btn.support_new": "✍️ Message the admin",
        "btn.support_thread": "🧵 My conversation",
        "btn.support_direct": "🔗 Direct contact",
        "btn.tickets": "📬 Support inbox",
        "btn.tickets_open": "🟠 Open only",
        "btn.tickets_all": "🗂 All threads",
        "btn.reply": "✍️ Reply to user",
        "btn.close_ticket": "✅ Close thread",
        "btn.reopen_ticket": "♻️ Reopen thread",
        # -------------------------------------------------------- user side
        "support_menu": (
            "💬 <b>Support</b>\n{rule}\n"
            "Any question, bug or idea: write it to the admin right here. It lands directly with them "
            "and the answer comes back inside this bot.\n\n"
            "🧵 Thread status: <b>{state}</b>\n"
            "✉️ Messages exchanged: <b>{count}</b>{note}"
        ),
        "support_state_none": "not started",
        "support_state_open": "waiting for a reply",
        "support_state_answered": "answered",
        "support_state_closed": "closed",
        "support_prompt": (
            "✍️ <b>Message the admin</b>\n{rule}\n"
            "Write it in one message and send. Up to <b>{limit}</b> characters.\n\n"
            "💡 The more precise, the faster it gets fixed: operator, app name, exact error.\n"
            "✖️ Send /cancel to abort."
        ),
        "support_too_long": "⚠️ That is too long. Trim it down ({limit} characters max).",
        "support_too_fast": "⏳ Slow down. One message every <b>{seconds}</b> seconds.",
        "support_off": "🚧 Support is closed for now. Try again a bit later.",
        "support_sent": (
            "✅ <b>Your message reached the admin</b>\n{rule}\n"
            "🎫 Thread: <code>{ticket}</code>\n\n"
            "The reply arrives here in the bot, no need to send it again."
        ),
        "support_no_admin": "⚠️ Saved, but I could not ping the admin right now. They will see it as soon as they are back.",
        "support_thread": "🧵 <b>Thread {ticket}</b>\n{rule}\n{list}",
        "support_thread_empty": "📭 You have not written to support yet.",
        "support_you": "👤 You",
        "support_admin": "🛠 Support",
        "support_incoming": (
            "📩 <b>Reply from support</b>\n{rule}\n{body}\n\n"
            "🎫 Thread: <code>{ticket}</code>"
        ),
        "support_closed_user": (
            "🔒 Thread <code>{ticket}</code> was closed.\n"
            "Send a new message any time something else comes up."
        ),
        # ------------------------------------------------------- admin side
        "support.list": (
            "📬 <b>Support desk</b>\n{rule}\n"
            "🟠 Open: <b>{open}</b> · ✅ Answered: <b>{answered}</b> · 🔒 Closed: <b>{closed}</b>\n"
            "🔔 Waiting on you: <b>{waiting}</b>\n\n{list}"
        ),
        "support.list_empty": "Nothing in this list yet.",
        "support.card": (
            "🎫 <b>Thread {ticket}</b>\n{rule}\n"
            "👤 {name} · {username}\n"
            "🆔 <code>{tg_id}</code>\n"
            "📌 Status: <b>{state}</b> · 🕒 {updated}\n{rule}\n{list}"
        ),
        "support.reply_prompt": (
            "✍️ Write your reply to <b>{name}</b>. HTML tags are allowed.\n"
            "It is delivered to them inside this bot.\n✖️ Cancel: /cancel"
        ),
        "support.reply_sent": "✅ Reply delivered to <b>{name}</b>.",
        "support.reply_failed": "❌ I could not deliver it: <code>{reason}</code>",
        "support.new_ticket": (
            "📨 <b>New support message</b>\n{rule}\n"
            "👤 {name} · {username}\n"
            "🆔 <code>{tg_id}</code>\n"
            "🎫 Thread: <code>{ticket}</code>\n{rule}\n{body}"
        ),
        "support.closed": "🔒 Thread closed.",
        "support.reopened": "♻️ Thread reopened.",
        "support.gone": "That thread is gone.",
        "support.toggle_on": "🔔 Support: on",
        "support.toggle_off": "🔕 Support: off",
        "support.empty_body": "⚠️ The text is empty.",
    },
}
