# proxy.py
from urllib.parse import urlparse, parse_qs
from telegram.utils.request import Request

# اگر خواستی این لینک رو از env بگیری:
TG_LINK = "tg://proxy?server=allinone.transiiantanialnmiomana.info&port=666&secret=dde9a4f23b1d768c04a8d7f39120ca5b6e"

def parse_tg_proxy_link(tg_link: str):
    """
    tg_link expected like: tg://proxy?server=...&port=...&secret=...
    returns (server, port, secret_or_none)
    """
    u = urlparse(tg_link)
    qs = parse_qs(u.query)
    server = qs.get("server", [None])[0]
    port = qs.get("port", [None])[0]
    secret = qs.get("secret", [None])[0]
    return server, port, secret

def get_request():
    """
    Returns a telegram.utils.request.Request configured to use socks5 proxy.
    NOTE: This assumes the proxy host:port supports SOCKS5. If it's MTProto-only,
    python-telegram-bot via Bot API can NOT use it.
    """
    server, port, secret = parse_tg_proxy_link(TG_LINK)
    if not server or not port:
        # fallback: return default Request (no proxy)
        return Request()
    # try socks5 scheme (the most common for bot usage). If your proxy is HTTP(S), change to http://
    proxy_url = f"socks5://{server}:{port}"
    return Request(proxy_url=proxy_url)

