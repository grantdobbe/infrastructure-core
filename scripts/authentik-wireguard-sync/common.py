"""Shared helpers for authentik-wireguard-sync scripts."""

import ipaddress
import logging
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

COMMENT_PREFIX = "authentik:"


def load_config(extra_required=None):
    load_dotenv(Path(__file__).resolve().parent / ".env")
    required = [
        "AUTHENTIK_URL",
        "AUTHENTIK_TOKEN",
        "MIKROTIK_URL",
        "MIKROTIK_USER",
        "MIKROTIK_PASSWORD",
        "VPN_SUBNET",
    ]
    if extra_required:
        required.extend(extra_required)
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
        params = {}
    return users


def get_user_by_username(session, cfg, username):
    url = f"{cfg['AUTHENTIK_URL']}/api/v3/core/users/"
    resp = session.get(url, params={"username": username})
    resp.raise_for_status()
    results = resp.json()["results"]
    if not results:
        log.error("User '%s' not found in Authentik", username)
        sys.exit(1)
    return results[0]


def set_user_attribute(session, cfg, user_pk, attributes):
    url = f"{cfg['AUTHENTIK_URL']}/api/v3/core/users/{user_pk}/"
    resp = session.patch(url, json={"attributes": attributes})
    resp.raise_for_status()
