#!/usr/bin/env python3
"""Sync Authentik vpn-users group to MikroTik WireGuard peers."""

import ipaddress
import logging
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

COMMENT_PREFIX = "authentik:"


def load_config():
    load_dotenv(Path(__file__).resolve().parent / ".env")
    required = [
        "AUTHENTIK_URL",
        "AUTHENTIK_TOKEN",
        "MIKROTIK_URL",
        "MIKROTIK_USER",
        "MIKROTIK_PASSWORD",
        "VPN_SUBNET",
    ]
    cfg = {}
    missing = []
    for key in required:
        val = os.environ.get(key)
        if not val:
            missing.append(key)
        cfg[key] = val
    if missing:
        log.error("Missing required env vars: %s", ", ".join(missing))
        sys.exit(1)
    cfg["WG_INTERFACE"] = os.environ.get("WG_INTERFACE", "wireguard1")
    cfg["VPN_GROUP"] = os.environ.get("VPN_GROUP", "vpn-users")
    cfg["VPN_SUBNET"] = ipaddress.ip_network(cfg["VPN_SUBNET"], strict=False)
    return cfg


def authentik_session(cfg):
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {cfg['AUTHENTIK_TOKEN']}"
    s.headers["Accept"] = "application/json"
    return s


def mikrotik_session(cfg):
    s = requests.Session()
    s.auth = (cfg["MIKROTIK_USER"], cfg["MIKROTIK_PASSWORD"])
    s.headers["Accept"] = "application/json"
    s.verify = False
    return s


def get_vpn_group_id(session, cfg):
    url = f"{cfg['AUTHENTIK_URL']}/api/v3/core/groups/"
    resp = session.get(url, params={"name": cfg["VPN_GROUP"]})
    resp.raise_for_status()
    results = resp.json()["results"]
    if not results:
        log.error("Group '%s' not found in Authentik", cfg["VPN_GROUP"])
        sys.exit(1)
    return results[0]["pk"]


def get_vpn_users(session, cfg, group_pk):
    users = []
    url = f"{cfg['AUTHENTIK_URL']}/api/v3/core/users/"
    params = {"groups": group_pk, "page_size": 100}
    while url:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        users.extend(data["results"])
        url = data["pagination"].get("next")
        params = {}  # next URL includes params
    return users


def set_user_attribute(session, cfg, user_pk, attributes):
    url = f"{cfg['AUTHENTIK_URL']}/api/v3/core/users/{user_pk}/"
    resp = session.patch(url, json={"attributes": attributes})
    resp.raise_for_status()


def get_mikrotik_peers(session, cfg):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers"
    resp = session.get(url)
    resp.raise_for_status()
    return [p for p in resp.json() if p.get("interface") == cfg["WG_INTERFACE"]]


def add_mikrotik_peer(session, cfg, public_key, allowed_address, comment):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers"
    resp = session.put(url, json={
        "interface": cfg["WG_INTERFACE"],
        "public-key": public_key,
        "allowed-address": allowed_address,
        "comment": comment,
    })
    resp.raise_for_status()
    log.info("Added peer %s (%s)", comment, allowed_address)


def update_mikrotik_peer(session, cfg, peer_id, public_key, allowed_address):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers/{peer_id}"
    resp = session.patch(url, json={
        "public-key": public_key,
        "allowed-address": allowed_address,
    })
    resp.raise_for_status()
    log.info("Updated peer %s", peer_id)


def delete_mikrotik_peer(session, cfg, peer_id, comment):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers/{peer_id}"
    resp = session.delete(url)
    resp.raise_for_status()
    log.info("Deleted peer %s (%s)", peer_id, comment)


def allocate_ip(subnet, used_ips):
    gateway = next(subnet.hosts())  # .1 reserved for gateway
    for host in subnet.hosts():
        if host == gateway:
            continue
        if host not in used_ips:
            return host
    log.error("No free IPs in %s", subnet)
    sys.exit(1)


def sync(cfg):
    ak = authentik_session(cfg)
    mk = mikrotik_session(cfg)

    group_pk = get_vpn_group_id(ak, cfg)
    users = get_vpn_users(ak, cfg, group_pk)
    peers = get_mikrotik_peers(mk, cfg)

    # Index current managed peers by comment
    managed_peers = {}
    for peer in peers:
        comment = peer.get("comment", "")
        if comment.startswith(COMMENT_PREFIX):
            managed_peers[comment] = peer

    # Collect all used IPs (from MikroTik peers + Authentik attributes)
    used_ips = set()
    for peer in peers:
        for addr in peer.get("allowed-address", "").split(","):
            addr = addr.strip()
            if addr:
                try:
                    used_ips.add(ipaddress.ip_address(addr.split("/")[0]))
                except ValueError:
                    pass

    # Build desired state
    desired = {}
    for user in users:
        if not user.get("is_active", True):
            continue
        attrs = user.get("attributes", {})
        pubkey = attrs.get("wireguardPublicKey")
        if not pubkey:
            log.debug("Skipping %s: no wireguardPublicKey", user["username"])
            continue

        allowed_ip = attrs.get("wireguardAllowedIPs")
        if allowed_ip:
            try:
                used_ips.add(ipaddress.ip_address(allowed_ip.split("/")[0]))
            except ValueError:
                pass

        if not allowed_ip:
            ip = allocate_ip(cfg["VPN_SUBNET"], used_ips)
            allowed_ip = f"{ip}/32"
            used_ips.add(ip)
            attrs["wireguardAllowedIPs"] = allowed_ip
            set_user_attribute(ak, cfg, user["pk"], attrs)
            log.info("Assigned %s to %s", allowed_ip, user["username"])

        comment = f"{COMMENT_PREFIX}{user['username']}"
        desired[comment] = {
            "public_key": pubkey,
            "allowed_address": allowed_ip,
        }

    # Diff and apply
    desired_comments = set(desired.keys())
    current_comments = set(managed_peers.keys())

    # Add new peers
    for comment in desired_comments - current_comments:
        d = desired[comment]
        add_mikrotik_peer(mk, cfg, d["public_key"], d["allowed_address"], comment)

    # Remove stale peers
    for comment in current_comments - desired_comments:
        peer = managed_peers[comment]
        delete_mikrotik_peer(mk, cfg, peer[".id"], comment)

    # Update changed peers
    for comment in desired_comments & current_comments:
        d = desired[comment]
        peer = managed_peers[comment]
        if (peer.get("public-key") != d["public_key"]
                or peer.get("allowed-address") != d["allowed_address"]):
            update_mikrotik_peer(mk, cfg, peer[".id"], d["public_key"], d["allowed_address"])


def main():
    cfg = load_config()
    sync(cfg)


if __name__ == "__main__":
    main()
