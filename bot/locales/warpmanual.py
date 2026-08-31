"""Strings for endpoints an admin pins by hand.

Own catalogue rather than more keys in ``locales/warppool.py``, and merged last in
``i18n`` so anything here wins. Persian is the default and English is a full
peer.

Two things every screen in here has to say, because getting either wrong is how
an Irancell user ends up with a config that cannot connect:

  * **which pool feeds which button.** IPv6 is Irancell, IPv4 is everyone else.
    It is printed on the prompt, on the report and on the listing rather than
    left for the admin to remember.
  * **whether the endpoint was actually tested here.** On a host with no IPv6
    route no handshake is possible, so a pasted address is taken on trust and
    marked as such. Pretending it was measured would be a lie, and hiding it
    would make a working feature look broken.
"""

from __future__ import annotations

WARPMANUAL: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------------ buttons
        "btn.pool_add_v4": "\u2795 \u0627\u0641\u0632\u0648\u062f\u0646 \u062f\u0633\u062a\u06cc IPv4",
        "btn.pool_add_v6": "\u2795 \u0627\u0641\u0632\u0648\u062f\u0646 \u062f\u0633\u062a\u06cc IPv6",
        "btn.pool_manual": "\U0001f590 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u062f\u0633\u062a\u06cc",
        "btn.pool_manual_check": "\U0001fa7a \u062a\u0633\u062a \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u062f\u0633\u062a\u06cc",
        "btn.pool_manual_clear_v4": "\U0001f5d1 \u067e\u0627\u06a9\u200c\u0633\u0627\u0632\u06cc \u062f\u0633\u062a\u06cc IPv4",
        "btn.pool_manual_clear_v6": "\U0001f5d1 \u067e\u0627\u06a9\u200c\u0633\u0627\u0632\u06cc \u062f\u0633\u062a\u06cc IPv6",

        # -------------------------------------------------- the pool screen
        "pool.manual_block": (
            "\U0001f590 <b>\u062f\u0633\u062a\u06cc</b> \u2014 IPv4 <b>{v4}</b>/{v4all} \u00b7 "
            "IPv6 <b>{v6}</b>/{v6all} \u00b7 \u0633\u0627\u0644\u0645/\u06a9\u0644"
        ),

        # ---------------------------------------------------- asking for input
        "pool.manual_prompt": (
            "\U0001f590 <b>\u0627\u0641\u0632\u0648\u062f\u0646 \u062f\u0633\u062a\u06cc \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a {family}</b>\n{rule}\n"
            "\u0627\u06cc\u0646 \u0627\u0633\u062a\u062e\u0631 \u062f\u0642\u06cc\u0642\u0627\u064b \u0647\u0645\u0627\u0646 \u0686\u06cc\u0632\u06cc \u0627\u0633\u062a \u06a9\u0647 \u06a9\u0627\u0631\u0628\u0631 \u0628\u0627 \u062f\u06a9\u0645\u0647\u200c\u06cc "
            "<b>{operator}</b> \u0645\u06cc\u200c\u06af\u06cc\u0631\u062f.\n\n"
            "\U0001f4cb \u0644\u06cc\u0633\u062a \u0631\u0627 \u0628\u0641\u0631\u0633\u062a \u2014 \u0647\u0631 \u062e\u0637 \u06cc\u06a9 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u060c \u06cc\u0627 \u062c\u062f\u0627\u0634\u062f\u0647 \u0628\u0627 \u06a9\u0627\u0645\u0627 \u06cc\u0627 \u0641\u0627\u0635\u0644\u0647:\n"
            "\u2022 <code>162.159.192.1:2408</code>\n"
            "\u2022 <code>[2606:4700:d0::a29f:c001]:2408</code>\n"
            "\u2022 <code>188.114.98.10</code> \u2190 \u0628\u062f\u0648\u0646 \u067e\u0648\u0631\u062a\u060c \u06cc\u0639\u0646\u06cc <b>{port}</b>\n\n"
            "\U0001f9ea \u0647\u0631 \u0622\u062f\u0631\u0633 \u0628\u0627 \u0647\u0645\u0627\u0646 \u0647\u0646\u062f\u0634\u06cc\u06a9 \u0648\u0627\u0642\u0639\u06cc WireGuard \u062a\u0633\u062a \u0645\u06cc\u200c\u0634\u0648\u062f \u0648 "
            "\u0628\u0627\u06cc\u062f \u0627\u0632 \u06a9\u0641 \u0633\u0644\u0627\u0645\u062a <b>{floor}</b> \u0631\u062f \u0634\u0648\u062f\u061b \u0647\u0631\u0686\u0647 \u0631\u062f \u0646\u0634\u0648\u062f \u0630\u062e\u06cc\u0631\u0647 \u0646\u0645\u06cc\u200c\u0634\u0648\u062f.\n"
            "\U0001f4cc \u062d\u062f\u0627\u06a9\u0631\u062b <b>{cap}</b> \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a \u062f\u0631 \u0647\u0631 \u0628\u0627\u0631.\n"
            "\U0001f590 \u0627\u0644\u0627\u0646 \u062f\u0631 \u0627\u06cc\u0646 \u062e\u0627\u0646\u0648\u0627\u062f\u0647: <b>{pinned}</b>/{total} \u0633\u0627\u0644\u0645."
        ),
        "pool.manual_no_route": (
            "\u26a0\ufe0f <b>\u0627\u06cc\u0646 \u0633\u0631\u0648\u0631 \u0631\u0648\u062a {family} \u0646\u062f\u0627\u0631\u062f</b>\n"
            "\u067e\u0633 \u0627\u0632 \u0627\u06cc\u0646\u062c\u0627 \u0647\u06cc\u0686 \u0647\u0646\u062f\u0634\u06cc\u06a9\u06cc \u0645\u0645\u06a9\u0646 \u0646\u06cc\u0633\u062a \u0648 \u0622\u062f\u0631\u0633\u200c\u0647\u0627 "
            "<b>\u0628\u062f\u0648\u0646 \u062a\u0633\u062a</b> \u0648 \u0631\u0648\u06cc \u0627\u0639\u062a\u0645\u0627\u062f \u062a\u0648 \u0630\u062e\u06cc\u0631\u0647 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f.\n"
            "\U0001f449 \u0641\u0642\u0637 \u0686\u06cc\u0632\u06cc \u0631\u0627 \u0628\u0641\u0631\u0633\u062a \u06a9\u0647 \u062e\u0648\u062f\u062a \u0631\u0648\u06cc \u06af\u0648\u0634\u06cc \u062a\u0633\u062a \u06a9\u0631\u062f\u0647\u200c\u0627\u06cc."
        ),
        "pool.manual_empty": (
            "\U0001f914 \u0686\u06cc\u0632\u06cc \u0642\u0627\u0628\u0644 \u062e\u0648\u0627\u0646\u062f\u0646 \u0646\u0628\u0648\u062f. \u06cc\u06a9 \u0644\u06cc\u0633\u062a \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a \u0628\u0641\u0631\u0633\u062a\u060c "
            "\u0645\u062b\u0644 <code>162.159.192.1:2408</code>"
        ),
        "pool.manual_none": (
            "\u274c <b>\u0647\u06cc\u0686 \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a {family} \u0645\u0639\u062a\u0628\u0631\u06cc \u062f\u0631 \u0627\u06cc\u0646 \u0645\u062a\u0646 \u0646\u0628\u0648\u062f</b>\n{rule}\n"
            "\U0001f4cd \u06cc\u0627 \u0642\u0627\u0644\u0628 \u0622\u062f\u0631\u0633\u200c\u0647\u0627 \u0627\u0634\u062a\u0628\u0627\u0647 \u0627\u0633\u062a\u060c \u06cc\u0627 \u062e\u0627\u0646\u0648\u0627\u062f\u0647\u200c\u06cc \u0622\u0646\u200c\u0647\u0627 \u0641\u0631\u0642 \u062f\u0627\u0631\u062f.\n"
            "\u0628\u0631\u0627\u06cc IPv6 \u067e\u0648\u0631\u062a \u0631\u0627 \u062f\u0627\u062e\u0644 \u06a9\u0631\u0648\u0634\u0647 \u0628\u062f\u0647: <code>[2606:4700:d0::a29f:c001]:2408</code>"
        ),
        "pool.manual_identity": (
            "\u26d4\ufe0f \u0647\u0648\u06cc\u062a \u0627\u0633\u06a9\u0646 \u062f\u0631 \u062f\u0633\u062a\u0631\u0633 \u0646\u06cc\u0633\u062a\u060c \u067e\u0633 \u0647\u06cc\u0686 \u0622\u062f\u0631\u0633\u06cc \u0642\u0627\u0628\u0644 \u062a\u0633\u062a \u0646\u06cc\u0633\u062a."
        ),
        "pool.manual_started": (
            "\U0001f9ea <b>\u062f\u0627\u0631\u0645 {count} \u0645\u0648\u0631\u062f \u0631\u0627 \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u062e\u0631 {family} \u062a\u0633\u062a \u0645\u06cc\u200c\u06a9\u0646\u0645</b>\n{rule}\n"
            "\u0647\u0646\u062f\u0634\u06cc\u06a9 \u0648\u0627\u0642\u0639\u06cc\u060c \u0686\u0646\u062f \u0628\u0627\u0631 \u0648 \u0628\u0627 \u0641\u0627\u0635\u0644\u0647. \u0646\u062a\u06cc\u062c\u0647 \u062f\u0631 \u0647\u0645\u06cc\u0646 \u067e\u06cc\u0627\u0645 \u0645\u06cc\u200c\u0622\u06cc\u062f."
        ),
        "pool.manual_done": (
            "\U0001f590 <b>\u0627\u0641\u0632\u0648\u062f\u0646 \u062f\u0633\u062a\u06cc {family} \u0627\u0646\u062c\u0627\u0645 \u0634\u062f</b>\n{rule}\n"
            "\U0001f4f2 \u0645\u0642\u0635\u062f: \u062f\u06a9\u0645\u0647\u200c\u06cc <b>{operator}</b>\n"
            "\U0001f4e5 \u062f\u0627\u062f\u0647 \u0634\u062f: <b>{given}</b>\n"
            "\u2705 \u0633\u0627\u0644\u0645 \u0648 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f: <b>{stored}</b>\n"
            "\U0001f552 \u0628\u062f\u0648\u0646 \u062a\u0633\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f: <b>{untested}</b>\n"
            "\U0001f480 \u062c\u0648\u0627\u0628 \u0646\u062f\u0627\u062f: <b>{dead}</b>\n"
            "\u26a0\ufe0f \u0636\u0639\u06cc\u0641 \u0628\u0648\u062f: <b>{weak}</b>\n"
            "\u23ed \u0631\u062f \u0634\u062f (\u062e\u0627\u0646\u0648\u0627\u062f\u0647/\u062a\u06a9\u0631\u0627\u0631\u06cc/\u0646\u0627\u0645\u0639\u062a\u0628\u0631): <b>{skipped}</b>\n{rule}\n"
            "\U0001f590 \u062f\u0633\u062a\u06cc \u062f\u0631 \u0627\u06cc\u0646 \u062e\u0627\u0646\u0648\u0627\u062f\u0647: <b>{pinned}</b>/{total} \u0633\u0627\u0644\u0645\n"
            "\U0001f3ca \u06a9\u0644 \u0627\u0633\u062a\u062e\u0631 {family}: <b>{pool}</b>/{target}\n"
            "\u23f1 \u0632\u0645\u0627\u0646: <b>{secs}</b> \u062b\u0627\u0646\u06cc\u0647\n{rule}\n{list}"
        ),
        "pool.manual_more": "\u2026 \u0648 <b>{count}</b> \u0645\u0648\u0631\u062f \u062f\u06cc\u06af\u0631.",
        "pool.manual_untested_note": (
            "\u26a0\ufe0f \u0627\u06cc\u0646 \u0645\u0648\u0627\u0631\u062f \u0627\u0632 \u0627\u06cc\u0646 \u0633\u0631\u0648\u0631 \u0642\u0627\u0628\u0644 \u062a\u0633\u062a \u0646\u0628\u0648\u062f\u0646\u062f (\u0631\u0648\u062a {family} \u0646\u062f\u0627\u0631\u062f). "
            "\u0628\u0647 \u06a9\u0627\u0631\u0628\u0631 \u062f\u0627\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f \u0648\u0644\u06cc \u0647\u0645\u06cc\u0634\u0647 \u067e\u0634\u062a \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u0627\u0646\u062f\u0627\u0632\u0647\u200c\u06af\u06cc\u0631\u06cc\u200c\u0634\u062f\u0647 \u0642\u0631\u0627\u0631 \u0645\u06cc\u200c\u06af\u06cc\u0631\u0646\u062f."
        ),
        "pool.manual_failed": "\u26d4\ufe0f \u0627\u0641\u0632\u0648\u062f\u0646 \u062f\u0633\u062a\u06cc \u0646\u0627\u0645\u0648\u0641\u0642 \u0628\u0648\u062f: <code>{reason}</code>",

        # ------------------------------------------------- per line verdicts
        "pool.manual_v_stored": "\u0633\u0627\u0644\u0645\u060c \u062f\u0631 \u0627\u0633\u062a\u062e\u0631",
        "pool.manual_v_untested": "\u0628\u062f\u0648\u0646 \u062a\u0633\u062a\u060c \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f",
        "pool.manual_v_dead": "\u062c\u0648\u0627\u0628 \u0646\u062f\u0627\u062f",
        "pool.manual_v_weak": "\u0627\u0632 \u06a9\u0641 \u0633\u0644\u0627\u0645\u062a \u0631\u062f \u0646\u0634\u062f",
        "pool.manual_v_family": "\u062e\u0627\u0646\u0648\u0627\u062f\u0647\u200c\u06cc \u0627\u0634\u062a\u0628\u0627\u0647",
        "pool.manual_v_dup": "\u062a\u06a9\u0631\u0627\u0631\u06cc",
        "pool.manual_v_bad": "\u0642\u0627\u0644\u0628 \u0646\u0627\u0645\u0639\u062a\u0628\u0631",
        "pool.manual_v_over": "\u0628\u06cc\u0634\u062a\u0631 \u0627\u0632 \u0633\u0642\u0641 \u0645\u062c\u0627\u0632",

        # --------------------------------------------------- the manual screen
        "pool.manual_screen": (
            "\U0001f590 <b>\u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u062f\u0633\u062a\u06cc</b>\n{rule}\n"
            "\u0627\u06cc\u0646\u200c\u0647\u0627 \u0631\u0627 \u062e\u0648\u062f\u062a \u0648\u0627\u0631\u062f \u06a9\u0631\u062f\u0647\u200c\u0627\u06cc. \u0647\u06cc\u0686 \u067e\u0627\u06a9\u0633\u0627\u0632\u06cc \u062e\u0648\u062f\u06a9\u0627\u0631\u06cc \u062d\u0630\u0641\u0634\u0627\u0646 \u0646\u0645\u06cc\u200c\u06a9\u0646\u062f\u061b "
            "\u0627\u06af\u0631 \u0628\u0645\u06cc\u0631\u0646\u062f \u06a9\u0646\u0627\u0631 \u06af\u0630\u0627\u0634\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f \u0648 \u0627\u06af\u0631 \u0628\u0631\u06af\u0631\u062f\u0646\u062f \u062e\u0648\u062f\u0634\u0627\u0646 \u0632\u0646\u062f\u0647 \u0645\u06cc\u200c\u0634\u0648\u0646\u062f.\n{rule}\n{list}"
        ),
        "pool.manual_family": (
            "\n<b>{family}</b> \u2190 {operator}\n"
            "\u2764\ufe0f \u0633\u0627\u0644\u0645: <b>{healthy}</b>/{total} \u00b7 \U0001f552 \u0628\u062f\u0648\u0646 \u062a\u0633\u062a: <b>{untested}</b>\n"
        ),
        "pool.manual_family_empty": "\u2014 \u0647\u0646\u0648\u0632 \u0686\u06cc\u0632\u06cc \u062f\u0633\u062a\u06cc \u0648\u0627\u0631\u062f \u0646\u0634\u062f\u0647.",
        "pool.manual_check_started": (
            "\U0001fa7a <b>\u062a\u0633\u062a \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u200c\u0647\u0627\u06cc \u062f\u0633\u062a\u06cc \u0634\u0631\u0648\u0639 \u0634\u062f</b>\n{rule}\n"
            "\u0641\u0642\u0637 \u0645\u0648\u0627\u0631\u062f\u06cc \u06a9\u0647 \u062e\u0648\u062f\u062a \u0648\u0627\u0631\u062f \u06a9\u0631\u062f\u0647\u200c\u0627\u06cc\u060c \u0646\u0647 \u0647\u0645\u0647\u200c\u06cc \u0627\u0633\u062a\u062e\u0631."
        ),
        "pool.manual_check_done": (
            "\U0001fa7a <b>\u062a\u0633\u062a \u062f\u0633\u062a\u06cc \u062a\u0645\u0627\u0645 \u0634\u062f</b>\n{rule}\n"
            "\U0001f50d \u0628\u0631\u0631\u0633\u06cc \u0634\u062f: <b>{checked}</b>\n"
            "\u2705 \u0632\u0646\u062f\u0647: <b>{alive}</b>\n"
            "\U0001f480 \u06a9\u0646\u0627\u0631 \u06af\u0630\u0627\u0634\u062a\u0647 \u0634\u062f: <b>{dead}</b>\n"
            "\u23ed \u0642\u0627\u0628\u0644 \u062a\u0633\u062a \u0646\u0628\u0648\u062f: <b>{skipped}</b>\n{rule}\n"
            "\U0001f590 IPv4 <b>{v4}</b>/{v4all} \u00b7 IPv6 <b>{v6}</b>/{v6all}"
        ),
        "pool.manual_clear_ask": (
            "\U0001f5d1 <b>\u067e\u0627\u06a9\u200c\u0633\u0627\u0632\u06cc \u062f\u0633\u062a\u06cc {family}</b>\n{rule}\n"
            "<b>{count}</b> \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a\u06cc \u06a9\u0647 \u062f\u0633\u062a\u06cc \u0648\u0627\u0631\u062f \u0634\u062f\u0647 \u067e\u0627\u06a9 \u0645\u06cc\u200c\u0634\u0648\u062f. "
            "\u0628\u0631\u06af\u0634\u062a\u06cc \u0646\u062f\u0627\u0631\u062f \u2014 \u0645\u0637\u0645\u0626\u0646\u06cc\u061f"
        ),
        "pool.manual_cleared": "\U0001f5d1 {count} \u0627\u0646\u062f\u067e\u0648\u06cc\u0646\u062a \u062f\u0633\u062a\u06cc {family} \u067e\u0627\u06a9 \u0634\u062f",
    },
    "en": {
        # ------------------------------------------------------------ buttons
        "btn.pool_add_v4": "\u2795 Add IPv4 by hand",
        "btn.pool_add_v6": "\u2795 Add IPv6 by hand",
        "btn.pool_manual": "\U0001f590 Hand entered endpoints",
        "btn.pool_manual_check": "\U0001fa7a Re-check the pinned ones",
        "btn.pool_manual_clear_v4": "\U0001f5d1 Clear manual IPv4",
        "btn.pool_manual_clear_v6": "\U0001f5d1 Clear manual IPv6",

        # -------------------------------------------------- the pool screen
        "pool.manual_block": (
            "\U0001f590 <b>By hand</b> \u2014 IPv4 <b>{v4}</b>/{v4all} \u00b7 "
            "IPv6 <b>{v6}</b>/{v6all} \u00b7 healthy/total"
        ),

        # ---------------------------------------------------- asking for input
        "pool.manual_prompt": (
            "\U0001f590 <b>Add {family} endpoints by hand</b>\n{rule}\n"
            "This pool is exactly what a user gets from the <b>{operator}</b> button.\n\n"
            "\U0001f4cb Send the list \u2014 one endpoint per line, or separated by commas "
            "or spaces:\n"
            "\u2022 <code>162.159.192.1:2408</code>\n"
            "\u2022 <code>[2606:4700:d0::a29f:c001]:2408</code>\n"
            "\u2022 <code>188.114.98.10</code> \u2190 no port means <b>{port}</b>\n\n"
            "\U0001f9ea Every address gets the same real WireGuard handshake as a scanned "
            "one and has to clear health <b>{floor}</b>. Whatever does not is never stored.\n"
            "\U0001f4cc Up to <b>{cap}</b> endpoints per paste.\n"
            "\U0001f590 Pinned in this family right now: <b>{pinned}</b>/{total} healthy."
        ),
        "pool.manual_no_route": (
            "\u26a0\ufe0f <b>This host has no {family} route</b>\n"
            "So no handshake is possible from here and the addresses are stored "
            "<b>untested</b>, on your word.\n"
            "\U0001f449 Only send what you have tested on a handset yourself."
        ),
        "pool.manual_empty": (
            "\U0001f914 Nothing readable in there. Send a list of endpoints, like "
            "<code>162.159.192.1:2408</code>"
        ),
        "pool.manual_none": (
            "\u274c <b>No valid {family} endpoint in that message</b>\n{rule}\n"
            "\U0001f4cd Either the format is off or those addresses are the other family.\n"
            "For IPv6 put the port outside brackets: "
            "<code>[2606:4700:d0::a29f:c001]:2408</code>"
        ),
        "pool.manual_identity": (
            "\u26d4\ufe0f No scan identity is available, so nothing can be tested right now."
        ),
        "pool.manual_started": (
            "\U0001f9ea <b>Testing {count} address(es) for the {family} pool</b>\n{rule}\n"
            "Real handshakes, several of them, spaced out. This message gets the result."
        ),
        "pool.manual_done": (
            "\U0001f590 <b>Hand entry into the {family} pool is done</b>\n{rule}\n"
            "\U0001f4f2 Serves: the <b>{operator}</b> button\n"
            "\U0001f4e5 Given: <b>{given}</b>\n"
            "\u2705 Healthy and stored: <b>{stored}</b>\n"
            "\U0001f552 Stored untested: <b>{untested}</b>\n"
            "\U0001f480 No answer: <b>{dead}</b>\n"
            "\u26a0\ufe0f Below the floor: <b>{weak}</b>\n"
            "\u23ed Skipped (family, duplicate, unparseable): <b>{skipped}</b>\n{rule}\n"
            "\U0001f590 Pinned in this family: <b>{pinned}</b>/{total} healthy\n"
            "\U0001f3ca Whole {family} pool: <b>{pool}</b>/{target}\n"
            "\u23f1 Took: <b>{secs}</b>s\n{rule}\n{list}"
        ),
        "pool.manual_more": "\u2026 and <b>{count}</b> more.",
        "pool.manual_untested_note": (
            "\u26a0\ufe0f These could not be tested from this server (no {family} route). "
            "They are handed to users, always behind every measured endpoint."
        ),
        "pool.manual_failed": "\u26d4\ufe0f Hand entry failed: <code>{reason}</code>",

        # ------------------------------------------------- per line verdicts
        "pool.manual_v_stored": "healthy, in the pool",
        "pool.manual_v_untested": "stored untested",
        "pool.manual_v_dead": "no answer",
        "pool.manual_v_weak": "below the health floor",
        "pool.manual_v_family": "wrong family",
        "pool.manual_v_dup": "duplicate",
        "pool.manual_v_bad": "unparseable",
        "pool.manual_v_over": "over the per paste cap",

        # --------------------------------------------------- the manual screen
        "pool.manual_screen": (
            "\U0001f590 <b>Hand entered endpoints</b>\n{rule}\n"
            "You typed these in. No automatic cleanup deletes them: a pinned endpoint "
            "that dies is sidelined, and it revives by itself when it answers again.\n{rule}\n{list}"
        ),
        "pool.manual_family": (
            "\n<b>{family}</b> \u2192 {operator}\n"
            "\u2764\ufe0f healthy: <b>{healthy}</b>/{total} \u00b7 \U0001f552 untested: <b>{untested}</b>\n"
        ),
        "pool.manual_family_empty": "\u2014 nothing pinned yet.",
        "pool.manual_check_started": (
            "\U0001fa7a <b>Re-checking the pinned endpoints</b>\n{rule}\n"
            "Only the ones you entered, not the whole pool."
        ),
        "pool.manual_check_done": (
            "\U0001fa7a <b>Pinned endpoint check done</b>\n{rule}\n"
            "\U0001f50d Checked: <b>{checked}</b>\n"
            "\u2705 Alive: <b>{alive}</b>\n"
            "\U0001f480 Sidelined: <b>{dead}</b>\n"
            "\u23ed Not testable here: <b>{skipped}</b>\n{rule}\n"
            "\U0001f590 IPv4 <b>{v4}</b>/{v4all} \u00b7 IPv6 <b>{v6}</b>/{v6all}"
        ),
        "pool.manual_clear_ask": (
            "\U0001f5d1 <b>Clear the manual {family} list</b>\n{rule}\n"
            "<b>{count}</b> hand entered endpoint(s) will be deleted. "
            "There is no undo \u2014 sure?"
        ),
        "pool.manual_cleared": "\U0001f5d1 {count} manual {family} endpoint(s) cleared",
    },
}
