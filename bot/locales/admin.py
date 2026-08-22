"""Admin panel copy, kept apart from the user-facing catalogues."""

ADMIN: dict[str, dict[str, str]] = {
    "fa": {
        "admin.menu": (
            "\U0001f6e0 <b>\u067e\u0646\u0644 \u0645\u062f\u06cc\u0631\u06cc\u062a</b>\n{rule}\n"
            "\U0001f465 \u06a9\u0627\u0631\u0628\u0631\u0627\u0646: <b>{users}</b> (\u0627\u0645\u0631\u0648\u0632 +{users_today})\n"
            "\U0001f5c2 \u067e\u0646\u0644\u200c\u0647\u0627: <b>{panels}</b> (\u0627\u0645\u0631\u0648\u0632 +{panels_today})\n"
            "\U0001f4e1 \u0627\u0633\u062a\u062e\u0631 \u0622\u06cc\u200c\u067e\u06cc: <b>{pool}</b>\n"
            "\U0001f512 \u06a9\u0627\u0646\u0627\u0644 \u0627\u062c\u0628\u0627\u0631\u06cc: <b>{channels}</b>\n"
            "\U0001f527 \u0633\u0631\u0648\u06cc\u0633: <b>{maintenance}</b> \u00b7 \u0633\u0627\u062e\u062a: <b>{builds}</b>"
        ),
        "admin.stats": (
            "\U0001f4c8 <b>\u0622\u0645\u0627\u0631 \u06a9\u0627\u0645\u0644</b>\n{rule}\n"
            "\U0001f465 \u06a9\u0644 \u06a9\u0627\u0631\u0628\u0631\u0627\u0646: <b>{users}</b>\n"
            "\U0001f195 \u062c\u062f\u06cc\u062f \u0627\u0645\u0631\u0648\u0632: <b>{users_today}</b>\n"
            "\u26a1 \u0641\u0639\u0627\u0644 \u06f7 \u0631\u0648\u0632: <b>{active_week}</b>\n"
            "\u26d4\ufe0f \u0645\u0633\u062f\u0648\u062f: <b>{banned}</b>\n"
            "\U0001f5c2 \u067e\u0646\u0644 \u0641\u0639\u0627\u0644: <b>{panels}</b> \u00b7 \u0633\u0627\u0644\u0645: <b>{healthy}</b>\n"
            "\U0001f504 \u0628\u0627\u0632\u0633\u0627\u0632\u06cc: <b>{rebuilds}</b> \u00b7 \U0001f916 \u0627\u0639\u0645\u0627\u0644 \u062e\u0648\u062f\u06a9\u0627\u0631: <b>{syncs}</b>\n"
            "\u23f1 \u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 \u0632\u0645\u0627\u0646 \u0633\u0627\u062e\u062a: <b>{avg_build}</b> \u062b\u0627\u0646\u06cc\u0647\n"
            "\U0001f4e1 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0627\u06cc\u06cc\u062f\u0634\u062f\u0647: <b>{verified}</b> \u0627\u0632 <b>{pool}</b>"
        ),
        "admin.users_prompt": "\U0001f50d \u0622\u06cc\u062f\u06cc \u0639\u062f\u062f\u06cc\u060c \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u06cc\u0627 \u0628\u062e\u0634\u06cc \u0627\u0632 \u0646\u0627\u0645 \u06a9\u0627\u0631\u0628\u0631 \u0631\u0627 \u0628\u0641\u0631\u0633\u062a.",
        "admin.user_card": (
            "\U0001f464 <b>{name}</b>\n{rule}\n"
            "\U0001f194 <code>{tg_id}</code>\n"
            "\U0001f517 \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645: {username}\n"
            "\U0001f310 \u0632\u0628\u0627\u0646: {lang} \u00b7 \u0627\u067e\u0631\u0627\u062a\u0648\u0631: {operator}\n"
            "\U0001f5c2 \u067e\u0646\u0644: {panel}\n"
            "\U0001f4e6 \u062a\u0639\u062f\u0627\u062f \u0633\u0627\u062e\u062a: <b>{builds}</b>\n"
            "\u26d4\ufe0f \u0645\u0633\u062f\u0648\u062f: <b>{banned}</b>\n"
            "\U0001f552 \u0622\u062e\u0631\u06cc\u0646 \u0641\u0639\u0627\u0644\u06cc\u062a: {seen}"
        ),
        "admin.user_none": "\u0645\u0648\u0631\u062f\u06cc \u067e\u06cc\u062f\u0627 \u0646\u0634\u062f.",
        "admin.broadcast_prompt": (
            "\U0001f4e3 \u0645\u062a\u0646 \u067e\u06cc\u0627\u0645 \u0647\u0645\u06af\u0627\u0646\u06cc \u0631\u0627 \u0628\u0641\u0631\u0633\u062a. \u062a\u06af\u200c\u0647\u0627\u06cc HTML \u0645\u062c\u0627\u0632 \u0627\u0633\u062a.\n"
            "\u06af\u06cc\u0631\u0646\u062f\u0647: <b>{count}</b> \u06a9\u0627\u0631\u0628\u0631."
        ),
        "admin.broadcast_done": "\u2705 \u0627\u0631\u0633\u0627\u0644 \u062a\u0645\u0627\u0645 \u0634\u062f.\n\u2713 \u0645\u0648\u0641\u0642: <b>{sent}</b>\n\u2717 \u0646\u0627\u0645\u0648\u0641\u0642: <b>{failed}</b>",
        "admin.channels": (
            "\U0001f512 <b>\u0642\u0641\u0644 \u06a9\u0627\u0646\u0627\u0644</b>\n{rule}\n"
            "\u0648\u0636\u0639\u06cc\u062a: <b>{state}</b>\n\n{list}\n\n"
            "\u2139\ufe0f \u0631\u0628\u0627\u062a \u0628\u0627\u06cc\u062f \u062f\u0631 \u0647\u0631 \u06a9\u0627\u0646\u0627\u0644 \u0627\u062f\u0645\u06cc\u0646 \u0628\u0627\u0634\u062f."
        ),
        "admin.channel_prompt": (
            "\U0001f4ce \u06cc\u0648\u0632\u0631\u0646\u06cc\u0645 \u06a9\u0627\u0646\u0627\u0644 (\u0645\u0627\u0646\u0646\u062f <code>@mychannel</code>) \u06cc\u0627 \u0622\u06cc\u062f\u06cc \u0639\u062f\u062f\u06cc \u0631\u0627 \u0628\u0641\u0631\u0633\u062a.\n"
            "\u0627\u0648\u0644 \u0631\u0628\u0627\u062a \u0631\u0627 \u062f\u0631 \u06a9\u0627\u0646\u0627\u0644 \u0627\u062f\u0645\u06cc\u0646 \u06a9\u0646."
        ),
        "admin.channel_added": "\u2705 \u06a9\u0627\u0646\u0627\u0644 <b>{title}</b> \u0627\u0636\u0627\u0641\u0647 \u0634\u062f.",
        "admin.channel_bad": "\u274c \u0646\u062a\u0648\u0627\u0646\u0633\u062a\u0645 \u0628\u0647 \u0627\u06cc\u0646 \u06a9\u0627\u0646\u0627\u0644 \u062f\u0633\u062a\u0631\u0633\u06cc \u067e\u06cc\u062f\u0627 \u06a9\u0646\u0645: <code>{reason}</code>",
        "admin.channel_removed": "\U0001f5d1 \u06a9\u0627\u0646\u0627\u0644 \u062d\u0630\u0641 \u0634\u062f.",
        "admin.channels_empty": "\u0647\u06cc\u0686 \u06a9\u0627\u0646\u0627\u0644\u06cc \u062b\u0628\u062a \u0646\u0634\u062f\u0647.",
        "admin.engine": (
            "\u2699\ufe0f <b>\u0645\u0648\u062a\u0648\u0631 \u0627\u0633\u06a9\u0646</b>\n{rule}\n"
            "\U0001f4e1 \u0627\u0633\u062a\u062e\u0631: <b>{total}</b> \u00b7 \u062a\u0627\u06cc\u06cc\u062f\u0634\u062f\u0647: <b>{verified}</b>\n"
            "\U0001f300 \u062f\u0627\u0645\u0646\u0647\u0654 \u062e\u0648\u062f\u062a\u0631\u0645\u06cc\u0645: <b>{domains}</b>\n"
            "\U0001f3c6 \u0628\u0647\u062a\u0631\u06cc\u0646 \u067e\u06cc\u0646\u06af: <b>{best}</b>\n"
            "\U0001f50c \u067e\u0648\u0631\u062a\u200c\u0647\u0627: <b>{ports}</b>\n"
            "\u23f3 \u0622\u062e\u0631\u06cc\u0646 \u0627\u0633\u06a9\u0646: <b>{updated}</b>\n"
            "\u2699\ufe0f \u062f\u0631 \u062d\u0627\u0644 \u0627\u062c\u0631\u0627: <b>{state}</b>\n"
            "\U0001f501 \u0641\u0627\u0635\u0644\u0647 \u0627\u0633\u06a9\u0646: <b>{interval}</b> \u062b\u0627\u0646\u06cc\u0647\n"
            "\U0001f4e6 \u062f\u0633\u062a\u0647 \u0647\u0631 \u0627\u0633\u06a9\u0646: <b>{batch}</b> \u00b7 \u0647\u0645\u0632\u0645\u0627\u0646\u06cc: <b>{concurrency}</b>\n"
            "{rule}\n"
            "\U0001f916 <b>\u0627\u0639\u0645\u0627\u0644 \u062e\u0648\u062f\u06a9\u0627\u0631 \u0631\u0648\u06cc \u067e\u0646\u0644\u200c\u0647\u0627</b>\n"
            "\u0648\u0636\u0639\u06cc\u062a: <b>{pilot}</b> \u00b7 \u0647\u0631 <b>{pilot_interval}</b> \u062b\u0627\u0646\u06cc\u0647\n"
            "\u062f\u0631 \u0646\u0648\u0628\u062a: <b>{due}</b> \u067e\u0646\u0644 \u00b7 \u0622\u062e\u0631\u06cc\u0646 \u062f\u0648\u0631: <b>{last_synced}</b> \u0645\u0648\u0641\u0642"
        ),
        "admin.sync_started": "\U0001f916 \u0627\u0639\u0645\u0627\u0644 \u062e\u0648\u062f\u06a9\u0627\u0631 \u0634\u0631\u0648\u0639 \u0634\u062f\u060c \u06a9\u0645\u06cc \u0637\u0648\u0644 \u0645\u06cc\u200c\u06a9\u0634\u062f...",
        "admin.sync_done": "\u2705 \u0631\u0648\u06cc <b>{count}</b> \u067e\u0646\u0644 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0627\u0632\u0647 \u0627\u0639\u0645\u0627\u0644 \u0634\u062f.",
        "admin.options": (
            "\U0001f39a <b>\u062a\u0646\u0637\u06cc\u0645\u0627\u062a</b>\n{rule}\n"
            "\u0631\u0648\u06cc \u0647\u0631 \u06af\u0632\u06cc\u0646\u0647 \u0628\u0632\u0646 \u062a\u0627 \u0648\u0636\u0639\u06cc\u062a\u0634 \u0639\u0648\u0636 \u0634\u0648\u062f."
        ),
        "admin.panels": "\U0001f5c2 <b>\u067e\u0646\u0644\u200c\u0647\u0627\u06cc \u0627\u062e\u06cc\u0631</b>\n{rule}\n{list}",
        "admin.logs": "\U0001f9fe <b>\u0631\u0648\u06cc\u062f\u0627\u062f\u0647\u0627\u06cc \u0627\u062e\u06cc\u0631</b>\n{rule}\n{list}",
        "admin.saved": "\u2705 \u0630\u062e\u06cc\u0631\u0647 \u0634\u062f.",
        "admin.denied": "\u26d4\ufe0f \u0627\u06cc\u0646 \u0628\u062e\u0634 \u0645\u062e\u0635\u0648\u0635 \u0645\u062f\u06cc\u0631\u0627\u0646 \u0627\u0633\u062a.",
        "admin.backup_caption": "\U0001f4be \u067e\u0634\u062a\u06cc\u0628\u0627\u0646 \u062f\u06cc\u062a\u0627\u0628\u06cc\u0633 \u00b7 {when}",
        "admin.ban_done": "\u26d4\ufe0f \u06a9\u0627\u0631\u0628\u0631 \u0645\u0633\u062f\u0648\u062f \u0634\u062f.",
        "admin.unban_done": "\u2705 \u0645\u0633\u062f\u0648\u062f\u06cc\u062a \u0628\u0631\u062f\u0627\u0634\u062a\u0647 \u0634\u062f.",
        "admin.on": "\u0631\u0648\u0634\u0646",
        "admin.off": "\u062e\u0627\u0645\u0648\u0634",
        "btn.ban": "\u26d4\ufe0f \u0645\u0633\u062f\u0648\u062f \u06a9\u0631\u062f\u0646",
        "btn.unban": "\u2705 \u0631\u0641\u0639 \u0645\u0633\u062f\u0648\u062f\u06cc\u062a",
        "opt.maintenance": "\u062d\u0627\u0644\u062a \u0633\u0631\u0648\u06cc\u0633",
        "opt.builds_enabled": "\u0627\u062c\u0627\u0632\u0647 \u0633\u0627\u062e\u062a \u067e\u0646\u0644",
        "opt.force_join": "\u0639\u0636\u0648\u06cc\u062a \u0627\u062c\u0628\u0627\u0631\u06cc",
        "opt.warp_enabled": "\u0628\u062e\u0634 \u0648\u0627\u0631\u067e",
        "opt.support_enabled": "\u067e\u0634\u062a\u06cc\u0628\u0627\u0646\u06cc \u062f\u0631\u0648\u0646 \u0631\u0628\u0627\u062a",
        "opt.autopilot": "\u0627\u0639\u0645\u0627\u0644 \u062e\u0648\u062f\u06a9\u0627\u0631 \u0622\u06cc\u200c\u067e\u06cc \u062a\u0645\u06cc\u0632",
    },
    "en": {
        "admin.menu": (
            "\U0001f6e0 <b>Admin panel</b>\n{rule}\n"
            "\U0001f465 Users: <b>{users}</b> (today +{users_today})\n"
            "\U0001f5c2 Panels: <b>{panels}</b> (today +{panels_today})\n"
            "\U0001f4e1 IP pool: <b>{pool}</b>\n"
            "\U0001f512 Locked channels: <b>{channels}</b>\n"
            "\U0001f527 Maintenance: <b>{maintenance}</b> \u00b7 Builds: <b>{builds}</b>"
        ),
        "admin.stats": (
            "\U0001f4c8 <b>Full stats</b>\n{rule}\n"
            "\U0001f465 Total users: <b>{users}</b>\n"
            "\U0001f195 New today: <b>{users_today}</b>\n"
            "\u26a1 Active 7d: <b>{active_week}</b>\n"
            "\u26d4\ufe0f Banned: <b>{banned}</b>\n"
            "\U0001f5c2 Live panels: <b>{panels}</b> \u00b7 healthy: <b>{healthy}</b>\n"
            "\U0001f504 Rebuilds: <b>{rebuilds}</b> \u00b7 \U0001f916 auto applies: <b>{syncs}</b>\n"
            "\u23f1 Average build: <b>{avg_build}</b> s\n"
            "\U0001f4e1 Verified IPs: <b>{verified}</b> of <b>{pool}</b>"
        ),
        "admin.users_prompt": "\U0001f50d Send a numeric id, a username, or part of a name.",
        "admin.user_card": (
            "\U0001f464 <b>{name}</b>\n{rule}\n"
            "\U0001f194 <code>{tg_id}</code>\n"
            "\U0001f517 Username: {username}\n"
            "\U0001f310 Language: {lang} \u00b7 Operator: {operator}\n"
            "\U0001f5c2 Panel: {panel}\n"
            "\U0001f4e6 Builds: <b>{builds}</b>\n"
            "\u26d4\ufe0f Banned: <b>{banned}</b>\n"
            "\U0001f552 Last seen: {seen}"
        ),
        "admin.user_none": "No match found.",
        "admin.broadcast_prompt": (
            "\U0001f4e3 Send the broadcast text. HTML tags are allowed.\n"
            "Recipients: <b>{count}</b> users."
        ),
        "admin.broadcast_done": "\u2705 Broadcast finished.\n\u2713 Sent: <b>{sent}</b>\n\u2717 Failed: <b>{failed}</b>",
        "admin.channels": (
            "\U0001f512 <b>Channel lock</b>\n{rule}\n"
            "State: <b>{state}</b>\n\n{list}\n\n"
            "\u2139\ufe0f The bot must be an admin in every channel."
        ),
        "admin.channel_prompt": (
            "\U0001f4ce Send the channel username (like <code>@mychannel</code>) or its numeric id.\n"
            "Add the bot as an admin there first."
        ),
        "admin.channel_added": "\u2705 Channel <b>{title}</b> added.",
        "admin.channel_bad": "\u274c I could not reach that channel: <code>{reason}</code>",
        "admin.channel_removed": "\U0001f5d1 Channel removed.",
        "admin.channels_empty": "No channels registered.",
        "admin.engine": (
            "\u2699\ufe0f <b>Scan engine</b>\n{rule}\n"
            "\U0001f4e1 Pool: <b>{total}</b> \u00b7 verified: <b>{verified}</b>\n"
            "\U0001f300 Self-healing hostnames: <b>{domains}</b>\n"
            "\U0001f3c6 Best ping: <b>{best}</b>\n"
            "\U0001f50c Ports: <b>{ports}</b>\n"
            "\u23f3 Last scan: <b>{updated}</b>\n"
            "\u2699\ufe0f Running: <b>{state}</b>\n"
            "\U0001f501 Interval: <b>{interval}</b> s\n"
            "\U0001f4e6 Batch: <b>{batch}</b> \u00b7 concurrency: <b>{concurrency}</b>\n"
            "{rule}\n"
            "\U0001f916 <b>Autopilot</b>\n"
            "State: <b>{pilot}</b> \u00b7 every <b>{pilot_interval}</b> s\n"
            "Queued: <b>{due}</b> panels \u00b7 last cycle: <b>{last_synced}</b> applied"
        ),
        "admin.sync_started": "\U0001f916 Autopilot cycle started, this takes a moment...",
        "admin.sync_done": "\u2705 Fresh clean IPs applied to <b>{count}</b> panels.",
        "admin.options": "\U0001f39a <b>Options</b>\n{rule}\nTap an option to flip it.",
        "admin.panels": "\U0001f5c2 <b>Recent panels</b>\n{rule}\n{list}",
        "admin.logs": "\U0001f9fe <b>Recent events</b>\n{rule}\n{list}",
        "admin.saved": "\u2705 Saved.",
        "admin.denied": "\u26d4\ufe0f Admins only.",
        "admin.backup_caption": "\U0001f4be Database backup \u00b7 {when}",
        "admin.ban_done": "\u26d4\ufe0f User banned.",
        "admin.unban_done": "\u2705 Ban lifted.",
        "admin.on": "on",
        "admin.off": "off",
        "btn.ban": "\u26d4\ufe0f Ban",
        "btn.unban": "\u2705 Unban",
        "opt.maintenance": "Maintenance mode",
        "opt.builds_enabled": "Panel building",
        "opt.force_join": "Forced membership",
        "opt.warp_enabled": "WARP section",
        "opt.support_enabled": "In-bot support",
        "opt.autopilot": "Automatic clean IP apply",
    },
}
