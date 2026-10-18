"""Garde d'authentification admin + protection SSRF pour les routes de scraping."""

import ipaddress
import socket

from flask import jsonify, request

from app import config


def check_admin():
    """None si OK, sinon un tuple Flask (response, status) à retourner."""
    if config.SCRAPE_PUBLIC:
        return None
    if not config.ADMIN_TOKEN:
        return jsonify({"error": "ADMIN_TOKEN is not configured on the server"}), 500
    if request.headers.get("Authorization", "") != f"Bearer {config.ADMIN_TOKEN}":
        return jsonify({"error": "Unauthorized"}), 401
    return None


def is_private_host(host):
    """True si privé/loopback, None si DNS inconnu, False sinon."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False
