#!/usr/bin/env python3
"""Generate a WireGuard client config for a user."""

import logging
import sys
from pathlib import Path

from common import (
    authentik_session,
    get_user_by_username,
    load_config,
    mikrotik_session,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def get_wg_server_pubkey(session, cfg):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard"
    resp = session.get(url)
    resp.raise_for_status()
    for iface in resp.json():
        if iface.get("name") == cfg["WG_INTERFACE"]:
            return iface["public-key"]
    log.error("WireGuard interface '%s' not found on MikroTik", cfg["WG_INTERFACE"])
    sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <username>", file=sys.stderr)
        sys.exit(1)

    username = sys.argv[1]
    cfg = load_config(extra_required=["VPN_ENDPOINT", "VPN_PORT", "VPN_DNS"])

    key_file = Path(__file__).resolve().parent / "keys" / f"{username}.key"
    if not key_file.exists():
        log.error("Private key not found: %s (run genkey.py first)", key_file)
        sys.exit(1)
    private_key = key_file.read_text().strip()

    ak = authentik_session(cfg)
    user = get_user_by_username(ak, cfg, username)
    attrs = user.get("attributes", {})
    allowed_ips = attrs.get("wireguardAllowedIPs")
    if not allowed_ips:
        log.error("User '%s' has no wireguardAllowedIPs attribute (run sync.py first)", username)
        sys.exit(1)

    mk = mikrotik_session(cfg)
    server_pubkey = get_wg_server_pubkey(mk, cfg)

    print(f"""\
[Interface]
PrivateKey = {private_key}
Address = {allowed_ips}
DNS = {cfg['VPN_DNS']}

[Peer]
PublicKey = {server_pubkey}
Endpoint = {cfg['VPN_ENDPOINT']}:{cfg['VPN_PORT']}
AllowedIPs = {cfg['VPN_SUBNET']}""")


if __name__ == "__main__":
    main()
