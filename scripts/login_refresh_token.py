#!/usr/bin/env python3
"""One-time device-code login. Writes MS_REFRESH_TOKEN to the repo Actions secret; never prints it."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEVICE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPES = "Tasks.ReadWrite offline_access User.Read"
DEFAULT_CLIENT_ID = "c0a7409f-7493-4aa4-be0f-096818d12a6b"
DEFAULT_REPO = "jailedxiu/quadrant-todo"


def request_json(url: str, form: dict):
    body = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")
        if "refresh_token" in err.lower() or "access_token" in err.lower():
            err = "(token redacted from error body)"
        raise RuntimeError(f"{e.code}: {err}") from e


def main() -> int:
    client_id = os.environ.get("AZURE_CLIENT_ID") or DEFAULT_CLIENT_ID
    repo = os.environ.get("GITHUB_REPO") or DEFAULT_REPO
    start = request_json(DEVICE_URL, {"client_id": client_id, "scope": SCOPES})
    uri = start.get("verification_uri") or "https://microsoft.com/devicelogin"
    code = start.get("user_code")
    if not code:
        print("error: device code response missing user_code", file=sys.stderr)
        return 1
    print(f"Open {uri} and enter this code: {code}", flush=True)
    interval = int(start.get("interval") or 5)
    expires = int(start.get("expires_in") or 900)
    deadline = time.time() + expires
    token = None
    while time.time() < deadline:
        time.sleep(interval)
        try:
            token = request_json(
                TOKEN_URL,
                {
                    "client_id": client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": start["device_code"],
                },
            )
            break
        except RuntimeError as e:
            msg = str(e)
            if "authorization_pending" in msg:
                continue
            if "slow_down" in msg:
                interval += 5
                continue
            if "authorization_declined" in msg or "expired_token" in msg:
                print("Login was declined or expired.", file=sys.stderr)
                return 1
            # Typical when public client flows are disabled on the Azure app.
            print(f"Login failed: {e}", file=sys.stderr)
            print(
                "If this mentions unauthorized_client or public client, open Azure Portal → "
                "the app registration → Authentication: enable 'Allow public client flows', "
                "and add a Mobile and desktop platform (redirect http://localhost).",
                file=sys.stderr,
            )
            return 1
    if not token or not token.get("refresh_token"):
        print("error: no refresh_token in the response (need offline_access).", file=sys.stderr)
        return 1
    refresh = token["refresh_token"]
    # Store as a repo secret; never print the token.
    proc = subprocess.run(
        ["gh", "secret", "set", "MS_REFRESH_TOKEN", "--repo", repo],
        input=refresh.encode(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")
        print(f"gh secret set failed: {err}", file=sys.stderr)
        print("The refresh token was not printed. Re-run after fixing gh auth.", file=sys.stderr)
        return 1
    print(f"Saved MS_REFRESH_TOKEN as an Actions secret on {repo}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
