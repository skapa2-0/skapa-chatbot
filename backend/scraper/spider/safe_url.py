"""Protection SSRF : vérifie qu'une URL ne pointe pas vers une adresse interne."""

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_url(url: str) -> bool:
    """True uniquement si l'URL utilise http/https et pointe vers une IP publique.

    Résout le DNS et refuse si UNE des IP résolues est privée, loopback,
    link-local (169.254.0.0/16 — métadonnées cloud), réservée, multicast
    ou non-spécifiée, en IPv4 ET IPv6.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    host = parsed.hostname
    if not host:
        return False

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False

    if not infos:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False

    return True
