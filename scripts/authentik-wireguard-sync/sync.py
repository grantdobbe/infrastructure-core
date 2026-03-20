#!/usr/bin/env python3
"""Sync Authentik vpn-users group to MikroTik WireGuard peers."""

import ipaddress
import logging

from common import (
    COMMENT_PREFIX,
    authentik_session,
    get_vpn_group_id,
    get_vpn_users,
    load_config,
    mikrotik_session,
    set_user_attribute,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


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


def update_mikrotik_peer(session, cfg, peer_id, **fields):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers/{peer_id}"
    resp = session.patch(url, json=fields)
    resp.raise_for_status()
    log.info("Updated peer %s", peer_id)


def delete_mikrotik_peer(session, cfg, peer_id, comment):
    url = f"{cfg['MIKROTIK_URL']}/rest/interface/wireguard/peers/{peer_id}"
    resp = session.delete(url)
    resp.raise_for_status()
    log.info("Deleted peer %s (%s)", peer_id, comment)


def allocate_ip(subnet, used_ips):
    gateway = next(subnet.hosts())
    for host in subnet.hosts():
        if host == gateway:
            continue
        if host not in used_ips:
            return host
    log.error("No free IPs in %s", subnet)
    raise RuntimeError(f"No free IPs in {subnet}")


def sync(cfg):
    ak = authentik_session(cfg)
    mk = mikrotik_session(cfg)

    group_pk = get_vpn_group_id(ak, cfg)
    users = get_vpn_users(ak, cfg, group_pk)
    peers = get_mikrotik_peers(mk, cfg)

    # Index managed peers by comment
    managed_peers = {}
    for peer in peers:
        comment = peer.get("comment", "")
        if comment.startswith(COMMENT_PREFIX):
            managed_peers[comment] = peer

    # Index ALL peers by public key for duplicate detection
    peers_by_key = {}
    for peer in peers:
        key = peer.get("public-key", "")
        if key:
            peers_by_key[key] = peer

    # Collect all used IPs
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

    # Adopt existing peers whose public key matches but comment differs
    for comment, d in desired.items():
        if comment in managed_peers:
            continue
        existing = peers_by_key.get(d["public_key"])
        if existing and existing.get("comment", "") != comment:
            old_comment = existing.get("comment", "(none)")
            fields = {"comment": comment}
            if existing.get("allowed-address") != d["allowed_address"]:
                fields["allowed-address"] = d["allowed_address"]
            update_mikrotik_peer(mk, cfg, existing[".id"], **fields)
            log.info("Adopted peer %s -> %s", old_comment, comment)
            managed_peers[comment] = existing

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
            update_mikrotik_peer(
                mk, cfg, peer[".id"],
                **{"public-key": d["public_key"], "allowed-address": d["allowed_address"]},
            )


def main():
    cfg = load_config()
    sync(cfg)


if __name__ == "__main__":
    main()
