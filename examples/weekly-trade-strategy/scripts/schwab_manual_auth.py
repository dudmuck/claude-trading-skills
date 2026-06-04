#!/usr/bin/env python3
"""Schwab manual auth flow — no browser opening required.

Prints the auth URL, asks you to paste the redirect URL after Schwab signs you in.
All in one terminal session, so there's no round-trip latency to expire the code.

Run with the same Python that schwab-mcp uses (so we share the schwab-py install):
    ~/.local/share/uv/tools/schwab-mcp/bin/python ~/schwab_manual_auth.py
"""

import os
from pathlib import Path

from schwab.auth import client_from_manual_flow

TOKEN_PATH = Path.home() / ".local/share/schwab-mcp/token.yaml"
CALLBACK_URL = "https://127.0.0.1:8182"

cid = os.environ["SCHWAB_CLIENT_ID"]
csec = os.environ["SCHWAB_CLIENT_SECRET"]

# Make sure stale file doesn't short-circuit the flow.
if TOKEN_PATH.exists():
    TOKEN_PATH.unlink()
    print(f"Removed stale {TOKEN_PATH}")

# This prints the URL, waits for stdin paste of the redirect URL, exchanges
# the code, writes the token file, and returns a client.
client = client_from_manual_flow(
    api_key=cid,
    app_secret=csec,
    callback_url=CALLBACK_URL,
    token_path=str(TOKEN_PATH),
)

# schwab-py writes the token under the process umask (commonly 022/002 -> 644/664),
# NOT 0600 — so a live 7-day refresh token can end up group/other-readable. Enforce
# owner-only perms explicitly. (Do this every run; re-auth recreates the file.)
TOKEN_PATH.chmod(0o600)

print(f"\nToken written to {TOKEN_PATH}")
perms = oct(TOKEN_PATH.stat().st_mode)[-3:]
print(f"Permissions: {perms}" + ("" if perms == "600" else "  <-- WARNING: expected 600"))
