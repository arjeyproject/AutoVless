"""Copy for the Configurations screen, the real ping test and the Proxy Chain.

Kept in its own catalogue so the whole feature's wording lives in one file,
following the TURBO convention. Merged into CATALOG before PAYMENT/PRO, so the
older catalogues still win any key they already own.
"""

RLM = "\u200f"

CONFIGS: dict[str, dict[str, str]] = {
    "fa": {
        # ------------------------------------------------------------ buttons
        "btn.configs": "\u2699\ufe0f \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627",
        "btn.test_all": "\U0001f52c \u062a\u0633\u062a \u0647\u0645\u0647",
        "btn.refresh_list": "\u267b\ufe0f \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc",
        "btn.details": "\U0001f484 \u062c\u0632\u0626\u06cc\u0627\u062a",
        "btn.test_one": "\U0001f52c \u062a\u0633\u062a",
        "btn.toggle": "\u23f8\ufe0f \u063a\u06cc\u0631\u0641\u0639\u0627\u0644",
        "btn.enable": "\u25b6\ufe0f \u0641\u0639\u0627\u0644",
        "btn.remove": "\U0001f5d1 \u062d\u0630\u0641",
        "btn.chain": "\U0001f517 \u0632\u0646\u062c\u06cc\u0631 \u067e\u0631\u0648\u06a9\u0633\u06cc",
        "btn.chain_add": "\u2795 \u0633\u0627\u062e\u062a \u0632\u0646\u062c\u06cc\u0631 \u062c\u062f\u06cc\u062f",
        "btn.chain_export": "\U0001f4e5 \u062f\u0631\u06cc\u0627\u0641\u062a \u06a9\u0627\u0646\u0641\u06cc\u06af \u0632\u0646\u062c\u06cc\u0631",
        "btn.chain_test": "\U0001f52c \u062a\u0633\u062a \u0632\u0646\u062c\u06cc\u0631",
        "btn.sort": "\u21c5 \u0645\u0631\u062a\u0628\u200c\u0633\u0627\u0632\u06cc",
        "btn.filter": "\u2699\ufe0f \u0641\u06cc\u0644\u062a\u0631",
        # ------------------------------------------------------------- screen
        "configs_screen": (
            "\u200f\U0001f9ec <b>\u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u067e\u0646\u0644</b> \u00b7 {count} \u0645\u0648\u0631\u062f\n"
            "\u200f{rule}\n"
            "{cards}\n\n"
            "\u200f\U0001f4a1 \u062a\u0633\u062a \u0648\u0627\u0642\u0639\u06cc \u0627\u0632 \u0633\u0631\u0648\u0631 \u0631\u0628\u0627\u062a \u0627\u0646\u062c\u0627\u0645 \u0645\u06cc\u200c\u0634\u0648\u062f: \u062a\u0627\u0646\u0644 \u0648\u0627\u0642\u0639\u06cc \u0628\u0627\u0632 \u0645\u06cc\u200c\u0634\u0648\u062f\u060c "
            "\u0622\u06cc\u200c\u067e\u06cc \u062e\u0631\u0648\u062c\u06cc \u0648 \u067e\u06cc\u0646\u06af \u062f\u0631\u0633\u062a \u0627\u0646\u062f\u0627\u0632\u0647\u002e\u06af\u06cc\u0631\u06cc \u0645\u06cc\u200c\u0634\u0648\u062f."
        ),
        "config_row_online": "\U0001f7e2 #{i} \u00b7 <code>{addr}</code> \u00b7 {flag} {ping} \u00b7 \u062e\u0631\u0648\u062c\u06cc <code>{exit}</code>",
        "config_row_offline": "\U0001f534 #{i} \u00b7 <code>{addr}</code> \u00b7 {error}",
        "config_row_unknown": "\u26aa #{i} \u00b7 <code>{addr}</code> \u00b7 \u062a\u0633\u062a \u0646\u0634\u062f\u0647",
        "config_row_disabled": "\u26d4 #{i} \u00b7 <code>{addr}</code> \u00b7 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644",
        "config_row_testing": "\U0001f7e1 #{i} \u00b7 <code>{addr}</code> \u00b7 \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a...",
        "configs_empty": "\u200f\U0001f4ed \u0647\u06cc\u0686 \u06a9\u0627\u0646\u0641\u06cc\u06af\u06cc \u0628\u0631\u0627\u06cc \u0646\u0645\u0627\u06cc\u0634 \u0646\u06cc\u0633\u062a.",
        "configs_filter_note": "\u200f\U0001f50d \u0641\u06cc\u0644\u062a\u0631: {filter} \u00b7 \u0645\u0631\u062a\u0628\u200c\u0633\u0627\u0632\u06cc: {sort}",
        # -------------------------------------------------------------- detail
        "config_detail": (
            "\u200f\U0001f4cb <b>\u06a9\u0627\u0646\u0641\u06cc\u06af #{i}</b>\n"
            "\u200f{rule}\n"
            "\u200f\U0001f310 \u0647\u0627\u0633\u062a: <code>{host}</code>\n"
            "\u200f\U0001f4cd \u0633\u0631\u0648\u0631: <code>{addr}</code>\n"
            "\u200f\U0001f510 \u0627\u0645\u0646\u06cc\u062a: {security} \u00b7 \u0634\u0628\u06a9\u0647: {transport}\n"
            "\u200f\U0001f3db \u06a9\u0644\u0627\u0633\u062a\u0631: {colo}\n"
            "\u200f\U0001f3d7 \u0622\u06cc\u200c\u067e\u06cc \u0633\u0631\u0648\u0631: <code>{server_ip}</code>\n"
            "\u200f\U0001f30d \u0622\u06cc\u200c\u067e\u06cc \u062e\u0631\u0648\u062c\u06cc: {exit_line}\n"
            "\u200f\U0001f321 \u067e\u06cc\u0646\u06af: {ping_line}\n"
            "\u200f\U0001f552 \u0622\u062e\u0631\u06cc\u0646 \u062a\u0633\u062a: {tested_line}\n"
            "\u200f\u2757 \u062e\u0637\u0627: {error_line}"
        ),
        "exit_unknown": "\u062a\u0633\u062a \u0646\u0634\u062f\u0647",
        "no_error": "-",
        "never": "\u0647\u0631\u06af\u0632",
        # --------------------------------------------------------------- test
        "testing_all": "\u200f\U0001f52c \u062a\u0633\u062a \u0647\u0645\u0647\u002e\u06cc \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627 \u0634\u0631\u0648\u0639 \u0634\u062f... {done}/{total}",
        "testing_one": "\u200f\U0001f52c \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a \u06a9\u0627\u0646\u0641\u06cc\u06af #{i}...",
        "test_all_done": "\u200f\u2705 \u062a\u0633\u062a \u0647\u0645\u0647 \u062a\u0645\u0627\u0645 \u0634\u062f: {ok_count} \u0631\u0648\u0634\u0646\u060c {bad_count} \u062e\u0627\u0645\u0648\u0634.",
        "test_still_running": "\u23f3 \u062a\u0633\u062a \u0647\u0645\u0647 \u0647\u0646\u0648\u0632 \u062f\u0631 \u062c\u0631\u06cc\u0627\u0646 \u0627\u0633\u062a.",
        # -------------------------------------------------------------- push
        "push_started": "\u200f\U0001f4e4 \u062f\u0631 \u062d\u0627\u0644 \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u067e\u0646\u0644 \u0628\u0627 \u062a\u063a\u06cc\u06cc\u0631\u0627\u062a...",
        "push_done": "\u200f\u2705 \u067e\u0646\u0644 \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0634\u062f \u0648 \u062a\u063a\u06cc\u06cc\u0631\u0627\u062a \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.",
        "push_failed": "\u200f\u274c \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u067e\u0646\u0644 \u0634\u06a9\u0633\u062a: <code>{reason}</code>",
        "delete_confirm_cfg": "\u200f\u26a0\ufe0f \u062d\u0630\u0641 \u06a9\u0627\u0646\u0641\u06cc\u06af #{i} (<code>{addr}</code>)\u061f \u0627\u06cc\u0646 \u0627\u0646\u062f\u0631\u0633 \u0627\u0632 \u067e\u0646\u0644 \u0628\u0631\u062f\u0627\u0634\u062a\u0647 \u0645\u06cc\u200c\u0634\u0648\u062f \u0648 \u067e\u0646\u0644 \u062f\u0648\u0628\u0627\u0631\u0647 \u062f\u06cc\u067e\u0644\u0648\u06cc \u0645\u06cc\u200c\u0634\u0648\u062f.",
        "config_removed": "\u200f\U0001f5d1 \u06a9\u0627\u0646\u0641\u06cc\u06af #{i} \u062d\u0630\u0641 \u0648 \u067e\u0646\u0644 \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0634\u062f.",
        "config_toggled": "\u200f{state} \u06a9\u0627\u0646\u0641\u06cc\u06af #{i} \u00b7 \u067e\u0646\u0644 \u062f\u0631 \u067e\u0633\u200c\u0632\u0645\u06cc\u0646 \u0628\u0631\u0648\u0632\u0631\u0633\u0627\u0646\u06cc \u0645\u06cc\u200c\u0634\u0648\u062f.",
        "state_on": "\u25b6\ufe0f \u0641\u0639\u0627\u0644 \u0634\u062f:",
        "state_off": "\u23f8\ufe0f \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0634\u062f:",
        # --------------------------------------------------------------- chain
        "chain_screen": (
            "\u200f\U0001f517 <b>\u0632\u0646\u062c\u06cc\u0631 \u067e\u0631\u0648\u06a9\u0633\u06cc</b>\n"
            "\u200f{rule}\n{chains}\n\n"
            "\u200f\U0001f4a1 \u062a\u0631\u0627\u0641\u06cc\u06a9 \u0628\u0647 \u062a\u0631\u062a\u06cc\u0628 \u0627\u0632 \u0647\u0645\u0647 \u0647\u0627\u067e\u200c\u0647\u0627 \u0631\u062f \u0645\u06cc\u200c\u0634\u0648\u062f\u061b \u0622\u062e\u0631\u06cc\u0646 \u0647\u0627\u067e \u0622\u06cc\u200c\u067e\u06cc \u062e\u0631\u0648\u062c\u06cc \u0631\u0627 \u062a\u0639\u06cc\u06cc\u0646 \u0645\u06cc\u200c\u06a9\u0646\u062f. "
            "\u062f\u0631\u06cc\u0627\u0641\u062a \u0641\u0627\u06cc\u0644\u060c \u06cc\u06a9 \u06a9\u0627\u0646\u0641\u06cc\u06af \u0648\u0627\u0642\u0639\u06cc Xray \u0645\u06cc\u200c\u062f\u0647\u062f \u06a9\u0647 \u0647\u0627\u067e\u200c\u0647\u0627 \u0631\u0627 \u0648\u0627\u0642\u0639\u0627\u064b \u0632\u0646\u062c\u06cc\u0631 \u0645\u06cc\u200c\u06a9\u0646\u062f."
        ),
        "chain_none": "\u200f\U0001f4ed \u0647\u0646\u0648\u0632 \u0632\u0646\u062c\u06cc\u0631\u06cc \u0633\u0627\u062e\u062a\u0647 \u0646\u0634\u062f\u0647.",
        "chain_row": "\u200f{state_mark} <b>{name}</b> \u00b7 {visual}\n\u200f   {status_line}",
        "chain_visual": "\U0001f4f1 \u2190 {hops} \u2190 \U0001f310",
        "chain_enabled_mark": "\u2705",
        "chain_disabled_mark": "\u26aa",
        "chain_status_ok": "\u0648\u0636\u0639\u06cc\u062a: \u0631\u0648\u0634\u0646 \u00b7 \u067e\u06cc\u0646\u06af {ping} \u00b7 \u062e\u0631\u0648\u062c\u06cc {flag} <code>{exit}</code>",
        "chain_status_bad": "\u0648\u0636\u0639\u06cc\u062a: \u062e\u0631\u0627\u0628 \u00b7 {error}",
        "chain_status_untested": "\u0648\u0636\u0639\u06cc\u062a: \u062a\u0633\u062a \u0646\u0634\u062f\u0647",
        "chain_add_prompt": (
            "\u200f\U0001f517 <b>\u0633\u0627\u062e\u062a \u0632\u0646\u062c\u06cc\u0631 \u2014 \u0647\u0627\u067e {i}</b>\n"
            "\u200f{rule}\n"
            "\u200f\u06cc\u06a9 \u0644\u06cc\u0646\u06a9 \u067e\u0631\u0648\u06a9\u0633\u06cc \u0628\u0641\u0631\u0633\u062a (vless / trojan / ss / socks5 / http) \u06cc\u0627 \u06cc\u06a9\u06cc \u0627\u0632 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627\u06cc \u067e\u0646\u0644 \u0631\u0627 \u0627\u0646\u062a\u062e\u0627\u0628 \u06a9\u0646.\n\n"
            "\u200f\U0001f6a8 \u0647\u0627\u067e \u0627\u0648\u0644 \u0628\u0627\u06cc\u062f \u0645\u0633\u062a\u0642\u06cc\u0645 \u0627\u0632 \u062f\u0633\u062a\u06af\u0627\u0647 \u062f\u0633\u062a\u0631\u0633\u06cc\u200c\u067e\u0630\u06cc\u0631 \u0628\u0627\u0634\u062f. \u062d\u062f\u0627\u06a9\u062b\u0631 {max} \u0647\u0627\u067e."
        ),
        "chain_current": "\u200f\U0001f517 \u0647\u0627\u067e\u200c\u0647\u0627\u06cc \u0641\u0639\u0644\u06cc: {visual}",
        "chain_pick": "##{i} \u00b7 {addr}",
        "chain_done": "\u2705 \u067e\u0627\u06cc\u0627\u0646 \u0648 \u0630\u062e\u06cc\u0631\u0647",
        "chain_saved": "\u200f\u2705 \u0632\u0646\u062c\u06cc\u0631 \u00ab{name}\u00bb \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f. \u0628\u0631\u0627\u06cc \u0627\u0633\u062a\u0641\u0627\u062f\u0647\u060c \u062a\u0633\u062a \u06a9\u0646 \u0648 \u0641\u0639\u0627\u0644\u0634 \u06a9\u0646.",
        "chain_bad_hop": "\u200f\u274c \u0644\u06cc\u0646\u06a9 \u0645\u0639\u062a\u0628\u0631 \u0646\u06cc\u0633\u062a: {reason}",
        "chain_loop": "\u200f\u274c \u0627\u06cc\u0646 \u0633\u0631\u0648\u0631 \u062f\u0631 \u0632\u0646\u062c\u06cc\u0631 \u062a\u06a9\u0631\u0627\u0631 \u0634\u062f\u0647 \u0627\u0633\u062a (\u062d\u0644\u0642\u0647 \u0645\u0645\u0646\u0648\u0639).",
        "chain_too_long": "\u200f\u274c \u062d\u062f\u0627\u06a9\u062b\u0631 {max} \u0647\u0627\u067e \u0645\u062c\u0627\u0632 \u0627\u0633\u062a.",
        "chain_hop_core": "\u200f\u274c \u0627\u06cc\u0646 \u0647\u0627\u067e \u0628\u0647 \u0647\u0633\u062a\u0647\u0020xray \u0646\u06cc\u0627\u0632 \u062f\u0627\u0631\u062f \u06a9\u0647 \u0631\u0648\u06cc \u0633\u0631\u0648\u0631 \u0646\u0635\u0628 \u0646\u06cc\u0633\u062a.",
        "chain_empty": "\u200f\u274c \u0632\u0646\u062c\u06cc\u0631 \u062e\u0627\u0644\u06cc \u0627\u0633\u062a.",
        "chain_detail": (
            "\u200f\U0001f517 <b>{name}</b>\n"
            "\u200f{rule}\n"
            "\u200f{visual}\n\n"
            "\u200f{status_line}"
        ),
        "chain_test_running": "\u200f\U0001f52c \u062f\u0631 \u062d\u0627\u0644 \u062a\u0633\u062a \u0632\u0646\u062c\u06cc\u0631...",
        "chain_test_done": "\u200f{mark} \u062a\u0633\u062a \u0632\u0646\u062c\u06cc\u0631 \u062a\u0645\u0627\u0645 \u0634\u062f: {status_line}",
        "chain_core_missing": "\u200f\u26a0\ufe0f \u0647\u0633\u062a\u0647\u0020xray \u0631\u0648\u06cc \u0633\u0631\u0648\u0631 \u0646\u0635\u0628 \u0646\u06cc\u0633\u062a\u061b \u062a\u0633\u062a \u0648\u0627\u0642\u0639\u06cc \u0632\u0646\u062c\u06cc\u0631 \u0645\u0645\u06a9\u0646 \u0646\u06cc\u0633\u062a.",
        "chain_export_done": "\u200f\U0001f4e5 \u0627\u06cc\u0646 \u0641\u0627\u06cc\u0644 \u0631\u0627 \u062f\u0631 Xray/v2rayN/Hiddify \u0648\u0627\u0631\u062f \u06a9\u0646. \u0647\u0627\u067e\u200c\u0647\u0627 \u0648\u0627\u0642\u0639\u0627\u064b \u0632\u0646\u062c\u06cc\u0631 \u0634\u062f\u0647\u200c\u0627\u0646\u062f (proxySettings).",
        "chain_enabled_on": "\u200f\u2705 \u0632\u0646\u062c\u06cc\u0631 \u0641\u0639\u0627\u0644 \u0634\u062f \u2014 \u062f\u0631 \u062e\u0631\u0648\u062c\u06cc\u200c\u0647\u0627\u06cc \u0641\u0631\u06af\u0645\u0646\u062a \u0627\u0639\u0645\u0627\u0644 \u0645\u06cc\u200c\u0634\u0648\u062f.",
        "chain_enabled_off": "\u200f\u26aa \u0632\u0646\u062c\u06cc\u0631 \u063a\u06cc\u0631\u0641\u0639\u0627\u0644 \u0634\u062f.",
        "chain_deleted": "\u200f\U0001f5d1 \u0632\u0646\u062c\u06cc\u0631 \u062d\u0630\u0641 \u0634\u062f.",
        "chain_name_prompt": "\u200f\U0001f4dd \u06cc\u06a9 \u0646\u0627\u0645 \u0628\u0631\u0627\u06cc \u0627\u06cc\u0646 \u0632\u0646\u062c\u06cc\u0631 \u0628\u0641\u0631\u0633\u062a (\u06cc\u0627 /done \u0628\u0627 \u0646\u0627\u0645 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636):",
        # ---------------------------------------------------------- sort/filter
        "sort_ping": "\u06a9\u0645\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af",
        "sort_status": "\u0648\u0636\u0639\u06cc\u062a",
        "sort_proto": "\u067e\u0631\u0648\u062a\u06a9\u0644",
        "sort_index": "\u062a\u0631\u062a\u06cc\u0628 \u067e\u06cc\u0634\u200c\u0641\u0631\u0636",
        "flt_all": "\u0647\u0645\u0647",
        "flt_online": "\u0631\u0648\u0634\u0646\u200c\u0647\u0627",
        "flt_offline": "\u062e\u0627\u0645\u0648\u0634\u200c\u0647\u0627",
        "flt_tls": "TLS",
        "flt_http": "HTTP",
        "no_match": "\u200f\U0001f4ed \u0628\u0627 \u0627\u06cc\u0646 \u0641\u06cc\u0644\u062a\u0631 \u0686\u06cc\u0632\u06cc \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f.",
    },
    "en": {
        "btn.configs": "\u2699\ufe0f Configurations",
        "btn.test_all": "\U0001f52c Test all",
        "btn.refresh_list": "\u267b\ufe0f Refresh",
        "btn.details": "\U0001f484 Details",
        "btn.test_one": "\U0001f52c Test",
        "btn.toggle": "\u23f8\ufe0f Disable",
        "btn.enable": "\u25b6\ufe0f Enable",
        "btn.remove": "\U0001f5d1 Remove",
        "btn.chain": "\U0001f517 Proxy chain",
        "btn.chain_add": "\u2795 New chain",
        "btn.chain_export": "\U0001f4e5 Export chain config",
        "btn.chain_test": "\U0001f52c Test chain",
        "btn.sort": "\u21c5 Sort",
        "btn.filter": "\u2699\ufe0f Filter",
        "configs_screen": (
            "\U0001f9ec <b>Panel configurations</b> \u00b7 {count}\n"
            "{rule}\n"
            "{cards}\n\n"
            "\U0001f4a1 The test is real: it opens the actual tunnel from the bot's "
            "server and measures the true exit IP and latency."
        ),
        "config_row_online": "\U0001f7e2 #{i} \u00b7 <code>{addr}</code> \u00b7 {flag} {ping} \u00b7 exit <code>{exit}</code>",
        "config_row_offline": "\U0001f534 #{i} \u00b7 <code>{addr}</code> \u00b7 {error}",
        "config_row_unknown": "\u26aa #{i} \u00b7 <code>{addr}</code> \u00b7 untested",
        "config_row_disabled": "\u26d4 #{i} \u00b7 <code>{addr}</code> \u00b7 disabled",
        "config_row_testing": "\U0001f7e1 #{i} \u00b7 <code>{addr}</code> \u00b7 testing...",
        "configs_empty": "\U0001f4ed Nothing to list yet.",
        "configs_filter_note": "\U0001f50d filter: {filter} \u00b7 sort: {sort}",
        "config_detail": (
            "\U0001f4cb <b>Config #{i}</b>\n"
            "{rule}\n"
            "\U0001f310 host: <code>{host}</code>\n"
            "\U0001f4cd server: <code>{addr}</code>\n"
            "\U0001f510 security: {security} \u00b7 transport: {transport}\n"
            "\U0001f3db colo: {colo}\n"
            "\U0001f3d7 server IP: <code>{server_ip}</code>\n"
            "\U0001f30d exit IP: {exit_line}\n"
            "\U0001f321 ping: {ping_line}\n"
            "\U0001f552 last test: {tested_line}\n"
            "\u2757 error: {error_line}"
        ),
        "exit_unknown": "untested",
        "no_error": "-",
        "never": "never",
        "testing_all": "\U0001f52c Testing every config... {done}/{total}",
        "testing_one": "\U0001f52c Testing config #{i}...",
        "test_all_done": "\u2705 Test run finished: {ok_count} online, {bad_count} offline.",
        "test_still_running": "\u23f3 The batch test is still running.",
        "push_started": "\U0001f4e4 Pushing the panel update...",
        "push_done": "\u2705 Panel updated and saved.",
        "push_failed": "\u274c Panel update failed: <code>{reason}</code>",
        "delete_confirm_cfg": "\u26a0\ufe0f Remove config #{i} (<code>{addr}</code>)? The endpoint leaves the panel and the panel re-deploys.",
        "config_removed": "\U0001f5d1 Config #{i} removed and the panel updated.",
        "config_toggled": "{state} config #{i} \u00b7 the panel updates in the background.",
        "state_on": "\u25b6\ufe0f enabled",
        "state_off": "\u23f8\ufe0f disabled",
        "chain_screen": (
            "\U0001f517 <b>Proxy chain</b>\n"
            "{rule}\n{chains}\n\n"
            "\U0001f4a1 Traffic walks the hops in order; the LAST hop decides the exit "
            "address. The exported file is a real Xray config with the hops wired "
            "through proxySettings."
        ),
        "chain_none": "\U0001f4ed No chains yet.",
        "chain_row": "{state_mark} <b>{name}</b> \u00b7 {visual}\n   {status_line}",
        "chain_visual": "\U0001f4f1 \u2192 {hops} \u2192 \U0001f310",
        "chain_enabled_mark": "\u2705",
        "chain_disabled_mark": "\u26aa",
        "chain_status_ok": "status: online \u00b7 ping {ping} \u00b7 exit {flag} <code>{exit}</code>",
        "chain_status_bad": "status: offline \u00b7 {error}",
        "chain_status_untested": "status: untested",
        "chain_add_prompt": (
            "\U0001f517 <b>New chain \u2014 hop {i}</b>\n"
            "{rule}\n"
            "Send a proxy link (vless / trojan / ss / socks5 / http) or pick one of "
            "your panel configs below.\n\n"
            "\U0001f6a8 The first hop must be reachable from the device directly. Up to {max} hops."
        ),
        "chain_current": "\U0001f517 current hops: {visual}",
        "chain_pick": "#{i} \u00b7 {addr}",
        "chain_done": "\u2705 finish",
        "chain_saved": "\u2705 chain \u201c{name}\u201d saved. Test it, then enable it.",
        "chain_bad_hop": "\u274c not a valid link: {reason}",
        "chain_loop": "\u274c that server is already in the chain (loops are not allowed).",
        "chain_too_long": "\u274c at most {max} hops.",
        "chain_hop_core": "\u274c this hop needs the xray core, which this server lacks.",
        "chain_empty": "\u274c the chain is empty.",
        "chain_detail": "\U0001f517 <b>{name}</b>\n{rule}\n{visual}\n\n{status_line}",
        "chain_test_running": "\U0001f52c Testing the chain...",
        "chain_test_done": "{mark} chain test finished: {status_line}",
        "chain_core_missing": "\u26a0\ufe0f the xray core is not installed on this server; a real chain test is not possible.",
        "chain_export_done": "\U0001f4e5 Import this file into Xray/v2rayN/Hiddify. The hops are genuinely chained (proxySettings).",
        "chain_enabled_on": "\u2705 chain enabled - it drives the fragment exports.",
        "chain_enabled_off": "\u26aa chain disabled.",
        "chain_deleted": "\U0001f5d1 chain deleted.",
        "chain_name_prompt": "\U0001f4dd send a name for this chain (or /done for the default):",
        "sort_ping": "lowest ping",
        "sort_status": "status",
        "sort_proto": "protocol",
        "sort_index": "default order",
        "flt_all": "all",
        "flt_online": "online",
        "flt_offline": "offline",
        "flt_tls": "TLS",
        "flt_http": "HTTP",
        "no_match": "\U0001f4ed nothing matches this filter.",
    },
}

