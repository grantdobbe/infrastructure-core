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

### Networking & Security
- **[Caddy](caddy.yml):** Modern reverse proxy with automatic TLS. Uses modular configurations in `configs/sites/`.
- **[DNS](dns.yml):** Local DNS management (Technitium).
- **[LLDAP](lldap.yml):** Lightweight LDAP server for centralized authentication across the lab.

### Documentation & Knowledge
- **[Bookstack](bookstack.yml):** Wiki and documentation platform, accessible at `docs.hacker-haus.org`.
- **[Joplin Server](joplin-server.yml):** Synchronization backend for Joplin notes.

### Dashboard & Notifications
- **[MagicMirror²](magicmirror.yml):** Centralized smart mirror information display.
- **[Notifications](notifications.yml):** Handling for `ntfy` and `apprise` services for system alerts.

## Configuration Structure

### Repository Layout
- **`*.yml`**: Individual Docker Compose stacks for modular deployment.
- **`configs/`**: Manual configuration files (e.g., Caddyfile) that should be synced to `/srv/app-configs/caddy/`.
- **`stack.env`**: Environment variables and secrets used across the core stacks.

### Server Layout
| Path | Description |
| :--- | :--- |
| `/srv/app-configs/` | Persistent volume root for all containers. |
| `/srv/app-configs/caddy/` | Caddy entry point and modular site blocks. |

## Maintenance
To reload the reverse proxy after updating site configs:
```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```
