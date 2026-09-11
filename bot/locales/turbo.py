"""Copy for the turbo panel's two new buttons: Trojan and Fragment.

Kept in its own catalogue rather than folded into ``fa.py`` and ``en.py`` so both
features can be read and reworded in one place. Merged last in ``i18n``, so
anything here wins.

Every multi-line screen starts its lines with a right-to-left mark (\u200f).
Telegram aligns a line by its first strong character, so a line that opens with
an emoji or a latin word jumps left and drags the whole layout apart.
"""

RLM = "\u200f"

TURBO: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------------ buttons
        "btn.trojan": "\U0001f3af کانفیگ تروجان",
        "btn.fragment": "\U0001f9e9 تبدیل همه به فرگمنت",
        # ------------------------------------------------------------- trojan
        "sub_mixed": (
            "\u200f\U0001f3af <b>لینک ترکیبی (VLESS + Trojan)</b>\n"
            "\u200f<code>{mix}</code>\n\n"
            "\u200f\U0001f4a1 این یکی هر دو پروتکل را با هم می‌دهد. اگر روی شبکه‌ات یکی بسته شد، "
            "آن یکی وصل می‌شود."
        ),
        "trojan_configs": (
            "\u200f\U0001f3af <b>کانفیگ تروجان \u2014 موتور واقعی</b>\n"
            "\u200f{rule}\n"
            "\u200f\U0001f9ea پروتکل: <b>Trojan / WS / TLS</b>\n"
            "\u200f\U0001f4e6 تعداد: <b>{count}</b>\n"
            "\u200f\U0001f511 پسورد: <code>{password}</code>\n"
            "\u200f\U0001f517 لینک اشتراک تروجان:\n<code>{sub}</code>\n"
            "\u200f{rule}\n"
            "\u200f\u2705 تروجان واقعی است و روی همان ورکر خودت بالا می‌آید: پینگ می‌دهد و در "
            "v2rayNG و Hiddify و sing-box و Streisand کار می‌کند.\n"
            "\u200f\U0001f512 فقط روی پورت‌های TLS ساخته می‌شود. روی پورت ساده، پسورد تروجان "
            "بدون رمز رد می‌شود و هیچ کلاینتی قبولش نمی‌کند.\n"
            "\u200f\U0001f4a1 وصل نشد؟ یک بار <b>اعمال فوری آی‌پی تمیز</b> را بزن تا ورکرت روی "
            "نسخهٔ تازه بالا بیاید."
        ),
        "trojan_none": (
            "\u200f\u26a0\ufe0f <b>الان اندپوینت TLS نداری</b>\n"
            "\u200f{rule}\n"
            "\u200fتروجان فقط روی پورت‌های TLS (\u06f4\u06f4\u06f3 \u00b7 \u06f2\u06f0\u06f5\u06f3 \u00b7 \u06f8\u06f4\u06f4\u06f3) معنی دارد.\n"
            "\u200fیک بار <b>اعمال فوری آی‌پی تمیز</b> را بزن و دوباره امتحان کن."
        ),
        # ----------------------------------------------------------- fragment
        "fragment_ready": (
            "\U0001f9e9 فرگمنت روی <b>{count}</b> کانفیگ فعال شد "
            "(length {length} \u00b7 interval {interval}).\n\n"
            "\U0001f4f2 <b>v2rayNG / Streisand / V2Box:</b> دکمهٔ + \u2190 Import config from file "
            "\u2190 همین فایل.\n"
            "\U0001f504 خودش سریع‌ترین کانفیگ را پیدا و انتخاب می‌کند (leastPing).\n"
            "\U0001f4a1 فرگمنت کار کلاینت است نه سرور. برای همین لینک ساده نمی‌تواند حملش کند و "
            "باید فایل باشد."
        ),
        "fragment_none": (
            "\u200f\U0001f4ed هنوز کانفیگی روی پنلت نیست که فرگمنت شود. اول "
            "<b>اعمال فوری آی‌پی تمیز</b> را بزن."
        ),
    },
    "en": {
        "btn.trojan": "\U0001f3af Trojan configs",
        "btn.fragment": "\U0001f9e9 Convert all to Fragment",
        "sub_mixed": (
            "\U0001f3af <b>Mixed link (VLESS + Trojan)</b>\n"
            "<code>{mix}</code>\n\n"
            "\U0001f4a1 One link, both protocols. If your network kills one handshake, the "
            "other still connects."
        ),
        "trojan_configs": (
            "\U0001f3af <b>Trojan configs \u2014 real engine</b>\n"
            "{rule}\n"
            "\U0001f9ea Protocol: <b>Trojan / WS / TLS</b>\n"
            "\U0001f4e6 Count: <b>{count}</b>\n"
            "\U0001f511 Password: <code>{password}</code>\n"
            "\U0001f517 Trojan subscription:\n<code>{sub}</code>\n"
            "{rule}\n"
            "\u2705 These run on your own worker, they ping, and they work in v2rayNG, "
            "Hiddify, sing-box and Streisand.\n"
            "\U0001f512 TLS ports only: on a plain port the password would cross in the clear "
            "and no client would accept it.\n"
            "\U0001f4a1 Nothing connecting? Press <b>apply clean IPs</b> once so the worker "
            "picks up the newest bundle."
        ),
        "trojan_none": (
            "\u26a0\ufe0f <b>No TLS endpoint right now</b>\n"
            "{rule}\n"
            "Trojan only makes sense on a TLS port (443 \u00b7 2053 \u00b7 8443).\n"
            "Press <b>apply clean IPs</b> once and try again."
        ),
        "fragment_ready": (
            "\U0001f9e9 Fragment enabled on <b>{count}</b> configs "
            "(length {length} \u00b7 interval {interval}).\n\n"
            "\U0001f4f2 <b>v2rayNG / Streisand / V2Box:</b> + \u2192 Import config from file "
            "\u2192 this file.\n"
            "\U0001f504 It keeps the fastest config for you (leastPing).\n"
            "\U0001f4a1 Fragmentation is a client setting, not a server one, which is why a "
            "plain link cannot carry it and a file can."
        ),
        "fragment_none": (
            "\U0001f4ed No configs on your panel to fragment yet. Press <b>apply clean IPs</b> "
            "first."
        ),
    },
}
