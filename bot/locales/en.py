"""English copy."""

EN: dict[str, str] = {
    # ------------------------------------------------------------- buttons
    "btn.build": "🚀 Build turbo panel",
    "btn.smart_scan": "🛡 Smart scan — IPs + WARP",
    "btn.back_home": "🏠 Back to main menu",
    "btn.panel": "🎛 My panel",
    "btn.warp": "🛡 Create WARP / WireGuard",
    "btn.apps": "📱 Apps and downloads",
    "btn.guide": "📖 Connection guide",
    "btn.support": "💬 Support",
    "btn.donate": "❤️ Support us",
    "btn.lang": "🌐 فارسی",
    "btn.admin": "🛠 Admin panel",
    "btn.back": "◀️ Back",
    "btn.cf_signup": "☁️ Sign up at Cloudflare",
    "btn.cf_token": "🔑 Get Cloudflare token",
    "btn.qr": "📷 QR code",
    "btn.sub": "🔗 All-in-one subscription",
    "btn.clash": "🧩 Clash export",
    "btn.singbox": "📦 sing-box export",
    "btn.single": "📝 Individual configs",
    "btn.copy_sub": "📋 Copy subscription link",
    "btn.copy_mix": "📋 Copy mixed link",
    "btn.copy_clash": "📋 Copy Clash link",
    "btn.copy_singbox": "📋 Copy sing-box link",
    "btn.ping": "📡 Live ping test",
    "btn.apply": "⚡ Apply fresh clean IPs",
    "btn.rescan": "🔍 Rescan the network",
    "btn.rebuild": "🔄 Full rebuild",
    "btn.delete": "🗑 Delete panel",
    "btn.confirm": "✅ Yes, do it",
    "btn.cancel": "✖️ Cancel",
    "btn.joined": "\u2705 I joined",
    "btn.stats": "📈 Stats",
    "btn.users": "👥 Users",
    "btn.broadcast": "📣 Broadcast",
    "btn.channels": "🔒 Channel lock",
    "btn.engine": "🛡 Smart scanner",
    "btn.options": "🎛 Options",
    "btn.panels": "🗂 Panels",
    "btn.logs": "🧾 Events",
    "btn.backup": "💾 Backup",
    "btn.add": "➕ Add",
    "btn.sync_now": "🤖 Push IPs to every panel",
    # ---------------------------------------------------------------- main
    "main_menu": (
        "\u26a1 <b>{brand}</b> \u00b7 turbo build\n{rule}\n"
        "\U0001f44b Hey <b>{name}</b>!\n"
        "I build a private panel on <b>your own</b> Cloudflare account, hunt down clean IPs and\n"
        "mount them on <b>every config</b> automatically. You do nothing.\n"
        "{rule}\n"
        "\U0001f525 <b>Live engine</b>\n"
        "\U0001f4e1 Clean IPs: <b>{pool}</b> \u00b7 verified: <b>{verified}</b>\n"
        "\U0001f680 Under 700 ms: <b>{fast}</b>\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f300 Self-healing hostnames: <b>{domains}</b>\n"
        "\U0001f6e1 Healthy relays: <b>{relays}</b>\n"
        "\U0001f916 Automatic IP rotation: <b>{pilot}</b>\n"
        "{rule}\n"
        "\U0001f49a Free, and staying free. If it works, pass it to one more person.\n"
        "\U0001f447 Pick an option:"
    ),
    "welcome_note": (
        "\U0001f331 <b>{brand}</b> is free and built so people can reach an open internet."
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
    "token_bad_format": "\u26a0\ufe0f That does not look like a Cloudflare token. Send the token only.",
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
        "\U0001f389 <b>Your panel is ready!</b>\n{rule}\n"
        "\u23f1 Build time: <b>{seconds}</b> s\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f680 Under 700 ms: <b>{fast}</b> endpoints\n"
        "\U0001f4e6 Configs: <b>{count}</b>\n"
        "\U0001f50c Ports: <b>{ports}</b>\n"
        "\U0001f4f6 Operator: <b>{operator}</b>\n"
        "\U0001f310 Host: <code>{host}</code>\n"
        "{rule}\n"
        "\U0001f517 <b>All-in-one subscription</b> — every config in one link:\n"
        "<code>{sub}</code>\n"
        "\U0001f4a5 Paste this single link into your client and hit Copy below.\n"
        "\U0001f916 Nothing left to do: the bot keeps mounting fresh clean IPs on this\n"
        "same subscription link. Just hit Update in your client now and then.\n"
        "\u26a1 Proxy Chain is on: your exit IP is static, so AI sites like Gemini and\n"
        "ChatGPT work without endless re-logins.\n"
        "\U0001f4a1 Run <b>Real Delay</b> and connect to the fastest entry."
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
        "\U0001f49f Tunnel: <b>{health}</b>\n"
        "\U0001f916 Last auto apply: <b>{synced}</b> ({syncs} total)\n"
        "\U0001f504 Rebuilds: <b>{rebuilds}</b> \u00b7 updated: <b>{updated}</b>\n"
        "{rule}\n"
        "\U0001f4a1 The subscription link never changes; what it serves refreshes on its own."
    ),
    "panel_health_ok": "\u2705 healthy",
    "panel_health_bad": "\u26a0\ufe0f checking",
    "sub_links": (
        "\U0001f517 <b>All-in-one subscription</b> — everything in one link\n{rule}\n"
        "This is the only link you need — every config, every port, every protocol:\n"
        "<code>{sub}</code>\n\n"
        "\u2705 Add it under Subscription in v2rayNG / Streisand / NekoBox / Hiddify and hit Update.\n"
        "\u267b\ufe0f The link is permanent; what it serves refreshes on its own."
    ),
    "sub_extras": (
        "\u2b07\ufe0f <b>Other formats</b> — only if your app insists:\n"
        "\U0001f9e9 Clash / Mihomo:\n<code>{clash}</code>\n"
        "\U0001f4e6 sing-box:\n<code>{singbox}</code>"
    ),
    "single_configs": (
        "\U0001f4dd <b>Individual configs</b>\n{rule}\nTap a config to copy it, or use the copy buttons below.\n"
        "\U0001f4a1 The all-in-one subscription is still the better path: the best IPs mount themselves.\n"
        "\u26a1 port 443 \u00b7 \U0001f7e1 port 80 \u00b7 \U0001f300 self-healing hostname"
    ),
    "qr_caption": "\U0001f4f7 {brand} subscription QR code",
    "ping_result": (
        "\U0001f4e1 <b>Live ping test</b>\n{rule}\n{rows}\n\n"
        "\u2139\ufe0f Measured from the bot server. Dead entries are demoted from the pool automatically."
    ),
    "applying": "\u26a1 Mounting the freshest clean IPs on this panel...",
    "applied": (
        "\u2705 <b>Clean IPs applied</b>\n{rule}\n"
        "\U0001f4e6 Fresh configs: <b>{count}</b>\n"
        "\U0001f3c6 Best ping: <b>{best}</b>\n"
        "\U0001f49f Tunnel: <b>{health}</b>\n\n"
        "\U0001f517 Your subscription link is unchanged. Hit Update in your client to pull them."
    ),
    "apply_failed": "\u274c Could not apply: <code>{reason}</code>",
    "delete_confirm": (
        "\U0001f5d1 Are you sure? Worker <code>{script}</code> will be removed from your Cloudflare "
        "account and the configs will stop working."
    ),
    "deleted": "\u2705 Panel deleted.",
    "rebuilding": "\u267b\ufe0f Rebuilding the panel...",
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
        "\U0001f300 Self-healing hostnames: <b>{domains}</b>\n"
        "\U0001f6e1 Healthy relays: <b>{relays}</b>\n"
        "\U0001f50c Active ports: <b>{ports}</b>\n"
        "\u23f3 Last scan: <b>{updated}</b>\n"
        "\u2699\ufe0f Scanner: <b>{state}</b> \u00b7 \U0001f916 autopilot: <b>{pilot}</b>\n"
        "{rule}\n"
        "\U0001f4cd Top datacenters: {colos}"
    ),
    "apps": "\U0001f4f1 <b>Apps and downloads</b>\n{rule}\nPick your device.",
    "guide": (
        "\U0001f4d6 <b>Connection guide</b>\n{rule}\n"
        "1\ufe0f\u20e3 Install an app from the Apps section.\n"
        "2\ufe0f\u20e3 Add the subscription link under <b>Subscription</b> and hit Update.\n"
        "3\ufe0f\u20e3 Run a Real Delay test and select the fastest config.\n"
        "4\ufe0f\u20e3 Stuck? Enable Fragment, then try the \U0001f7e1 port 80 configs.\n"
        "5\ufe0f\u20e3 Still nothing? Tap <b>Apply fresh clean IPs</b>; your link stays the same.\n"
        "{rule}\n"
        "\U0001f527 On mobile data port 80 often wins; on fixed lines port 443 usually does.\n"
        "\U0001f300 A config marked \U0001f300 rides a self-healing hostname and outlives the rest."
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
    # --------------------------------------------------------------- gating
    "join_required": (
        "\U0001f48e Please join the channel below to support the bot developers \u2764\ufe0f\u200d\U0001f525"
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
