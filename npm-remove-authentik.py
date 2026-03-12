#!/usr/bin/env python3
"""
Removes Authentik forward auth from all Nginx Proxy Manager proxy hosts.

Usage:
    NPM_EMAIL=admin@example.com NPM_PASSWORD=secret python3 npm-remove-authentik.py
    NPM_EMAIL=... NPM_PASSWORD=... python3 npm-remove-authentik.py --dry-run
"""

import argparse
import os
import re
import sys
import requests

NPM_URL = "http://10.10.10.10:81"

AUTHENTIK_PATTERN = re.compile(
    r"\n*location /outpost\.goauthentik\.io \{.*?\}\s*"
    r"auth_request /outpost\.goauthentik\.io/auth/nginx;\s*"
    r"error_page 401 = @goauthentik_proxy_signin;\s*"
    r"auth_request_set \$auth_cookie \$upstream_http_set_cookie;\s*"
    r"add_header Set-Cookie \$auth_cookie;\s*"
    r"auth_request_set \$authentik_username\s+\$upstream_http_x_authentik_username;\s*"
    r"auth_request_set \$authentik_groups\s+\$upstream_http_x_authentik_groups;\s*"
    r"auth_request_set \$authentik_email\s+\$upstream_http_x_authentik_email;\s*"
    r"auth_request_set \$authentik_name\s+\$upstream_http_x_authentik_name;\s*"
    r"auth_request_set \$authentik_uid\s+\$upstream_http_x_authentik_uid;\s*"
    r"proxy_set_header X-authentik-username\s+\$authentik_username;\s*"
    r"proxy_set_header X-authentik-groups\s+\$authentik_groups;\s*"
    r"proxy_set_header X-authentik-email\s+\$authentik_email;\s*"
    r"proxy_set_header X-authentik-name\s+\$authentik_name;\s*"
    r"proxy_set_header X-authentik-uid\s+\$authentik_uid;\s*"
    r"location @goauthentik_proxy_signin \{.*?\}",
    re.DOTALL,
)


def get_token(email, password):
    r = requests.post(f"{NPM_URL}/api/tokens", json={"identity": email, "secret": password})
    r.raise_for_status()
    return r.json()["token"]


def get_proxy_hosts(token):
    r = requests.get(f"{NPM_URL}/api/nginx/proxy-hosts",
                     headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def update_proxy_host(token, host_id, payload):
    r = requests.put(f"{NPM_URL}/api/nginx/proxy-hosts/{host_id}",
                     headers={"Authorization": f"Bearer {token}"},
                     json=payload)
    r.raise_for_status()
    return r.json()


def main():
    parser = argparse.ArgumentParser(description="Remove Authentik forward auth from NPM proxy hosts")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without making changes")
    args = parser.parse_args()

    email = os.environ.get("NPM_EMAIL")
    password = os.environ.get("NPM_PASSWORD")
    if not email or not password:
        print("Error: NPM_EMAIL and NPM_PASSWORD environment variables are required", file=sys.stderr)
        sys.exit(1)

    print(f"Authenticating to {NPM_URL}...")
    token = get_token(email, password)

    hosts = get_proxy_hosts(token)
    print(f"Found {len(hosts)} proxy hosts\n")

    for host in hosts:
        domains = host.get("domain_names", [])
        host_id = host["id"]
        current_config = host.get("advanced_config", "") or ""

        if "outpost.goauthentik.io" not in current_config:
            print(f"  SKIP (no authentik): {', '.join(domains)}")
            continue

        new_config = AUTHENTIK_PATTERN.sub("", current_config).strip()

        print(f"  {'[DRY RUN] ' if args.dry_run else ''}REMOVE: {', '.join(domains)}")

        if not args.dry_run:
            update_proxy_host(token, host_id, {"advanced_config": new_config})

    print("\nDone.")


if __name__ == "__main__":
    main()
