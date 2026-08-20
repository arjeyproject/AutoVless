"""English copy."""

EN: dict[str, str] = {
    # ------------------------------------------------------------- buttons
    "btn.build": "\U0001f680 Build turbo panel",
    "btn.panel": "\U0001f39b My panel",
    "btn.warp": "\U0001f6e1 Create WARP / WireGuard",
    "btn.convert": "\U0001f504 Convert link",
    "btn.apps": "\U0001f4f1 Apps and downloads",
    "btn.guide": "\U0001f4d6 Connection guide",
    "btn.status": "\U0001f4ca Live network status",
    "btn.operator": "\U0001f4f6 My operator",
    "btn.support": "\U0001f4ac Support",
    "btn.donate": "\u2764\ufe0f Support us",
    "btn.lang": "\U0001f310 \u0641\u0627\u0631\u0633\u06cc",
    "btn.admin": "\U0001f6e0 Admin panel",
    "btn.back": "\u2b05\ufe0f Back",
    "btn.cf_signup": "\u2601\ufe0f Sign up at Cloudflare",
    "btn.cf_token": "\U0001f511 Get Cloudflare token",
    "btn.qr": "\U0001f4f7 QR code",
    "btn.sub": "\U0001f517 Subscription link",
    "btn.clash": "\U0001f9e9 Clash export",
    "btn.singbox": "\U0001f4e6 sing-box export",
    "btn.single": "\U0001f4dd Individual configs",
    "btn.ping": "\U0001f4e1 Live ping test",
    "btn.rescan": "\u26a1 Rescan clean IPs",
    "btn.rebuild": "\U0001f504 Rebuild panel",
    "btn.delete": "\U0001f5d1 Delete panel",
    "btn.confirm": "\u2705 Yes, do it",
    "btn.cancel": "\u2716\ufe0f Cancel",
    "btn.joined": "\u2705 I joined",
    "btn.stats": "\U0001f4c8 Stats",
    "btn.users": "\U0001f465 Users",
    "btn.broadcast": "\U0001f4e3 Broadcast",
    "btn.channels": "\U0001f512 Channel lock",
    "btn.engine": "\u2699\ufe0f Scan engine",
    "btn.options": "\U0001f39a Options",
    "btn.panels": "\U0001f5c2 Panels",
    "btn.logs": "\U0001f9fe Events",
    "btn.backup": "\U0001f4be Backup",
    "btn.add": "\u2795 Add",
    "btn.scan_now": "\u26a1 Scan now",
    # ---------------------------------------------------------------- main
    "main_menu": (
        "\u26a1 <b>{brand}</b> \u00b7 turbo build \u26a1\n{rule}\n"
        "\U0001f44b Hey <b>{name}</b>!\n"
        "I build a private panel on your own Cloudflare account and mount the fastest clean IPs "
        "on your configs automatically.\n\n"
        "\U0001f525 <b>Live engine</b>\n"
        "\U0001f4e1 Clean IPs ready: <b>{pool}</b>\n"
        "\U0001f680 Under 700 ms: <b>{fast}</b>\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f6e1 Healthy relays: <b>{healthy}</b>\n\n"
        "\U0001f447 Pick an option:"
    ),
    "welcome_note": (
        "\U0001f331 <b>{brand}</b> is free and built so people can reach an open internet.\n"
        "We ask for nothing. If it works for you, pass it on to one more person. \u2764\ufe0f"
    ),
    "support_us": (
        "\u2764\ufe0f <b>Support us</b>\n{rule}\n"
        "{brand} is free and sells no subscriptions.\n\n"
        "\u2022 Share the bot with a friend\n"
        "\u2022 Star the project on GitHub\n"
        "\u2022 Send bugs and ideas to support\n\n"
        "\U0001f34a Every config you pass on opens one more window."
    ),
    # --------------------------------------------------------------- build
    "token_intro": (
        "\U0001f680 <b>Build a turbo panel</b>\n{rule}\n"
        "1\ufe0f\u20e3 No Cloudflare account yet? <b>Sign up</b> first.\n"
        "2\ufe0f\u20e3 Tap <b>Get Cloudflare token</b> (permissions are pre-selected).\n"
        "3\ufe0f\u20e3 In Cloudflare press <code>Continue to summary</code>, then <code>Create Token</code>.\n"
        "4\ufe0f\u20e3 Copy the token and paste it right here.\n\n"
        "\U0001f512 The token only works on your own account and is used only to create the Worker.\n"
        "\u23f1 Typical delivery time: 20 to 45 seconds \u26a1"
    ),
    "token_bad_format": "\u26a0\ufe0f That does not look like a Cloudflare token. Send the token only, without links or extra text.",
    "token_rejected": (
        "\u274c Cloudflare rejected this token.\n\n<b>Reason:</b> <code>{reason}</code>\n\n"
        "Use the \u201cGet Cloudflare token\u201d button again so the permissions are set correctly."
    ),
    "build_progress": "\u2699\ufe0f <b>Building your panel</b>\n{rule}\n{steps}",
    "step_verify": "Verifying token and account",
    "step_subdomain": "Preparing the workers.dev subdomain",
    "step_scan": "Selecting clean IPs",
    "step_deploy": "Uploading the Worker to your account",
    "step_health": "Health checking the panel",
    "no_clean_ip": "\u23f3 The clean IP pool is still warming up. Try again in about a minute.",
    "panel_ready": (
        "\U0001f389 <b>Your panel is ready!</b> \U0001f680\n{rule}\n"
        "\u23f1 Build time: <b>{seconds}</b> s\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f680 Under 700 ms: <b>{fast}</b> endpoints\n"
        "\U0001f4e6 Configs: <b>{count}</b>\n"
        "\U0001f9ea Protocol: <b>VLESS / WS</b>\n"
        "\U0001f50c Ports: <b>{ports}</b>\n"
        "\U0001f4f6 Operator: <b>{operator}</b>\n"
        "\U0001f310 Host: <code>{host}</code>\n\n"
        "\U0001f4a1 Run <b>Real Delay</b> in your client and pick the fastest entry.\n"
        "\U0001f525 Turn <b>Fragment</b> on for a steadier connection."
    ),
    "health_warn": (
        "\u26a0\ufe0f The Worker was created but is not answering yet. Cloudflare edge propagation can "
        "take up to a minute, then the configs come alive."
    ),
    "panel_none": "\U0001f4ed No panel yet. Start from \u201cBuild turbo panel\u201d.",
    "panel_overview": (
        "\U0001f39b <b>My panel</b>\n{rule}\n"
        "\U0001f310 Host: <code>{host}</code>\n"
        "\U0001f194 User id: <code>{uuid}</code>\n"
        "\U0001f4e6 Configs: <b>{count}</b>\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f504 Rebuilds: <b>{rebuilds}</b>\n"
        "\U0001f552 Updated: <b>{updated}</b>"
    ),
    "sub_links": (
        "\U0001f517 <b>Subscription links</b>\n{rule}\n"
        "<b>v2rayNG / Streisand / NekoBox</b>\n<code>{sub}</code>\n\n"
        "<b>Clash / Mihomo</b>\n<code>{clash}</code>\n\n"
        "<b>sing-box</b>\n<code>{singbox}</code>\n\n"
        "\u267b\ufe0f The link is permanent and refreshes after every rebuild."
    ),
    "single_configs": "\U0001f4dd <b>Individual configs</b>\n{rule}\nTap a config to copy it.",
    "qr_caption": "\U0001f4f7 {brand} subscription QR code",
    "ping_result": (
        "\U0001f4e1 <b>Live ping test</b>\n{rule}\n{rows}\n\n"
        "\u2139\ufe0f Measured from the bot server. Check real delay in your own client as well."
    ),
    "delete_confirm": (
        "\U0001f5d1 Are you sure? Worker <code>{script}</code> will be removed from your Cloudflare "
        "account and the configs will stop working."
    ),
    "deleted": "\u2705 Panel deleted.",
    "rebuilding": "\u267b\ufe0f Mounting fresh clean IPs...",
    "rebuilt": "\u2705 Panel updated with fresh clean IPs.",
    "token_missing": "\U0001f511 I need your Cloudflare token again for this. Send it now.",
    "scan_started": "\u26a1 A fresh scan started, hold on a moment...",
    # ---------------------------------------------------------------- info
    "network_status": (
        "\U0001f4ca <b>Live network status</b>\n{rule}\n"
        "\U0001f4e1 IP pool: <b>{total}</b>\n"
        "\u2705 Verified: <b>{verified}</b>\n"
        "\U0001f680 Under 700 ms: <b>{fast}</b>\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f50c Active ports: <b>{ports}</b>\n"
        "\u23f3 Last scan: <b>{updated}</b>\n"
        "\u2699\ufe0f Scanner: <b>{state}</b>\n\n"
        "\U0001f4cd Top datacenters: {colos}"
    ),
    "apps": (
        "\U0001f4f1 <b>Apps and downloads</b>\n{rule}\n"
        "\u2022 <b>Android:</b> v2rayNG \u00b7 NekoBox \u00b7 Hiddify\n"
        "\u2022 <b>iOS:</b> Streisand \u00b7 Shadowrocket \u00b7 FoXray\n"
        "\u2022 <b>Windows:</b> v2rayN \u00b7 Hiddify \u00b7 Nekoray\n"
        "\u2022 <b>macOS:</b> V2Box \u00b7 Streisand \u00b7 Hiddify\n\n"
        "\U0001f4a1 Paste the subscription link into the app's Subscription section, not the manual config field."
    ),
    "guide": (
        "\U0001f4d6 <b>Connection guide</b>\n{rule}\n"
        "1\ufe0f\u20e3 Install one of the recommended apps.\n"
        "2\ufe0f\u20e3 Add the subscription link under Subscription and hit Update.\n"
        "3\ufe0f\u20e3 Run a Real Delay test and select the fastest config.\n"
        "4\ufe0f\u20e3 Still stuck? Enable Fragment, then try the port 80 configs.\n"
        "5\ufe0f\u20e3 Nothing works? Use \u201cRescan clean IPs\u201d and then \u201cRebuild panel\u201d.\n\n"
        "\U0001f527 On mobile data, port 80 often behaves better; on fixed lines, port 443 usually wins."
    ),
    "operator_menu": (
        "\U0001f4f6 <b>My operator</b>\n{rule}\n"
        "Pick your operator and I will tailor the port and setting advice.\n\n"
        "Current: <b>{current}</b>"
    ),
    "operator_saved": "\u2705 Operator set to <b>{operator}</b>.\n\n\U0001f4a1 {tip}",
    "operator_unset": "not set",
    "convert_prompt": (
        "\U0001f504 <b>Convert link</b>\n{rule}\n"
        "Send one or more <code>vless://</code> links and I will return Clash, sing-box and a subscription blob."
    ),
    "convert_bad": "\u26a0\ufe0f No valid VLESS link found. The text must start with <code>vless://</code>.",
    "convert_done": "\u2705 Converted <b>{count}</b> configs.",
    "warp_building": "\U0001f6e1 Registering a fresh WARP identity...",
    "warp_ready": (
        "\U0001f6e1 <b>WARP / WireGuard ready</b>\n{rule}\n"
        "\U0001f511 Account type: <b>{account}</b>\n"
        "\U0001f4e1 Endpoint: <code>{endpoint}</code>\n\n"
        "Import the attached file into WireGuard or Hiddify."
    ),
    "warp_failed": "\u274c WARP registration failed. Try again in a moment.",
    # --------------------------------------------------------------- gating
    "join_required": (
        "\U0001f512 <b>Membership required</b>\n{rule}\n"
        "Join the channels below, then press \u201cI joined\u201d."
    ),
    "join_ok": "\u2705 Nice. Access unlocked.",
    "join_fail": "\u26a0\ufe0f You are not a member of every channel yet.",
    "maintenance": "\U0001f6e0 The bot is under maintenance. Check back shortly.",
    "banned": "\u26d4\ufe0f Your access to this bot has been revoked.",
    "builds_off": "\u23f8 Panel building is paused right now. Try again later.",
    "error_generic": "\u274c Something went wrong: <code>{reason}</code>",
    "cancelled": "Alright, cancelled.",
    "busy": "\u23f3 A request is already running, give it a second.",
}
