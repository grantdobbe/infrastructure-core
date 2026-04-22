# Core Infrastructure (pi-core)

This directory contains the primary service definitions for the "Hacker Haus" core node.

## Hardware & Environment
- **Host:** Raspberry Pi 5 (`pi-core`)
- **IP Address:** `10.10.10.10`
- **Operating System:** Linux
- **Configuration Root:** All persistent data and configuration files are stored on the host in `/srv/app-configs/<service_name>`.

## Deployment & Management
These services are managed using:
- **Komodo:** Centralized dashboard for container management and deployment.
- **Periphery:** Lightweight agent running on `pi-core` that handles the execution of these Compose stacks.

To deploy changes, commit to this repository and trigger a synchronization within the Komodo dashboard.

## Service Catalog

Unless otherwise specified, all services use LDAP or OIDC for authentication.

### Networking & Security
- **[Nginx Proxy Manager](nginx-proxy-manager.yml):** Reverse proxy with TLS through ACME.
- **[DNS](dns.yml):** Local DNS management (Technitium). Does not handle SSO at this time, creds are in 1Password.
- **[Authentik](authentik.yml):** Identity provider offering LDAP and OAuth2/OIDC for centralized authentication. 

### Documentation & Knowledge
- **[Bookstack](bookstack.yml):** Wiki and documentation platform, accessible at `docs.hacker-haus.org`.
- **[Joplin Server](joplin-server.yml):** Synchronization backend for Joplin notes.

### Productivity
- **[Radicale](radicale.yml):** CalDAV/CardDAV server for task lists.

### Dashboard & Notifications
- **[MagicMirror²](magicmirror.yml):** Centralized smart mirror information display. Does not use SSO as it is not required.
- **[Notifications](notifications.yml):** Push notifications (`ntfy`) and multi-service alert aggregation (`apprise`). Does not use SSO as multiple users aren't supported at this time.

## SSO Architecture

All user-facing services authenticate through **Authentik** using either OIDC or LDAP:

| Service | Auth Method |
| :--- | :--- |
| BookStack | OIDC |
| Joplin Server | OIDC |
| Radicale | LDAP |

External services (TrueNAS, Jellyfin, Calibre-Web, Linux hosts) also integrate via Authentik LDAP. See [`docs/sso-integration-runbook.md`](docs/sso-integration-runbook.md) for setup details.

## Scripts

- **[`scripts/authentik-wireguard-sync/`](scripts/authentik-wireguard-sync/):** Python script that syncs Authentik's `vpn-users` group to MikroTik WireGuard peers, handling IP allocation and peer lifecycle.
- **[`scripts/radicale-gtd/`](scripts/radicale-gtd/):** Bash script that bootstraps GTD task list collections (Inbox, Next Actions, Waiting For, Projects, Someday/Maybe) in Radicale.

## Configuration Structure

### Repository Layout
- **`*.yml`**: Individual Docker Compose stacks for modular deployment.
- **`stack.env`**: Environment variables and secrets used across the core stacks.
- **`authentik.env`**: Authentik-specific configuration (e.g. LDAP outpost token).
- **`scripts/`**: Custom automation and provisioning scripts.
- **`docs/`**: Integration runbooks and reference documentation.

### Server Layout
| Path | Description |
| :--- | :--- |
| `/srv/app-configs/` | Persistent volume root for all containers. |