# Appended late so the merge order cannot bury it: an abuse-flagged account
# needs its own honest screen, in both languages, with the way out named.
CONFIGS["fa"]["account_blocked"] = (
    "\u200f\U0001f6a8 <b>\u0627\u06a9\u0627\u0646\u062a Cloudflare \u0634\u0645\u0627 \u062a\u0648\u0633\u0637 Cloudflare \u0645\u0633\u062f\u0648\u062f \u0634\u062f\u0647 \u0627\u0633\u062a</b>\n"
    "\u200f{rule}\n"
    "\u200fCloudflare \u0646\u0648\u0634\u062a\u0646 \u0631\u0648\u06cc Pages \u0648 \u0627\u062c\u0631\u0627\u06cc Workers \u0627\u06cc\u0646 \u0627\u06a9\u0627\u0646\u062a \u0631\u0627 \u0628\u0647 \u062f\u0644\u06cc\u0644 \u0628\u0631\u0631\u0633\u06cc \u062a\u062e\u0644\u0641 \u0645\u062a\u0648\u0642\u0641 \u06a9\u0631\u062f\u0647. "
    "\u067e\u0646\u0644 \u0641\u0639\u0644\u0627 \u0627\u0632 \u062f\u06cc\u067e\u0644\u0648\u06cc \u0642\u0628\u0644\u06cc \u062e\u0648\u062f \u0633\u0631\u0648 \u0645\u06cc\u200c\u0634\u0648\u062f \u0648 \u06a9\u0627\u0646\u0641\u06cc\u06af\u200c\u0647\u0627 \u062a\u0627 \u0645\u0627\u0646\u062f\u0646 \u0622\u0646 \u062f\u06cc\u067e\u0644\u0648 \u06a9\u0627\u0631 \u0645\u06cc\u200c\u06a9\u0646\u0646\u062f.\n\n"
    "\u200f\u2757 \u0631\u0627\u0647 \u062d\u0644:\n"
    "\u200f1. \u0628\u0647 <code>abusereply@cloudflare.com</code> \u0627\u06cc\u0645\u06cc\u0644 \u0628\u0632\u0646\u06cc\u062f \u0648 \u062f\u0631\u062e\u0648\u0627\u0633\u062a \u0628\u0631\u0631\u0633\u06cc \u0628\u062f\u0647\u06cc\u062f.\n"
    "\u200f2. \u06cc\u0627 \u0628\u0627 \u06cc\u06a9 \u0627\u06a9\u0627\u0646\u062a Cloudflare \u062a\u0627\u0632\u0647 \u0648 \u06cc\u06a9 \u062f\u0627\u0645\u0646\u0647\u0020\u062c\u062f\u06cc\u062f\u060c \u0627\u0632 \u062f\u06a9\u0645\u0647\u0020\u0633\u0627\u062e\u062a \u067e\u0646\u0644 \u06cc\u06a9 \u067e\u0646\u0644 \u062a\u0627\u0632\u0647 \u0628\u0633\u0627\u0632\u06cc\u062f."
)
CONFIGS["en"]["account_blocked"] = (
    "\U0001f6a8 <b>Your Cloudflare account has been flagged by Cloudflare</b>\n"
    "{rule}\n"
    "Cloudflare stopped Pages writes and Workers executions on this account pending "
    "abuse review. The panel keeps serving from its last healthy deployment, so your "
    "current configs keep working until that deployment is removed.\n\n"
    "\u2757 The way out:\n"
    "1. Email <code>abusereply@cloudflare.com</code> and ask for a review.\n"
    "2. Or build a fresh panel with a new Cloudflare account and a domain."
)
