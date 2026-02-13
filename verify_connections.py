#!/usr/bin/env python3
"""Verify all research engine connections (SSM, NewsBlur, Raindrop, Zotero)."""

import boto3
import requests
from pyzotero import zotero


AWS_PROFILE = "seth-dev"
AWS_REGION = "us-east-1"
SSM_PREFIX = "/prod/ResearchAgent/"
SSM_KEYS = {
    "newsblur_user": f"{SSM_PREFIX}NewsBlur_User",
    "newsblur_pass": f"{SSM_PREFIX}NewsBlur_Pass",
    "raindrop_token": f"{SSM_PREFIX}Raindrop_Token",
    "raindrop_client_id": f"{SSM_PREFIX}Raindrop_ClientID",
    "raindrop_client_secret": f"{SSM_PREFIX}Raindrop_ClientSecret",
    "raindrop_refresh_token": f"{SSM_PREFIX}Raindrop_RefreshToken",
    "zotero_key": f"{SSM_PREFIX}Zotero_Token",
    "zotero_user": f"{SSM_PREFIX}Zotero_User",
}


def status(label: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    msg = f"  [{tag}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def fetch_ssm_params() -> tuple[dict[str, str], boto3.client]:
    """Fetch all required parameters from AWS SSM Parameter Store."""
    print("\n--- AWS SSM Parameter Store ---")
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    ssm = session.client("ssm")
    params: dict[str, str] = {}
    all_ok = True

    for name, path in SSM_KEYS.items():
        try:
            resp = ssm.get_parameter(Name=path, WithDecryption=True)
            params[name] = resp["Parameter"]["Value"]
            status(path, True)
        except Exception as e:
            # Raindrop refresh params are optional before first OAuth run
            if name in ("raindrop_client_secret", "raindrop_refresh_token"):
                status(path, False, "not yet created (run raindrop_oauth.py first)")
            else:
                status(path, False, str(e))
                all_ok = False

    if not all_ok:
        print("\n  Cannot continue — fix SSM issues first.")
        raise SystemExit(1)

    return params, ssm


def check_newsblur(username: str, password: str) -> None:
    """Authenticate against the NewsBlur API."""
    print("\n--- NewsBlur ---")
    try:
        resp = requests.post(
            "https://newsblur.com/api/login",
            data={"username": username, "password": password},
            timeout=15,
        )
        body = resp.json()
        ok = body.get("authenticated", False)
        status("Login", ok, f"code={body.get('code')}")
    except Exception as e:
        status("Login", False, str(e))


def refresh_raindrop_token(params: dict[str, str], ssm) -> str | None:
    """Attempt to refresh the Raindrop access token using the refresh token."""
    required = ("raindrop_client_id", "raindrop_client_secret", "raindrop_refresh_token")
    if not all(params.get(k) for k in required):
        return None

    try:
        resp = requests.post(
            "https://raindrop.io/oauth/access_token",
            headers={"Content-Type": "application/json"},
            json={
                "grant_type": "refresh_token",
                "client_id": params["raindrop_client_id"],
                "client_secret": params["raindrop_client_secret"],
                "refresh_token": params["raindrop_refresh_token"],
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        new_access = data["access_token"]
        new_refresh = data["refresh_token"]

        # Persist new tokens to SSM
        for name, value in [("Raindrop_Token", new_access), ("Raindrop_RefreshToken", new_refresh)]:
            ssm.put_parameter(
                Name=f"{SSM_PREFIX}{name}",
                Value=value,
                Type="SecureString",
                Overwrite=True,
            )
        print("  Token refreshed and saved to SSM")
        return new_access
    except Exception:
        return None


def check_raindrop(params: dict[str, str], ssm) -> None:
    """Verify the Raindrop.io bearer token, auto-refreshing if expired."""
    print("\n--- Raindrop.io ---")
    token = params.get("raindrop_token", "")
    try:
        resp = requests.get(
            "https://api.raindrop.io/rest/v1/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )

        if resp.status_code == 401:
            print("  Token expired, attempting refresh...")
            new_token = refresh_raindrop_token(params, ssm)
            if new_token:
                resp = requests.get(
                    "https://api.raindrop.io/rest/v1/user",
                    headers={"Authorization": f"Bearer {new_token}"},
                    timeout=15,
                )
            else:
                status("Token", False, "expired — run raindrop_oauth.py to re-authorize")
                return

        ok = resp.status_code == 200
        detail = resp.json().get("user", {}).get("fullName", "") if ok else f"HTTP {resp.status_code}"
        status("Token", ok, detail)
    except Exception as e:
        status("Token", False, str(e))


def check_zotero(api_key: str, user_id: str) -> None:
    """List top-level collections to verify the Zotero API key."""
    print("\n--- Zotero ---")
    try:
        zot = zotero.Zotero(user_id, "user", api_key)
        collections = zot.collections_top()
        names = [c["data"]["name"] for c in collections]
        ok = True
        status("API Key", ok, f"{len(names)} top-level collections")
        for name in names:
            print(f"       • {name}")
    except Exception as e:
        status("API Key", False, str(e))


def main() -> None:
    params, ssm = fetch_ssm_params()
    check_newsblur(params["newsblur_user"], params["newsblur_pass"])
    check_raindrop(params, ssm)
    check_zotero(params["zotero_key"], params["zotero_user"])
    print()


if __name__ == "__main__":
    main()
