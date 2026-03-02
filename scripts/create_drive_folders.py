"""
Standalone: OAuth login + auto-create Google Drive folders.
Uses raw HTTP requests (no google-api-python-client needed).

Usage:
    python scripts/create_drive_folders.py
"""

import os
import sys
import json
import webbrowser
import urllib.parse
import http.server
import threading

# Use requests if available, else urllib
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False


# =============================================================================
# CONFIG
# =============================================================================
ROOT_FOLDER_ID = "1uCvrvjSeT7vOTMDx30eKYbqkqC5-zVTV"
OAUTH_PORT = 9876
TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".adg-kms", "oauth_token.json")

def load_env():
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, value = line.partition('=')
                    env_vars[key.strip()] = value.strip()
    return env_vars

ENV = load_env()
CLIENT_ID = ENV.get("OAUTH_CLIENT_ID", "")
CLIENT_SECRET = ENV.get("OAUTH_CLIENT_SECRET", "")


# =============================================================================
# FOLDER STRUCTURE
# =============================================================================
TEAM_SUBS = ["Strategy_Plan", "Insight_Research", "Playbook_SOP", "Campaign_Reports", "Templates_Briefs"]

FOLDER_TREE = {
    "00_HUB_Governance": {
        "Glossary_Taxonomy": {}, "Metadata_Schema": {}, "SOP_Lifecycle": {},
        "Access_DLP": {}, "Decision_Log": {}, "Golden_Answers_Template": {},
    },
    "01_Marketing_D2Com": {
        "House_ID_Development": {f: {} for f in TEAM_SUBS},
        "Community_Activation": {f: {} for f in TEAM_SUBS},
        "Product_Marketing_Solar": {f: {} for f in TEAM_SUBS},
        "Product_Marketing_Home": {f: {} for f in TEAM_SUBS},
    },
    "02_Marketing_B2B": {
        "Key_Account_Marketing": {f: {} for f in TEAM_SUBS},
        "Industrial_Solution_Marketing": {f: {} for f in TEAM_SUBS},
        "OEM_Export_Marketing": {f: {} for f in TEAM_SUBS},
        "Solar_EPC_Solution_Marketing": {f: {} for f in TEAM_SUBS},
    },
    "03_Marketing_S2B2C": {
        "Product_Marketing_Door": {f: {} for f in TEAM_SUBS},
        "Research_Marketing_Operation": {f: {} for f in TEAM_SUBS},
    },
    "04_MARCOM": {
        "Performance_Marketing": {f: {} for f in TEAM_SUBS},
        "3D_Graphic_Designer": {f: {} for f in TEAM_SUBS},
        "Trade_Marketing": {f: {} for f in TEAM_SUBS},
        "Event_Communication_Copywriter": {f: {} for f in TEAM_SUBS},
        "Corporate_Brand_Copywriter": {f: {} for f in TEAM_SUBS},
        "Brand_CX_Communication": {f: {} for f in TEAM_SUBS},
    },
    "99_Archive": {},
    "_PENDING_": {},
}


# =============================================================================
# SIMPLE HTTP HELPERS
# =============================================================================
def http_post_json(url, data=None, headers=None, json_body=None):
    """POST request returning JSON."""
    if HAS_REQUESTS:
        r = requests.post(url, data=data, json=json_body, headers=headers)
        r.raise_for_status()
        return r.json()
    else:
        if json_body:
            body = json.dumps(json_body).encode('utf-8')
            if headers is None:
                headers = {}
            headers['Content-Type'] = 'application/json'
        elif data:
            body = urllib.parse.urlencode(data).encode('utf-8')
        else:
            body = b''
        req = urllib.request.Request(url, data=body, headers=headers or {})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))


def http_get_json(url, headers=None):
    """GET request returning JSON."""
    if HAS_REQUESTS:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    else:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))


# =============================================================================
# OAUTH (manual flow using browser)
# =============================================================================
_auth_code = None

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _auth_code = params.get('code', [None])[0]
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body><h2>Login successful! You can close this tab.</h2></body></html>')
    
    def log_message(self, format, *args):
        pass  # Suppress logs


