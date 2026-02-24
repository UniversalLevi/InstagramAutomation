#!/usr/bin/env python3
"""
One-time OAuth helper: get TikTok access_token and save it to your account config.

Run from the Tiktok folder:
  cd Tiktok
  python get_tiktok_token.py
  python get_tiktok_token.py my_account   # use a different account file

Before running:
1. In TikTok Developer Portal → your app → Login Kit (or OAuth) → add Redirect URI:
   http://127.0.0.1:8765/callback
   (If TikTok rejects localhost, use ngrok: run "ngrok http 8765" and add the https URL + /callback)
2. config/accounts/my_account.yaml must have client_key and client_secret.

Then:
- Open the URL this script prints in your browser.
- Log in to TikTok and approve.
- You will be redirected back; the script will save access_token to your config and exit.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote, urlparse

PROJECT_ROOT = __file__.replace("get_tiktok_token.py", "").rstrip("/\\")
if PROJECT_ROOT and PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

PORT = 8765
REDIRECT_URI_DEFAULT = f"http://127.0.0.1:{PORT}/callback"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPE = "video.upload,video.publish"


def load_account(account_id: str) -> dict:
    from pathlib import Path
    from config.loader import get_account_config
    config = get_account_config(account_id)
    api = config.get("tiktok_api") or {}
    if not api.get("client_key") or not api.get("client_secret"):
        raise SystemExit(
            f"Account '{account_id}' must have tiktok_api.client_key and tiktok_api.client_secret in config/accounts/{account_id}.yaml"
        )
    return config


def save_tokens(account_id: str, access_token: str, refresh_token: str = "", open_id: str = ""):
    from pathlib import Path
    import yaml
    from config.loader import ACCOUNTS_DIR
    path = ACCOUNTS_DIR / f"{account_id}.yaml"
    if not path.exists():
        raise SystemExit(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    api = data.setdefault("tiktok_api", {})
    api["access_token"] = access_token
    if refresh_token:
        api["refresh_token"] = refresh_token
    if open_id:
        api["open_id"] = open_id
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"Saved access_token (and refresh_token, open_id) to {path}")


def exchange_code(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    import urllib.request
    body = (
        f"client_key={quote(client_key, safe='')}"
        f"&client_secret={quote(client_secret, safe='')}"
        f"&code={quote(code, safe='')}"
        "&grant_type=authorization_code"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
    )
    req = urllib.request.Request(
        TOKEN_URL,
        data=body.encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def main():
    account_id = sys.argv[1] if len(sys.argv) > 1 else "my_account"
    redirect_uri = os.environ.get("REDIRECT_URI", REDIRECT_URI_DEFAULT)

    config = load_account(account_id)
    api = config["tiktok_api"]
    client_key = api["client_key"]
    client_secret = api["client_secret"]

    auth_url = (
        "https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={client_key}"
        "&response_type=code"
        f"&scope={SCOPE}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        "&state=autopost"
    )

    result = {"done": False, "code": None, "error": None}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if not self.path.startswith("/callback"):
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<p>Open the authorization URL in the script output. This page is not the callback.</p>")
                return
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            code = (qs.get("code") or [None])[0]
            err = (qs.get("error") or [None])[0]
            result["code"] = code
            result["error"] = err
            result["done"] = True
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if code:
                self.wfile.write(b"<h1>Success</h1><p>You can close this tab and return to the terminal.</p>")
            else:
                self.wfile.write(f"<h1>Error</h1><p>{err or 'No code received'}</p>".encode("utf-8"))

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    print()
    print("  Step 1: Add this Redirect URI in TikTok Developer Portal (your app -> Login Kit / OAuth):")
    print(f"           {redirect_uri}")
    print()
    print("  Step 2: Open this URL in your browser, log in to TikTok, and approve:")
    print()
    print(f"  {auth_url}")
    print()
    print("  Waiting for callback on http://127.0.0.1:8765/callback ...")
    print()

    while not result["done"]:
        server.handle_request()

    if result["error"]:
        print("TikTok returned an error:", result["error"])
        sys.exit(1)
    if not result["code"]:
        print("No authorization code received.")
        sys.exit(1)

    try:
        token_data = exchange_code(client_key, client_secret, result["code"], redirect_uri)
    except Exception as e:
        print("Failed to exchange code for token:", e)
        if hasattr(e, "read"):
            print(e.read().decode() if hasattr(e.read(), "decode") else e.read())
        sys.exit(1)

    access_token = token_data.get("access_token")
    if not access_token:
        print("Token response:", json.dumps(token_data, indent=2))
        sys.exit(1)

    save_tokens(
        account_id,
        access_token,
        refresh_token=token_data.get("refresh_token", ""),
        open_id=token_data.get("open_id", ""),
    )
    print("Done. You can now use API posting (queue a video and post).")

if __name__ == "__main__":
    main()
