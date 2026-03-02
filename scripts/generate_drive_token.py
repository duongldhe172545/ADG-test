"""
Generate Google Drive Refresh Token for .env

Run this script ONCE on your dev machine to get a refresh token.
Then paste it into .env as GDRIVE_REFRESH_TOKEN.

Usage:
    python scripts/generate_drive_token.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

def main():
    client_id = os.getenv('OAUTH_CLIENT_ID')
    client_secret = os.getenv('OAUTH_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        print("❌ OAUTH_CLIENT_ID and OAUTH_CLIENT_SECRET must be set in .env")
        sys.exit(1)
    
    print("=" * 60)
    print("  Google Drive Token Generator")
    print("=" * 60)
    print()
    print("This will open your browser to login with Google.")
    print("Login with the account that OWNS the Drive folders.")
    print()
    
    # Use InstalledAppFlow for local CLI auth (opens browser automatically)
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:0"],
        }
    }
    
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    credentials = flow.run_local_server(port=0, prompt='consent', access_type='offline')
    
    refresh_token = credentials.refresh_token
    
    if not refresh_token:
        print("❌ No refresh token received. Try again with a fresh consent.")
        sys.exit(1)
    
    print()
    print("=" * 60)
    print("  ✅ SUCCESS!")
    print("=" * 60)
    print()
    print("Add this line to your .env file:")
    print()
    print(f"  GDRIVE_REFRESH_TOKEN={refresh_token}")
    print()
    print("After that, the app will use this token automatically.")
    print("No browser login needed ever again!")
    print("=" * 60)


if __name__ == "__main__":
    main()
