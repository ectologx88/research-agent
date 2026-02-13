#!/usr/bin/env python3
"""One-time OAuth2 setup for Raindrop.io — fetches tokens and stores them in SSM."""

import http.server
import json
import threading
import urllib.parse
import webbrowser

import boto3
import requests

AWS_PROFILE = "seth-dev"
AWS_REGION = "us-east-1"
SSM_PREFIX = "/prod/ResearchAgent/"
REDIRECT_PORT = 19274
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"


def get_ssm_param(ssm, name: str) -> str:
    return ssm.get_parameter(Name=f"{SSM_PREFIX}{name}", WithDecryption=True)[
        "Parameter"
    ]["Value"]


def put_ssm_param(ssm, name: str, value: str, secure: bool = True) -> None:
    ssm.put_parameter(
        Name=f"{SSM_PREFIX}{name}",
        Value=value,
        Type="SecureString" if secure else "String",
        Overwrite=True,
    )
    print(f"  Stored {SSM_PREFIX}{name}")


def capture_auth_code() -> str:
    """Start a temporary local server to capture the OAuth redirect."""
    code_holder: dict[str, str] = {}
    ready = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)

            if "code" in params:
                code_holder["code"] = params["code"][0]
                body = b"<h2>Authorization successful - you can close this tab.</h2>"
                self.send_response(200)
            elif "error" in params:
                code_holder["error"] = params["error"][0]
                body = f"<h2>Authorization failed: {params['error'][0]}</h2>".encode()
                self.send_response(400)
            else:
                body = b"<h2>Unexpected request</h2>"
                self.send_response(400)

            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
            ready.set()

        def log_message(self, *_args):
            pass  # suppress request logs

    server = http.server.HTTPServer(("127.0.0.1", REDIRECT_PORT), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    ready.wait(timeout=120)
    server.server_close()

    if "error" in code_holder:
        raise SystemExit(f"OAuth error: {code_holder['error']}")
    if "code" not in code_holder:
        raise SystemExit("Timed out waiting for authorization redirect.")
    return code_holder["code"]


def main() -> None:
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    ssm = session.client("ssm")

    # Read current credentials from SSM
    client_id = get_ssm_param(ssm, "Raindrop_ClientID")
    client_secret = get_ssm_param(ssm, "Raindrop_Token")  # currently holds the secret

    print(f"Client ID:     {client_id[:8]}...")
    print(f"Client Secret: {client_secret[:8]}...")
    print(f"Redirect URI:  {REDIRECT_URI}")

    # Step 1: Open browser for authorization
    auth_url = (
        f"https://raindrop.io/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&response_type=code"
    )
    print(f"\nOpening browser for authorization...")
    webbrowser.open(auth_url)

    # Step 2: Capture the authorization code
    print("Waiting for redirect...")
    code = capture_auth_code()
    print(f"Authorization code received: {code[:8]}...")

    # Step 3: Exchange code for tokens
    print("\nExchanging code for tokens...")
    resp = requests.post(
        "https://raindrop.io/oauth/access_token",
        headers={"Content-Type": "application/json"},
        json={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"Token exchange failed: HTTP {resp.status_code}")
        print(resp.text)
        raise SystemExit(1)

    data = resp.json()
    if "access_token" not in data:
        print(f"Token exchange failed: {json.dumps(data, indent=2)}")
        raise SystemExit(1)
    access_token = data["access_token"]
    refresh_token = data["refresh_token"]
    expires_in = data.get("expires_in", "unknown")

    print(f"Access token:  {access_token[:8]}...")
    print(f"Refresh token: {refresh_token[:8]}...")
    print(f"Expires in:    {expires_in}s")

    # Step 4: Store tokens in SSM
    print("\nUpdating SSM parameters...")
    put_ssm_param(ssm, "Raindrop_ClientSecret", client_secret)
    put_ssm_param(ssm, "Raindrop_Token", access_token)
    put_ssm_param(ssm, "Raindrop_RefreshToken", refresh_token)

    # Quick verification
    print("\nVerifying new access token...")
    check = requests.get(
        "https://api.raindrop.io/rest/v1/user",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if check.status_code == 200:
        name = check.json().get("user", {}).get("fullName", "")
        print(f"  [PASS] Raindrop.io — {name}")
    else:
        print(f"  [FAIL] HTTP {check.status_code}")

    print("\nDone. You can now run verify_connections.py")


if __name__ == "__main__":
    main()
