#!/usr/bin/env python3
"""Generate a WireGuard keypair for a user and set the public key in Authentik."""

import logging
import os
import sys
from base64 import b64encode
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from common import authentik_session, get_user_by_username, load_config, set_user_attribute

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def generate_keypair():
    private_key = X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return b64encode(private_bytes).decode(), b64encode(public_bytes).decode()


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <username>", file=sys.stderr)
        sys.exit(1)

    username = sys.argv[1]
    cfg = load_config()

    private_key, public_key = generate_keypair()

    keys_dir = Path(__file__).resolve().parent / "keys"
    keys_dir.mkdir(exist_ok=True)
    os.chmod(keys_dir, 0o700)

    key_file = keys_dir / f"{username}.key"
    pub_file = keys_dir / f"{username}.pub"

    key_file.write_text(private_key + "\n")
    os.chmod(key_file, 0o600)

    pub_file.write_text(public_key + "\n")
    os.chmod(pub_file, 0o600)

    ak = authentik_session(cfg)
    user = get_user_by_username(ak, cfg, username)
    attrs = user.get("attributes", {})
    attrs["wireguardPublicKey"] = public_key
    set_user_attribute(ak, cfg, user["pk"], attrs)

    log.info("Generated keypair for %s", username)
    log.info("Private key: %s", key_file)
    log.info("Public key:  %s", public_key)


if __name__ == "__main__":
    main()
