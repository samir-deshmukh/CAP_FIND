"""Client address extraction that only honors forwarded headers from configured proxies."""
from __future__ import annotations

import ipaddress
import os

from fastapi import Request


def client_ip(request: Request) -> str:
    """Return a client IP without trusting attacker-controlled forwarding headers.

    Set CET_TRUSTED_PROXY_IPS to comma-separated proxy IPs/CIDRs only when the
    reverse proxy is known to append the actual client address to X-Forwarded-For.
    """
    peer = request.client.host if request.client else ""
    if not peer:
        return "unknown"
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"

    trusted = []
    for item in os.getenv("CET_TRUSTED_PROXY_IPS", "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            trusted.append(
                ipaddress.ip_network(item, strict=False)
                if "/" in item
                else ipaddress.ip_network(f"{item}/{peer_ip.max_prefixlen}", strict=False)
            )
        except ValueError:
            continue

    if not any(peer_ip in network for network in trusted):
        return str(peer_ip)

    forwarded = request.headers.get("x-forwarded-for", "")
    # A trusted proxy must append the observed client address. Never use the
    # leftmost value, which may have been supplied by the untrusted client.
    for candidate in reversed(forwarded.split(",")):
        try:
            return str(ipaddress.ip_address(candidate.strip()))
        except ValueError:
            continue
    return str(peer_ip)
