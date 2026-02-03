
import os
import sys
from notebooklm_mcp.api_client import NotebookLMClient, extract_cookies_from_chrome_export
from notebooklm_mcp.auth import load_cached_tokens

def get_client():
    cookie_header = os.environ.get("NOTEBOOKLM_COOKIES", "")
    csrf_token = os.environ.get("NOTEBOOKLM_CSRF_TOKEN", "")
    session_id = os.environ.get("NOTEBOOKLM_SESSION_ID", "")

    if cookie_header:
        cookies = extract_cookies_from_chrome_export(cookie_header)
    else:
        cached = load_cached_tokens()
        if cached:
            cookies = cached.cookies
            csrf_token = csrf_token or cached.csrf_token
            session_id = session_id or cached.session_id
        else:
            print("No authentication found. Please run 'notebooklm-mcp-auth' to authenticate.")
            return None

    return NotebookLMClient(cookies=cookies, csrf_token=csrf_token, session_id=session_id)

def main():
    try:
        client = get_client()
        if not client:
            return

        print("Fetching notebooks...")
        notebooks = client.list_notebooks()
        
        if not notebooks:
            print("No notebooks found.")
            return

        print(f"\nFound {len(notebooks)} notebooks:\n")
        for i, nb in enumerate(notebooks, 1):
            print(f"{i}. {nb.title}")
            print(f"   ID: {nb.id}")
            print(f"   Sources: {nb.source_count}")
            print(f"   URL: https://notebooklm.google.com/notebook/{nb.id}")
            print("")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    main()
