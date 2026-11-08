"""AutoVless: a Telegram bot that builds VLESS panels on the user's own Cloudflare account."""

__version__ = "1.1.1"

# StreamReader.read() may return the HTTP 101 headers and the first WebSocket
# frame in one packet. Keep that frame for the VLESS protocol reader instead
# of silently dropping it after the upgrade check.
from . import pingtest as _pingtest
from .pingtest_buffer import install as _install_pingtest_buffer

_install_pingtest_buffer(_pingtest)
