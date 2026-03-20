# SSO Integration Runbook — Jellyfin, Calibre-Web, Prometheus

## Prerequisites

- Authentik running at `auth.hacker-haus.org` with LDAP outpost (`10.10.10.10:389`)
- LDAP bind password available from Ansible vault
- Base DN: `dc=hacker-haus,dc=org`
- Bind DN: `cn=ldapservice,ou=users,dc=hacker-haus,dc=org`

---

## 1. Authentik — Create Objects

### Group

- [ ] Admin → Directory → Groups → **Create** `jellyfin-admins`
- [ ] Add admin users to the group

### Prometheus Proxy Provider + Application

- [ ] Admin → Applications → Providers → **Create** Proxy Provider:
  - Name: `prometheus-forward-auth`
  - Authorization flow: default
  - Type: **Forward auth (single application)**
  - External host: `https://prometheus.hacker-haus.org`
- [ ] Admin → Applications → **Create** Application:
  - Name: `Prometheus`
  - Slug: `prometheus`
  - Provider: `prometheus-forward-auth`
- [ ] Bind the application to the **Embedded Outpost** (or existing outpost)

---

## 2. Jellyfin — LDAP Plugin

URL: `media.hacker-haus.org`

### Install

- [ ] Dashboard → Plugins → Catalog → Install **"LDAP Authentication"**
- [ ] Restart Jellyfin

### Configure (Dashboard → Plugins → LDAP-Auth)

- [ ] LDAP Server: `10.10.10.10`
- [ ] LDAP Port: `389`
- [ ] Secure LDAP: unchecked
- [ ] LDAP Bind User: `cn=ldapservice,ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP Bind Password: *(from Ansible vault)*
- [ ] LDAP Base DN for searches: `ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP Search Filter: `(objectClass=user)`
- [ ] LDAP Search Attributes: `cn, mail`
- [ ] LDAP UID Attribute: `cn`
- [ ] LDAP Username Attribute: `cn`
- [ ] Enable User Creation: checked
- [ ] Admin Filter: `(memberOf=cn=jellyfin-admins,ou=groups,dc=hacker-haus,dc=org)`

### Verify

- [ ] Log out, log back in with an Authentik username/password
- [ ] Check Dashboard → Users — LDAP user should appear

> **Note:** Users log in with username (cn), not email. Attribute names may need
> tweaking based on the Authentik LDAP outpost schema.

---

## 3. Calibre-Web Fiction — LDAP

URL: `fiction.hacker-haus.org` (port 8083)

### Configure (Admin → Edit Basic Configuration → Feature Configuration)

- [ ] Enable **"Allow LDAP"**
- [ ] LDAP Server Host/IP: `10.10.10.10`
- [ ] LDAP Server Port: `389`
- [ ] LDAP Encryption: None
- [ ] LDAP Administrator: `cn=ldapservice,ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP Administrator Password: *(from Ansible vault)*
- [ ] LDAP Distinguished Name: `ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP User Object: `(objectClass=user)`
- [ ] LDAP Member Identifier: `cn`
- [ ] LDAP OpenLDAP: unchecked

### Post-config

- [ ] Admin → **Import LDAP Users**
- [ ] Assign permissions to imported users

### Verify

- [ ] Log in with LDAP credentials
- [ ] Imported users visible in Admin panel

---

## 4. Calibre-Web Nonfiction — LDAP

URL: `nonfiction.hacker-haus.org` (port 8183)

Same steps as Fiction.

### Configure (Admin → Edit Basic Configuration → Feature Configuration)

- [ ] Enable **"Allow LDAP"**
- [ ] LDAP Server Host/IP: `10.10.10.10`
- [ ] LDAP Server Port: `389`
- [ ] LDAP Encryption: None
- [ ] LDAP Administrator: `cn=ldapservice,ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP Administrator Password: *(from Ansible vault)*
- [ ] LDAP Distinguished Name: `ou=users,dc=hacker-haus,dc=org`
- [ ] LDAP User Object: `(objectClass=user)`
- [ ] LDAP Member Identifier: `cn`
- [ ] LDAP OpenLDAP: unchecked

### Post-config

- [ ] Admin → **Import LDAP Users**
- [ ] Assign permissions to imported users

### Verify

- [ ] Log in with LDAP credentials
- [ ] Imported users visible in Admin panel

---

## 5. Prometheus — NPM Forward Auth

URL: `prometheus.hacker-haus.org`

In the existing NPM proxy host for `prometheus.hacker-haus.org` → **Advanced** tab, add:

```nginx
location /outpost.goauthentik.io {
    internal;
    alias /dev/null;
    proxy_pass          http://10.10.10.10:9000/outpost.goauthentik.io;
    proxy_original_uri  $request_uri;
    proxy_set_header    Host $host;
    proxy_set_header    X-Original-URL $scheme://$http_host$request_uri;
    proxy_set_header    Content-Length "";
    proxy_pass_request_body off;
}

auth_request        /outpost.goauthentik.io/auth/nginx;
auth_request_set    $authentik_username $upstream_http_x_authentik_username;
auth_request_set    $authentik_groups $upstream_http_x_authentik_groups;
auth_request_set    $authentik_email $upstream_http_x_authentik_email;

proxy_set_header    X-authentik-username $authentik_username;
proxy_set_header    X-authentik-groups $authentik_groups;
proxy_set_header    X-authentik-email $authentik_email;

error_page          401 = @goauthentik_proxy_signin;

location @goauthentik_proxy_signin {
    internal;
    return 302 /outpost.goauthentik.io/start?rd=$scheme://$http_host$request_uri;
}
```

### Verify

- [ ] Visit `prometheus.hacker-haus.org` in a private window → should redirect to Authentik login
- [ ] After auth, Prometheus UI should load

---

## Notes

- LDAP traffic is unencrypted (port 389). Acceptable on local network. LDAPS available on 636 if needed later.
- NPM handles TLS termination and reverse proxying for all external access.
- No compose file changes are needed for any of these integrations.
