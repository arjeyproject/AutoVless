"""Strings for the paid entry gate, its admin screen, and the iPhone WARP path."""

AMNEZIAWG_IOS_URL = "https://apps.apple.com/app/amneziawg/id6478942365"
WIREGUARD_IOS_URL = "https://apps.apple.com/app/wireguard/id1441195209"
HIDDIFY_IOS_URL = "https://apps.apple.com/app/hiddify-proxy-vpn/id6596777532"

PAYMENT = {
    "fa": {
        # ---------------------------------------------------------- the gate
        "pay.gate": (
            "\U0001f510 <b>ورود به {brand}</b>\n{rule}\n"
            "برای استفاده از ربات، یک‌بار پرداخت لازم است.\n\n"
            "\U0001f4b0 مبلغ: <b>{price}</b>\n"
            "\u23f3 اعتبار: <b>{period}</b>\n\n"
            "روش پرداخت را انتخاب کن. بعد از پرداخت، ربات <b>خودکار</b> برایت باز می‌شود "
            "و نیازی به ارسال رسید نیست."
        ),
        "pay.price_toman": "{amount} تومان",
        "pay.price_stars": "{stars} \u2b50\ufe0f استارز",
        "pay.or": " یا ",
        "pay.period_forever": "دائمی",
        "pay.period_days": "{days} روز",
        "pay.no_gateway": (
            "\u26a0\ufe0f درگاه پرداخت هنوز توسط مدیر تنظیم نشده است. "
            "کمی بعد دوباره امتحان کن یا با پشتیبانی در تماس باش."
        ),
        "pay.zp_link": (
            "\U0001f4b3 <b>لینک پرداخت آماده است</b>\n{rule}\n"
            "مبلغ: <b>{price}</b>\n\n"
            "روی دکمه‌ی زیر بزن، پرداخت را کامل کن و بعد به ربات برگرد. "
            "تأیید پرداخت کاملاً خودکار است."
        ),
        "pay.failed": "\u274c ساخت پرداخت ممکن نشد: <code>{reason}</code>",
        "pay.stars_title": "اشتراک {brand}",
        "pay.stars_desc": "دسترسی {period} به همه‌ی امکانات {brand}",
        "pay.stars_label": "اشتراک",
        "pay.done": (
            "\u2705 <b>پرداخت تأیید شد!</b>\n{rule}\n"
            "کد پیگیری: <code>{ref}</code>\n"
            "اعتبار: <b>{until}</b>\n\n"
            "همه‌ی امکانات ربات برایت باز شد. \U0001f389"
        ),
        "pay.pending": (
            "\u23f3 هنوز پرداخت تأییدشده‌ای برایت ثبت نشده. "
            "اگر همین الان پرداخت کردی، چند ثانیه دیگر دوباره بزن."
        ),
        "pay.active": "\u2705 اشتراک تو فعال است \u00b7 {until}",
        "pay.until_forever": "دائمی",
        "pay.until": "تا {date}",
        "pay.precheckout_bad": "این فاکتور منقضی شده. لطفاً از داخل ربات دوباره پرداخت کن.",
        "btn.pay_zp": "\U0001f4b3 پرداخت آنلاین (کارت بانکی)",
        "btn.pay_stars": "\u2b50\ufe0f پرداخت با استارز تلگرام",
        "btn.pay_check": "\U0001f504 پرداخت کردم، بررسی کن",
        "btn.pay_open": "\U0001f4b3 رفتن به درگاه پرداخت",
        "btn.pay_support": "\U0001f4ac پشتیبانی",
        "btn.pay_menu": "\U0001f3e0 منوی اصلی",
        # ------------------------------------------------------------- admin
        "btn.pay_admin": "\U0001f4b3 درگاه پرداخت",
        "admin.pay": (
            "\U0001f4b3 <b>درگاه پرداخت ورود</b>\n{rule}\n"
            "وضعیت: <b>{state}</b>\n"
            "درگاه: <b>{gateway}</b>\n"
            "مبلغ (زرین‌پال): <b>{amount}</b> تومان\n"
            "مبلغ (استارز): <b>{stars}</b> \u2b50\ufe0f\n"
            "اعتبار هر پرداخت: <b>{period}</b>\n"
            "مرچنت زرین‌پال: <code>{merchant}</code>\n"
            "حالت تست (سندباکس): <b>{sandbox}</b>\n"
            "آدرس بازگشت: <code>{callback}</code>\n"
            "{rule}\n"
            "\U0001f465 مشترک فعال: <b>{active}</b> از {subscribers}\n"
            "\U0001f4b0 درآمد: <b>{toman}</b> تومان \u00b7 <b>{earned}</b> \u2b50\ufe0f\n"
            "\u2705 پرداخت موفق: <b>{paid}</b> \u00b7 \u23f3 در انتظار: <b>{pending}</b>"
            "{warning}"
        ),
        "admin.pay_warn_zp": (
            "\n\n\u26a0\ufe0f برای زرین‌پال باید <code>PUBLIC_URL</code> (با https) روی سرور تنظیم "
            "شده باشد و مرچنت وارد شده باشد."
        ),
        "admin.pay_warn_none": "\n\n\u26a0\ufe0f هیچ روش پرداخت فعالی تنظیم نشده؛ کاربران پیام «درگاه تنظیم نشده» می‌بینند.",
        "admin.pay_gw_stars": "استارز تلگرام",
        "admin.pay_gw_zarinpal": "زرین‌پال",
        "admin.pay_gw_both": "هر دو",
        "btn.pay_toggle": "\U0001f512 روشن / خاموش",
        "btn.pay_gw": "\U0001f500 تغییر درگاه",
        "btn.pay_amount": "\U0001f4b0 مبلغ تومان",
        "btn.pay_stars_price": "\u2b50\ufe0f مبلغ استارز",
        "btn.pay_days": "\u23f3 مدت اعتبار",
        "btn.pay_merchant": "\U0001f511 مرچنت زرین‌پال",
        "btn.pay_sandbox": "\U0001f9ea حالت تست",
        "btn.pay_grant": "\u2795 فعال‌سازی دستی",
        "btn.pay_revoke": "\u2796 لغو اشتراک",
        "btn.pay_list": "\U0001f9fe پرداخت‌های اخیر",
        "admin.pay_prompt_amount": "مبلغ ورود را به <b>تومان</b> بفرست (مثلاً <code>50000</code>):",
        "admin.pay_prompt_stars": "قیمت را به <b>استارز</b> بفرست (مثلاً <code>100</code>):",
        "admin.pay_prompt_days": "مدت اعتبار هر پرداخت را به <b>روز</b> بفرست. <code>0</code> یعنی دائمی:",
        "admin.pay_prompt_merchant": (
            "مرچنت‌کد زرین‌پال را بفرست (۳۶ کاراکتر، از پنل zarinpal.com). "
            "برای پاک کردن <code>-</code> بفرست:"
        ),
        "admin.pay_prompt_grant": (
            "آیدی عددی کاربر را بفرست. اختیاری: بعد از فاصله تعداد روز "
            "(مثلاً <code>123456789 30</code>):"
        ),
        "admin.pay_prompt_revoke": "آیدی عددی کاربری که اشتراکش لغو شود را بفرست:",
        "admin.pay_bad_number": "\u274c یک عدد معتبر بفرست.",
        "admin.pay_bad_merchant": "\u274c مرچنت معتبر نیست؛ باید ۳۶ کاراکتر به شکل UUID باشد.",
        "admin.pay_saved": "\u2705 ذخیره شد.",
        "admin.pay_granted": "\u2705 کاربر <code>{user}</code> فعال شد \u00b7 {until}",
        "admin.pay_revoked": "\u2705 اشتراک <code>{user}</code> لغو شد.",
        "admin.pay_revoke_none": "این کاربر اشتراکی نداشت.",
        "admin.pay_list": "\U0001f9fe <b>پرداخت‌های اخیر</b>\n{rule}\n{list}",
        "admin.pay_list_empty": "هنوز پرداختی ثبت نشده.",
        "pay.user_granted": "\U0001f389 اشتراک تو توسط مدیر فعال شد \u00b7 {until}",
        # ------------------------------------------------------- iPhone WARP
        "wg.ios_awg_caption": (
            "\U0001f34f <b>مخصوص آیفون / مک \u2014 روش پیشنهادی</b>\n"
            "این فایل را در اپ <b>AmneziaWG</b> (رایگان در App Store) باز کن. "
            "مبهم‌سازی دارد و فیلترینگ دست‌دادن وایرگارد را دور می‌زند."
        ),
        "wg.ios_plain_caption": (
            "\U0001f4c4 نسخه‌ی استاندارد برای اپ رسمی <b>WireGuard</b>. "
            "روی بعضی اپراتورها دست‌دادن آن فیلتر می‌شود؛ اگر وصل شد ولی چیزی باز نشد، "
            "فایل AmneziaWG بالا را استفاده کن."
        ),
        "wg.ios_guide": (
            "\U0001f34f <b>راه‌اندازی وایرگارد روی آیفون</b>\n{rule}\n"
            "۱) اپ <a href=\"" + AMNEZIAWG_IOS_URL + "\">AmneziaWG</a> را از App Store نصب کن.\n"
            "۲) فایل <b>AmneziaWG</b> بالا را لمس کن \u2192 Share \u2192 AmneziaWG.\n"
            "   یا در اپ: + \u2192 Import from file.\n"
            "۳) تونل را روشن کن. \u2705\n\n"
            "\U0001f501 راه دوم: اپ <a href=\"" + HIDDIFY_IOS_URL + "\">Hiddify</a> \u2014 "
            "لینک زیر را کپی کن و در Hiddify با «+ \u2192 Add from clipboard» اضافه کن. "
            "نویز ضدفیلتر خودش روی آن فعال است:\n"
            "<code>{hiddify}</code>\n\n"
            "\u26a0\ufe0f اپ رسمی <a href=\"" + WIREGUARD_IOS_URL + "\">WireGuard</a> مبهم‌سازی ندارد؛ "
            "فقط وقتی از آن استفاده کن که دو راه بالا جواب ندادند."
        ),
    },
    "en": {
        "pay.gate": (
            "\U0001f510 <b>Welcome to {brand}</b>\n{rule}\n"
            "A one-time payment unlocks the bot.\n\n"
            "\U0001f4b0 Price: <b>{price}</b>\n"
            "\u23f3 Valid for: <b>{period}</b>\n\n"
            "Pick a payment method. The bot unlocks <b>automatically</b> once the "
            "payment clears, no receipt needed."
        ),
        "pay.price_toman": "{amount} Toman",
        "pay.price_stars": "{stars} \u2b50\ufe0f Stars",
        "pay.or": " or ",
        "pay.period_forever": "lifetime",
        "pay.period_days": "{days} days",
        "pay.no_gateway": "\u26a0\ufe0f The admin has not configured a payment gateway yet. Please try again later.",
        "pay.zp_link": (
            "\U0001f4b3 <b>Your payment link is ready</b>\n{rule}\n"
            "Amount: <b>{price}</b>\n\n"
            "Tap the button, complete the payment, then come back. Verification is automatic."
        ),
        "pay.failed": "\u274c Could not create the payment: <code>{reason}</code>",
        "pay.stars_title": "{brand} access",
        "pay.stars_desc": "{period} access to everything in {brand}",
        "pay.stars_label": "Access",
        "pay.done": (
            "\u2705 <b>Payment confirmed!</b>\n{rule}\n"
            "Reference: <code>{ref}</code>\n"
            "Valid: <b>{until}</b>\n\n"
            "Everything is unlocked. \U0001f389"
        ),
        "pay.pending": "\u23f3 No confirmed payment yet. If you just paid, try again in a few seconds.",
        "pay.active": "\u2705 Your access is active \u00b7 {until}",
        "pay.until_forever": "lifetime",
        "pay.until": "until {date}",
        "pay.precheckout_bad": "This invoice has expired. Please pay again from inside the bot.",
        "btn.pay_zp": "\U0001f4b3 Pay online (bank card)",
        "btn.pay_stars": "\u2b50\ufe0f Pay with Telegram Stars",
        "btn.pay_check": "\U0001f504 I paid, check it",
        "btn.pay_open": "\U0001f4b3 Open the payment page",
        "btn.pay_support": "\U0001f4ac Support",
        "btn.pay_menu": "\U0001f3e0 Main menu",
        "btn.pay_admin": "\U0001f4b3 Payment gateway",
        "admin.pay": (
            "\U0001f4b3 <b>Paid entry gateway</b>\n{rule}\n"
            "State: <b>{state}</b>\n"
            "Gateway: <b>{gateway}</b>\n"
            "Price (Zarinpal): <b>{amount}</b> Toman\n"
            "Price (Stars): <b>{stars}</b> \u2b50\ufe0f\n"
            "Each payment is valid: <b>{period}</b>\n"
            "Zarinpal merchant: <code>{merchant}</code>\n"
            "Sandbox: <b>{sandbox}</b>\n"
            "Callback: <code>{callback}</code>\n"
            "{rule}\n"
            "\U0001f465 Active: <b>{active}</b> of {subscribers}\n"
            "\U0001f4b0 Revenue: <b>{toman}</b> Toman \u00b7 <b>{earned}</b> \u2b50\ufe0f\n"
            "\u2705 Paid: <b>{paid}</b> \u00b7 \u23f3 Pending: <b>{pending}</b>"
            "{warning}"
        ),
        "admin.pay_warn_zp": "\n\n\u26a0\ufe0f Zarinpal needs <code>PUBLIC_URL</code> (https) on the server and a merchant id.",
        "admin.pay_warn_none": "\n\n\u26a0\ufe0f No usable payment method is configured; users will see \"gateway not configured\".",
        "admin.pay_gw_stars": "Telegram Stars",
        "admin.pay_gw_zarinpal": "Zarinpal",
        "admin.pay_gw_both": "Both",
        "btn.pay_toggle": "\U0001f512 On / off",
        "btn.pay_gw": "\U0001f500 Switch gateway",
        "btn.pay_amount": "\U0001f4b0 Toman price",
        "btn.pay_stars_price": "\u2b50\ufe0f Stars price",
        "btn.pay_days": "\u23f3 Validity",
        "btn.pay_merchant": "\U0001f511 Zarinpal merchant",
        "btn.pay_sandbox": "\U0001f9ea Sandbox",
        "btn.pay_grant": "\u2795 Grant manually",
        "btn.pay_revoke": "\u2796 Revoke",
        "btn.pay_list": "\U0001f9fe Recent payments",
        "admin.pay_prompt_amount": "Send the entry price in <b>Toman</b> (e.g. <code>50000</code>):",
        "admin.pay_prompt_stars": "Send the price in <b>Stars</b> (e.g. <code>100</code>):",
        "admin.pay_prompt_days": "Send how many <b>days</b> one payment lasts. <code>0</code> means lifetime:",
        "admin.pay_prompt_merchant": "Send your Zarinpal merchant id (36 characters). Send <code>-</code> to clear:",
        "admin.pay_prompt_grant": "Send the user's numeric id, optionally followed by days (e.g. <code>123456789 30</code>):",
        "admin.pay_prompt_revoke": "Send the numeric id of the user to revoke:",
        "admin.pay_bad_number": "\u274c Send a valid number.",
        "admin.pay_bad_merchant": "\u274c That is not a merchant id; it must be a 36 character UUID.",
        "admin.pay_saved": "\u2705 Saved.",
        "admin.pay_granted": "\u2705 User <code>{user}</code> unlocked \u00b7 {until}",
        "admin.pay_revoked": "\u2705 Access for <code>{user}</code> revoked.",
        "admin.pay_revoke_none": "That user had no access to revoke.",
        "admin.pay_list": "\U0001f9fe <b>Recent payments</b>\n{rule}\n{list}",
        "admin.pay_list_empty": "No payments yet.",
        "pay.user_granted": "\U0001f389 An admin unlocked the bot for you \u00b7 {until}",
        "wg.ios_awg_caption": (
            "\U0001f34f <b>For iPhone / Mac \u2014 recommended</b>\n"
            "Open this file in the free <b>AmneziaWG</b> app from the App Store. "
            "It is obfuscated, so the WireGuard handshake filter does not see it."
        ),
        "wg.ios_plain_caption": (
            "\U0001f4c4 Standard file for the official <b>WireGuard</b> app. Some carriers filter its "
            "handshake; if it connects but nothing loads, use the AmneziaWG file above."
        ),
        "wg.ios_guide": (
            "\U0001f34f <b>WireGuard on iPhone</b>\n{rule}\n"
            "1) Install <a href=\"" + AMNEZIAWG_IOS_URL + "\">AmneziaWG</a> from the App Store.\n"
            "2) Tap the <b>AmneziaWG</b> file above \u2192 Share \u2192 AmneziaWG,\n"
            "   or in the app: + \u2192 Import from file.\n"
            "3) Turn the tunnel on. \u2705\n\n"
            "\U0001f501 Plan B: <a href=\"" + HIDDIFY_IOS_URL + "\">Hiddify</a> \u2014 copy this link and add "
            "it with \u201c+ \u2192 Add from clipboard\u201d. Anti-filter noise is built in:\n"
            "<code>{hiddify}</code>\n\n"
            "\u26a0\ufe0f The official <a href=\"" + WIREGUARD_IOS_URL + "\">WireGuard</a> app has no "
            "obfuscation; use it only if both options above fail."
        ),
    },
}
