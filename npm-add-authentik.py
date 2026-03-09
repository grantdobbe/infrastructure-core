#!/usr/bin/env python3
"""
Adds Authentik forward auth to all Nginx Proxy Manager proxy hosts,
skipping a configurable exclusion list.

Usage:
    NPM_EMAIL=admin@example.com NPM_PASSWORD=secret python3 npm-add-authentik.py
    NPM_EMAIL=... NPM_PASSWORD=... python3 npm-add-authentik.py --dry-run
"""

import argparse
import os
import sys
import requests

NPM_URL = "http://10.10.10.10:81"

# Hosts that should NOT get Authentik (manage their own auth or are public)
EXCLUSIONS = {
    "auth.hacker-haus.org",
    "citadel.hacker-haus.org",
    "docs.hacker-haus.org",
    "grafana.hacker-haus.org",
    "ha.hacker-haus.org",
    "homeassistant.hacker-haus.org",
    "joplin.hacker-haus.org",
    "media.hacker-haus.org",
    "office.hacker-haus.org",
    "plex.hacker-haus.org",
}

AUTHENTIK_SNIPPET = """\
location /outpost.goauthentik.io {
    proxy_pass          http://10.10.10.10:9000;
    proxy_pass_request_body off;
    proxy_set_header    Content-Length "";
    proxy_set_header    X-Original-URL $scheme://$http_host$request_uri;
    proxy_set_header    Host $http_host;
    auth_request_set    $auth_cookie $upstream_http_set_cookie;
    add_header          Set-Cookie $auth_cookie;
}

auth_request /outpost.goauthentik.io/auth/nginx;
error_page 401 = @goauthentik_proxy_signin;

auth_request_set $auth_cookie $upstream_http_set_cookie;
add_header Set-Cookie $auth_cookie;

auth_request_set $authentik_username $upstream_http_x_authentik_username;
auth_request_set $authentik_groups   $upstream_http_x_authentik_groups;
auth_request_set $authentik_email    $upstream_http_x_authentik_email;
auth_request_set $authentik_name     $upstream_http_x_authentik_name;
auth_request_set $authentik_uid      $upstream_http_x_authentik_uid;

proxy_set_header X-authentik-username $authentik_username;
proxy_set_header X-authentik-groups   $authentik_groups;
proxy_set_header X-authentik-email    $authentik_email;
proxy_set_header X-authentik-name     $authentik_name;
proxy_set_header X-authentik-uid      $authentik_uid;

location @goauthentik_proxy_signin {
    internal;
    add_header Set-Cookie $auth_cookie;
    return 302 /outpost.goauthentik.io/start?rd=$request_uri;
}"""


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
    parser = argparse.ArgumentParser(description="Add Authentik forward auth to NPM proxy hosts")
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

        # Skip if any domain is in the exclusion list
        if any(d in EXCLUSIONS for d in domains):
            print(f"  SKIP (excluded): {', '.join(domains)}")
            continue

        # Skip if snippet already present
        if "outpost.goauthentik.io" in current_config:
            print(f"  SKIP (already set): {', '.join(domains)}")
            continue

        print(f"  {'[DRY RUN] ' if args.dry_run else ''}PATCH: {', '.join(domains)}")

        if not args.dry_run:
            new_config = (current_config.rstrip() + "\n\n" + AUTHENTIK_SNIPPET).lstrip()
            update_proxy_host(token, host_id, {"advanced_config": new_config})

    print("\nDone.")


if __name__ == "__main__":
    main()
