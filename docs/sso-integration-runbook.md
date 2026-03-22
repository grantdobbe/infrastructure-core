# SSO Integration Runbook — Authentik LDAP

## Prerequisites

- Authentik running at `auth.hacker-haus.org` with LDAP outpost (`10.10.10.10:389`)
- LDAP bind password available from Ansible vault
- Base DN: `dc=hacker-haus,dc=org`
- Bind DN: `cn=ldapservice,ou=users,dc=hacker-haus,dc=org`

---

## 0. Authentik — Required Setup

These must be done before any service can use LDAP.

### ldapservice permissions

- [ ] Admin → Directory → Users → `ldapservice` → Permissions tab
- [ ] Assign the **"Search full LDAP directory"** permission
- [ ] Without this, the service account can only see its own entry

### SSH public keys

For any user that needs SSH key auth via LDAP:

- [ ] Admin → Directory → Users → edit user → Attributes (YAML block)
- [ ] Add: `sshPublicKey: "ssh-ed25519 AAAA... user@host"`
- [ ] The LDAP outpost exposes this automatically as an LDAP attribute

### Groups

- [ ] Create `jellyfin-admins` group, add admin users
- [ ] Create `truenas-admins` group (if needed for TrueNAS privilege mapping)

### Prometheus forward auth objects

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

## 1. TrueNAS SCALE — LDAP + SSH Keys

### LDAP Directory Service

Credentials → Directory Services → Configure LDAP:

| Setting | Value |
|---------|-------|
| Hostname | `10.10.10.10` |
| Base DN | `dc=hacker-haus,dc=org` |
| Bind DN | `cn=ldapservice,ou=users,dc=hacker-haus,dc=org` |
| Bind Password | *(from vault)* |
| Enable | checked |
| Encryption Mode | OFF |
| Validate Certificates | unchecked |
| Schema | RFC2307BIS |

**Auxiliary Parameters** (no leading whitespace on any line):

```
services = nss, pam, ssh
access_provider = permit

ldap_user_object_class = user
ldap_user_name = cn
ldap_user_ssh_public_key = sshPublicKey

ldap_group_object_class = group
ldap_group_name = cn

ldap_user_search_base = ou=users,dc=hacker-haus,dc=org
ldap_group_search_base = ou=groups,dc=hacker-haus,dc=org
ldap_netgroup_search_base = dc=hacker-haus,dc=org
```

> **Known issues:**
> - TrueNAS injects FreeIPA-style search bases (`cn=users,cn=accounts,...`)
>   with broken indentation. The auxiliary parameter overrides above fix this.
> - "Rebuild Directory Service Cache" may time out due to SSSD rootDSE
>   incompatibility with Authentik. Direct lookups (`getent passwd <user>`)
>   work regardless.
> - TrueNAS uses SSSD 2.9.x which handles Authentik's rootDSE differently
>   than newer versions (2.12+).

### SSH public key auth

On TrueNAS, ensure `/etc/ssh/sshd_config` contains:

```
AuthorizedKeysCommand /usr/bin/sss_ssh_authorizedkeys %u
AuthorizedKeysCommandUser nobody
```

Verify with: `sss_ssh_authorizedkeys <username>`

### Admin privilege mapping

- [ ] After LDAP is connected and cache is built, go to **Credentials → Groups → Privileges**
- [ ] Click **Add**, set **DS Groups** to `truenas-admins`, **Roles** to desired level

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

> **Note:** Users log in with username (cn), not email.

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

Same settings as Fiction above.

- [ ] Enable **"Allow LDAP"** and configure all LDAP fields identically
- [ ] Admin → **Import LDAP Users**
- [ ] Assign permissions to imported users
- [ ] Verify login with LDAP credentials

---

## 5. Prometheus — NPM Forward Auth

URL: `prometheus.hacker-haus.org`

In the existing NPM proxy host → **Advanced** tab, add:

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

## 6. Linux Hosts — SSSD + SSH Keys (via Ansible)

Managed by `ansible/pam-ldap.yml` using the `sssd_ldap` role.

```bash
cd ansible
ansible-playbook pam-ldap.yml --ask-vault-pass
```

This configures:
- SSSD with Authentik LDAP (user/group lookup, PAM auth)
- nsswitch.conf (`files sss` for passwd/group/shadow)
- sshd `AuthorizedKeysCommand` for LDAP SSH public keys
- `pam_mkhomedir` for automatic home directory creation

### Key SSSD settings for Authentik compatibility

| Setting | Value | Why |
|---------|-------|-----|
| `ldap_user_name` | `cn` | Authentik's `uid` is numeric; `cn` is the username |
| `ldap_group_name` | `cn` | Same reason |
| `ldap_user_object_class` | `user` | Authentik uses `user`, not `posixAccount` |
| `ldap_group_object_class` | `group` | Authentik uses `group`, not `posixGroup` |
| `ldap_schema` | `rfc2307bis` | Authentik uses `member` (not `memberUid`) |
| `ldap_user_ssh_public_key` | `sshPublicKey` | Maps to user's custom attribute in Authentik |
| `enumerate` | `false` | Enumeration can cause rootDSE timeout issues |
| `access_provider` | `permit` | Allow all LDAP users to log in |

---

## Notes

- LDAP traffic is unencrypted (port 389). Acceptable on local network. LDAPS available on 636 if needed.
- NPM handles TLS termination and reverse proxying for all external access.
- No compose file changes are needed for any of these integrations.
- The `ldapservice` user **must** have the "Search full LDAP directory" permission in Authentik (replaced the old "Search group" setting in 2024.8).
