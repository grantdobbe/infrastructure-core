#!/usr/bin/env bash
#
# Creates GTD task list collections in Radicale's data directory.
#
# Radicale stores collections as directories with a .Radicale.props JSON file
# that defines the collection type and display name. This script creates the
# directory structure so the collections exist before any client connects.
#
# Usage: ./setup-collections.sh [DATA_DIR] [USERNAME]
#   DATA_DIR  - Radicale data root (default: /srv/app-configs/radicale/data)
#   USERNAME  - Radicale username (default: gdobbe)

set -euo pipefail

DATA_DIR="${1:-/srv/app-configs/radicale/data}"
USERNAME="${2:-gdobbe}"
COLLECTIONS_ROOT="${DATA_DIR}/collections/collection-root/${USERNAME}"

# GTD collections: directory name -> display name
declare -A COLLECTIONS=(
    [gtd-inbox]="GTD Inbox"
    [gtd-next]="GTD Next Actions"
    [gtd-waiting]="GTD Waiting For"
    [gtd-projects]="GTD Projects"
    [gtd-someday]="GTD Someday/Maybe"
)

echo "Creating GTD collections in: ${COLLECTIONS_ROOT}"

mkdir -p "${COLLECTIONS_ROOT}"

for dir in "${!COLLECTIONS[@]}"; do
    display_name="${COLLECTIONS[$dir]}"
    collection_path="${COLLECTIONS_ROOT}/${dir}"

    mkdir -p "${collection_path}"

    # Write Radicale props file (defines this directory as a VTODO calendar)
    cat > "${collection_path}/.Radicale.props" <<EOF
{"C:supported-calendar-component-set": "VTODO", "D:displayname": "${display_name}", "tag": "VCALENDAR"}
EOF

    echo "  Created: ${dir} (${display_name})"
done

echo ""
echo "Done. Collections are ready for Radicale to serve."
echo ""
echo "If this is a fresh install, also create an htpasswd user:"
echo "  htpasswd -B -c ${DATA_DIR}/users ${USERNAME}"
