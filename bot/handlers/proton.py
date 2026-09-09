"""ProtonVPN: pick location, pick OS, generate config."""

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InlineQuery,
    InputTextMessageContent,
    InlineQueryResultArticle,
)
from typing import Optional

from ..protonvpn import ProtonVPNEngine
from ..platforms import list_platforms, PLATFORM_IOS, PLATFORM_ANDROID, PLATFORM_WINDOWS
from ..warpconf import render_amneziawg_warp_config, bracket_ipv6_endpoint
from ..i18n import i18n
from ..locales.proton import PROTON_STRINGS
from ..keyboards import glass_button, keyboard_platform_picker


class ProtonHandler:
    """Handles the three-screen ProtonVPN config generation flow."""

    def __init__(self, app: Client):
        self.app = app

    async def show_location_picker(self, message: Message):
        """Show the ProtonVPN location (country) picker."""
        lang = message.from_user.language_code or "en"
        text = PROTON_STRINGS.get(lang, {}).get(
            "select_location",
            "Select ProtonVPN Location:"
        )
        kb = InlineKeyboardMarkup(
            [
                [glass_button(f"US 🇺🇸", f"proton_loc_us")],
                [glass_button(f"UK 🇬🇧", f"proton_loc_uk")],
                [glass_button(f"CA 🇨🇦", f"proton_loc_ca")],
                [glass_button(f"DE 🇩🇪", f"proton_loc_de")],
                [glass_button(f"FR 🇫🇷", f"proton_loc_fr")],
                [glass_button(f"JP 🇯🇵", f"proton_loc_jp")],
                [glass_button(f"SG 🇸🇬", f"proton_loc_sg")],
                [glass_button(f"NL 🇳🇱", f"proton_loc_nl")],
            ]
        )
        await message.reply(text, reply_markup=kb)

    async def show_os_picker(self, message: Message, location: str):
        """Show the OS (platform) picker after location is selected."""
        lang = message.from_user.language_code or "en"
        text = PROTON_STRINGS.get(lang, {}).get(
            "select_platform",
            "Select your device:"
        )
        kb = keyboard_platform_picker(f"proton_os_{location}")
        await message.reply(text, reply_markup=kb)

    async def generate_config(
        self,
        message: Message,
        location: str,
        platform: str,
    ):
        """Generate and deliver the ProtonVPN config."""
        lang = message.from_user.language_code or "en"
        status_text = PROTON_STRINGS.get(lang, {}).get(
            "generating",
            "Generating ProtonVPN config..."
        )
        await message.reply(status_text)

        try:
            # Create Proton session
            async with aiohttp.ClientSession() as session:
                engine = ProtonVPNEngine(session)
                session_data = await engine.create_session()
                servers = await engine.fetch_servers()
                
                # Pick a server for the location
                chosen_server = self._pick_server(servers, location)
                if not chosen_server:
                    raise ValueError(f"No servers for {location}")
                
                # Generate keys
                seed = os.urandom(32)
                priv_key, pub_key = ProtonVPNEngine.derive_x25519_from_seed(seed)
                
                # Register the key
                await engine.register_certificate(pub_key)
                
                # Render config
                config = self._render_for_platform(
                    priv_key=priv_key,
                    pub_key=chosen_server["PublicKey"],
                    endpoint=chosen_server["Endpoint"],
                    platform=platform,
                )
                
                # Send config
                await message.reply_document(
                    document=io.BytesIO(config.encode()),
                    file_name=f"proton_{location}_{platform}.conf",
                )
        except Exception as e:
            error_text = PROTON_STRINGS.get(lang, {}).get(
                "error",
                f"Error: {e}"
            )
            await message.reply(error_text)

    def _pick_server(self, servers: list, location: str) -> Optional[dict]:
        """Pick a server for the given location."""
        for server in servers:
            if server.get("Country", "").upper() == location.upper():
                return server
        return servers[0] if servers else None

    def _render_for_platform(
        self,
        priv_key: str,
        pub_key: str,
        endpoint: str,
        platform: str,
    ) -> str:
        """Render config for the target platform."""
        prof = get_platform(platform)
        if not prof:
            platform = "android"
            prof = get_platform(platform)
        
        # Use warpconf to render
        return render_amneziawg_warp_config(
            interface_privkey=priv_key,
            interface_addr4="10.2.0.2/32",
            interface_addr6="2a07:b944::2:2/128",
            peer_pubkey=pub_key,
            peer_endpoint=endpoint,
            platform=platform,
            use_custom_dns=True,
            custom_dns=prof.dns_servers,
            mtu=prof.mtu,
        )
