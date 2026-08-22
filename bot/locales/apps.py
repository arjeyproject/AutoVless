"""Apps and downloads copy."""

APPS: dict[str, dict[str, str]] = {
    "fa": {
        "btn.apps_android": "\U0001f916 \u0627\u0646\u062f\u0631\u0648\u06cc\u062f",
        "btn.apps_ios": "\uf8ff \u0622\u06cc\u0641\u0648\u0646 \u0648 \u0622\u06cc\u067e\u062f",
        "btn.apps_windows": "\U0001fa9f \u0648\u06cc\u0646\u062f\u0648\u0632",
        "btn.apps_macos": "\U0001f4bb \u0645\u06a9",
        "btn.apps_linux": "\U0001f427 \u0644\u06cc\u0646\u0648\u06a9\u0633",
        "apps.home": (
            "\u200f\U0001f4f1 <b>\u0628\u0631\u0646\u0627\u0645\u0647\u200c\u0647\u0627 \u0648 \u0644\u06cc\u0646\u06a9 \u062f\u0627\u0646\u0644\u0648\u062f</b>\n"
            "\u200f{rule}\n"
            "\u200f\u0627\u0648\u0644 \u062f\u0633\u062a\u06af\u0627\u0647\u062a \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646\u060c \u0628\u0639\u062f \u0631\u0648\u06cc <b>\u0627\u0633\u0645 \u0628\u0631\u0646\u0627\u0645\u0647</b> \u0628\u0632\u0646 \u062a\u0627 \u0635\u0641\u062d\u0647\u0654 \u0646\u0635\u0628\u0634 \u0628\u0627\u0644\u0627 \u0628\u06cc\u0627\u06cc\u062f.\n\n"
            "\u200f\u2b50 = \u067e\u06cc\u0634\u0646\u0647\u0627\u062f \u0645\u0646\n"
            "\u200f\u25b6\ufe0f \u06af\u0648\u06af\u0644 \u067e\u0644\u06cc \u00b7 \uf8ff \u0627\u067e \u0627\u0633\u062a\u0648\u0631 \u00b7 \U0001f419 \u06af\u06cc\u062a\u200c\u0647\u0627\u0628 \u00b7 \U0001f310 \u0633\u0627\u06cc\u062a \u0631\u0633\u0645\u06cc\n\n"
            "\u200f\U0001f4a1 \u0628\u0631\u0646\u0627\u0645\u0647 \u0631\u0627 \u0646\u0635\u0628 \u06a9\u0631\u062f\u06cc\u061f \u0628\u0631\u0648 \u0633\u0631\u0627\u063a \u062f\u06a9\u0645\u0647\u0654 \u00ab\u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9\u00bb \u062f\u0631 \u0645\u062f\u06cc\u0631\u06cc\u062a \u067e\u0646\u0644."
        ),
        "apps.platform": (
            "\u200f{icon} <b>{title}</b>\n"
            "\u200f{rule}\n"
            "\u200f{count} \u0628\u0631\u0646\u0627\u0645\u0647\u0654 \u062a\u0633\u062a\u200c\u0634\u062f\u0647. \u0631\u0648\u06cc \u0627\u0633\u0645 \u0647\u0631 \u06a9\u062f\u0627\u0645 \u0628\u0632\u0646\u06cc \u0645\u0633\u062a\u0642\u06cc\u0645 \u0628\u0627\u0632 \u0645\u06cc\u200c\u0634\u0648\u062f.\n\n"
            "\u200f{note}\n\n"
            "\u200f\U0001f517 <b>\u0631\u0648\u0634 \u062f\u0631\u0633\u062a \u0627\u0641\u0632\u0648\u062f\u0646 \u06a9\u0627\u0646\u0641\u06cc\u06af</b>\n"
            "\u200f\u06f1. \u0644\u06cc\u0646\u06a9 \u0627\u0634\u062a\u0631\u0627\u06a9 \u0631\u0627 \u0627\u0632 \u0645\u0646\u0648\u06cc \u067e\u0646\u0644 \u06a9\u067e\u06cc \u06a9\u0646.\n"
            "\u200f\u06f2. \u062f\u0631 \u0628\u0631\u0646\u0627\u0645\u0647 \u0628\u062e\u0634 <b>Subscription</b> \u0631\u0627 \u0628\u0627\u0632 \u06a9\u0646 (\u0646\u0647 \u06a9\u0627\u0646\u0641\u06cc\u06af \u062f\u0633\u062a\u06cc).\n"
            "\u200f\u06f3. \u0644\u06cc\u0646\u06a9 \u0631\u0627 \u067e\u06cc\u0633\u062a \u06a9\u0646 \u0648 Update \u0628\u0632\u0646.\n"
            "\u200f\u06f4. \u062a\u0633\u062a \u062a\u0627\u062e\u06cc\u0631 \u0628\u06af\u06cc\u0631 \u0648 \u0633\u0631\u06cc\u0639\u200c\u062a\u0631\u06cc\u0646 \u0631\u0627 \u0648\u0635\u0644 \u06a9\u0646."
        ),
        "apps.note_android": (
            "\U0001f4cc \u0628\u0631\u0627\u06cc \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u0627\u06cc\u0646 \u0631\u0628\u0627\u062a \u0628\u0647\u062a\u0631\u06cc\u0646 \u0627\u0646\u062a\u062e\u0627\u0628 <b>v2rayNG</b> \u0627\u0633\u062a. "
            "\u0627\u06af\u0631 \u06af\u0648\u06af\u0644 \u067e\u0644\u06cc \u0628\u0627\u0644\u0627 \u0646\u06cc\u0627\u0645\u062f\u060c \u0646\u0633\u062e\u0647\u0654 APK \u0631\u0627 \u0627\u0632 \u06af\u06cc\u062a\u200c\u0647\u0627\u0628 \u0628\u06af\u06cc\u0631."
        ),
        "apps.note_ios": (
            "\U0001f4cc <b>Streisand</b> \u0631\u0627\u06cc\u06af\u0627\u0646 \u0627\u0633\u062a \u0648 \u0647\u0645\u0647\u0654 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u0645\u0627 \u0631\u0627 \u0645\u06cc\u200c\u0641\u0647\u0645\u062f. "
            "\u0628\u0631\u0627\u06cc \u062f\u0627\u0646\u0644\u0648\u062f \u0628\u0647 \u0627\u067e\u0644 \u0622\u06cc\u062f\u06cc \u063a\u06cc\u0631\u0627\u06cc\u0631\u0627\u0646\u06cc \u0646\u06cc\u0627\u0632 \u062f\u0627\u0631\u06cc."
        ),
        "apps.note_windows": (
            "\U0001f4cc <b>v2rayN</b> \u0631\u0627 \u062f\u0627\u0646\u0644\u0648\u062f \u06a9\u0646\u060c \u0627\u0632 \u062d\u0627\u0644\u062a \u0641\u0634\u0631\u062f\u0647 \u062e\u0627\u0631\u062c \u06a9\u0646 \u0648 \u0627\u062c\u0631\u0627 \u06a9\u0646. "
            "\u0627\u06af\u0631 \u062f\u0646\u0628\u0627\u0644 \u0686\u06cc\u0632\u06cc \u0633\u0627\u062f\u0647\u200c\u062a\u0631 \u0647\u0633\u062a\u06cc\u060c Hiddify \u0631\u0627 \u0646\u0635\u0628 \u06a9\u0646."
        ),
        "apps.note_macos": (
            "\U0001f4cc \u0631\u0648\u06cc \u0645\u06a9\u200c\u0647\u0627\u06cc Apple Silicon \u0645\u06cc\u200c\u062a\u0648\u0627\u0646\u06cc \u0646\u0633\u062e\u0647\u0654 \u0622\u06cc\u0641\u0648\u0646 Streisand \u0631\u0627 \u0647\u0645 \u0646\u0635\u0628 \u06a9\u0646\u06cc."
        ),
        "apps.note_linux": (
            "\U0001f4cc \u0646\u0633\u062e\u0647\u0654 AppImage \u06cc\u0627 deb \u0631\u0627 \u0627\u0632 \u0635\u0641\u062d\u0647\u0654 Releases \u0628\u0631\u062f\u0627\u0631. "
            "\u0628\u0631\u0627\u06cc \u0633\u0631\u0648\u0631 \u0628\u062f\u0648\u0646 \u06af\u0631\u0627\u0641\u06cc\u06a9\u060c sing-box \u06cc\u0627 mihomo \u06af\u0632\u06cc\u0646\u0647\u0654 \u062f\u0631\u0633\u062a \u0627\u0633\u062a."
        ),
        "apps.title_android": "\u0627\u0646\u062f\u0631\u0648\u06cc\u062f",
        "apps.title_ios": "\u0622\u06cc\u0641\u0648\u0646 \u0648 \u0622\u06cc\u067e\u062f",
        "apps.title_windows": "\u0648\u06cc\u0646\u062f\u0648\u0632",
        "apps.title_macos": "\u0645\u06a9\u200c\u0627\u0648\u200c\u0627\u0633",
        "apps.title_linux": "\u0644\u06cc\u0646\u0648\u06a9\u0633",
    },
    "en": {
        "btn.apps_android": "\U0001f916 Android",
        "btn.apps_ios": "\uf8ff iPhone / iPad",
        "btn.apps_windows": "\U0001fa9f Windows",
        "btn.apps_macos": "\U0001f4bb macOS",
        "btn.apps_linux": "\U0001f427 Linux",
        "apps.home": (
            "\U0001f4f1 <b>Apps and downloads</b>\n{rule}\n"
            "Pick your device, then tap an <b>app name</b> to open its install page.\n\n"
            "\u2b50 = my pick\n"
            "\u25b6\ufe0f Google Play \u00b7 \uf8ff App Store \u00b7 \U0001f419 GitHub \u00b7 \U0001f310 official site\n\n"
            "\U0001f4a1 Already installed? Grab the subscription link from the panel screen."
        ),
        "apps.platform": (
            "{icon} <b>{title}</b>\n{rule}\n"
            "{count} tested apps. Tap a name and it opens straight away.\n\n"
            "{note}\n\n"
            "\U0001f517 <b>How to add your configs</b>\n"
            "1. Copy the subscription link from the panel menu.\n"
            "2. Open <b>Subscription</b> in the app, not the manual config field.\n"
            "3. Paste the link and hit Update.\n"
            "4. Run a delay test and connect to the fastest one."
        ),
        "apps.note_android": (
            "\U0001f4cc <b>v2rayNG</b> is the best match for these configs. "
            "If Play is unreachable, take the APK from GitHub."
        ),
        "apps.note_ios": (
            "\U0001f4cc <b>Streisand</b> is free and understands every config we hand out. "
            "You need a non-Iranian Apple ID to download it."
        ),
        "apps.note_windows": (
            "\U0001f4cc Download <b>v2rayN</b>, unzip it and run it. "
            "Want something simpler? Install Hiddify."
        ),
        "apps.note_macos": (
            "\U0001f4cc On Apple Silicon Macs the iPhone build of Streisand installs too."
        ),
        "apps.note_linux": (
            "\U0001f4cc Grab the AppImage or deb from the Releases page. "
            "On a headless box, sing-box or mihomo is the right call."
        ),
        "apps.title_android": "Android",
        "apps.title_ios": "iPhone / iPad",
        "apps.title_windows": "Windows",
        "apps.title_macos": "macOS",
        "apps.title_linux": "Linux",
    },
}