def get_access_token():
    """Get OAuth access token via browser login or saved token."""
    global _auth_code
    
    # Try saved token first
    if os.path.exists(TOKEN_PATH):
        try:
            with open(TOKEN_PATH, 'r') as f:
                token_data = json.load(f)
            
            refresh_token = token_data.get("refresh_token")
            if refresh_token:
                # Refresh the token
                result = http_post_json(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    }
                )
                access_token = result["access_token"]
                print("✅ Refreshed saved token")
                return access_token
        except Exception as e:
            print(f"⚠️  Saved token failed: {e}")
    
    # Fresh login
    print("\n🔑 Google login required...")
    
    redirect_uri = f"http://localhost:{OAUTH_PORT}/"
    auth_url = (
        "https://accounts.google.com/o/oauth2/auth?"
        + urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/drive",
            "access_type": "offline",
            "prompt": "consent",
        })
    )
    
    # Start local server to catch callback
    server = http.server.HTTPServer(("localhost", OAUTH_PORT), OAuthHandler)
    
    print(f"\n   Copy this URL and open in browser:\n")
    print(f"   {auth_url}\n")
    
    try:
        webbrowser.open(auth_url)
        print("   (Browser should open automatically)")
    except:
        pass
    
    print("\n   Waiting for login...\n")
    
    # Wait for callback
    while _auth_code is None:
        server.handle_request()
    
    server.server_close()
    
    # Exchange code for tokens
    result = http_post_json(
        "https://oauth2.googleapis.com/token",
        data={
            "code": _auth_code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    )
    
    access_token = result["access_token"]
    refresh_token = result.get("refresh_token", "")
    
    # Save token
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        json.dump({"token": access_token, "refresh_token": refresh_token}, f, indent=2)
    print(f"✅ Login successful! Token saved.")
    
    return access_token


# =============================================================================
# DRIVE FOLDER CREATION (raw REST API)
# =============================================================================
def create_folder(access_token, name, parent_id):
    """Create a folder via Drive REST API."""
    result = http_post_json(
        "https://www.googleapis.com/drive/v3/files?supportsAllDrives=true",
        json_body={
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        },
        headers={"Authorization": f"Bearer {access_token}"}
    )
    return result["id"]


def verify_root(access_token, folder_id):
    """Check root folder is accessible."""
    result = http_get_json(
        f"https://www.googleapis.com/drive/v3/files/{folder_id}?fields=id,name&supportsAllDrives=true",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    return result["name"]


def create_tree(access_token, tree, parent_id, depth=0):
    """Recursively create folders. Returns results dict."""
    results = {}
    indent = "  " * depth
    
    for name, children in tree.items():
        print(f"{indent}📁 {name}...", end=" ", flush=True)
        try:
            fid = create_folder(access_token, name, parent_id)
            print(f"✅ {fid}")
        except Exception as e:
            print(f"❌ {e}")
            continue
        
        results[name] = {"id": fid, "children": {}}
        if children:
            results[name]["children"] = create_tree(access_token, children, fid, depth + 1)
    
    return results


def count_tree(tree):
    total = 0
    for name, children in tree.items():
        total += 1
        if children:
            total += count_tree(children)
    return total


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 60)
    print("  ADG Marketing KMS - Create Google Drive Folders")
    print("=" * 60)
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("❌ Missing OAUTH_CLIENT_ID or OAUTH_CLIENT_SECRET in .env!")
        sys.exit(1)
    
    total = count_tree(FOLDER_TREE)
    print(f"\n📂 Root: {ROOT_FOLDER_ID}")
    print(f"📊 Folders to create: {total}\n")
    
    # Login
    access_token = get_access_token()
    
    # Verify root
    print("\n🔗 Verifying root folder...")
    try:
        name = verify_root(access_token, ROOT_FOLDER_ID)
        print(f"✅ Root folder: {name}\n")
    except Exception as e:
        print(f"❌ Cannot access root: {e}")
        sys.exit(1)
    
    # Confirm
    answer = input("Create all folders? (y/n): ").strip().lower()
    if answer != 'y':
        print("Cancelled.")
        return
    
    # Create
    print("\n" + "=" * 60)
    results = create_tree(access_token, FOLDER_TREE, ROOT_FOLDER_ID)
    print("=" * 60)
    
    # Save
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "drive_folder_ids.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Done! IDs saved to: {out}")
    
    # Print mapping
    print("\n" + "=" * 60)
    print("  FOLDER_NOTEBOOK_MAPPING")
    print("=" * 60)
    print("\nFOLDER_NOTEBOOK_MAPPING = {")
    for dept, ddata in results.items():
        if dept in ("99_Archive", "_PENDING_"):
            continue
        if dept == "00_HUB_Governance":
            print(f'    "{ddata["id"]}": "NOTEBOOK_ID",  # {dept}')
        else:
            for team, tdata in ddata.get("children", {}).items():
                print(f'    "{tdata["id"]}": "NOTEBOOK_ID",  # {team}')
    print("}")
    
    pending = results.get("_PENDING_", {})
    if pending:
        print(f"\n📌 .env update:")
        print(f"   GDRIVE_PENDING_FOLDER_ID={pending['id']}")


if __name__ == "__main__":
    main()
