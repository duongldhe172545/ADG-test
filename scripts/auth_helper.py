#!/usr/bin/env python3
"""
NotebookLM Authentication Helper
Opens Chrome to notebooklm.google.com and extracts auth tokens after login
"""

import sys
import time
import json
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def authenticate():
    """Interactive authentication using Chrome"""
    print("🔐 NotebookLM Authentication")
    print("=" * 50)
    print("1. A Chrome window will open to NotebookLM")
    print("2. Login with your Google account")
    print("3. Once you see the NotebookLM dashboard, press ENTER here")
    print("=" * 50)
    
    # Setup Chrome with DevTools
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    try:
        driver = webdriver.Chrome(options=options)
        driver.get("https://notebooklm.google.com")
        
        print("\n⏳ Waiting for you to login...")
        print("   After login, press ENTER to continue...")
        input()
        
        # Extract cookies
        cookies = driver.get_cookies()
        page_source = driver.page_source
        current_url = driver.current_url
        
        # Look for required cookies
        cookie_dict = {}
        for cookie in cookies:
            cookie_dict[cookie['name']] = cookie['value']
        
        # Check for session cookies
        required = ['SID', 'HSID', 'SSID', 'APISID', 'SAPISID']
        found = [c for c in required if c in cookie_dict]
        
        if len(found) >= 3:
            print(f"✅ Found {len(found)} authentication cookies")
            
            # Extract CSRF token
            csrf_token = None
            if 'SNlM0e' in page_source:
                import re
                match = re.search(r'"SNlM0e":"([^"]+)"', page_source)
                if match:
                    csrf_token = match.group(1)
                    print("✅ Found CSRF token")
            
            # Extract session ID
            session_id = None
            if 'f.sid=' in page_source:
                match = re.search(r'f\.sid=(\d+)', page_source)
                if match:
                    session_id = match.group(1)
                    print("✅ Found session ID")
            
            # Save tokens
            cache_dir = Path.home() / ".notebooklm_mcp"
            cache_dir.mkdir(exist_ok=True)
            cache_file = cache_dir / "auth_tokens.json"
            
            tokens = {
                "cookies": cookie_dict,
                "csrf_token": csrf_token,
                "session_id": session_id,
                "timestamp": time.time()
            }
            
            with open(cache_file, 'w') as f:
                json.dump(tokens, f, indent=2)
            
            print(f"\n✅ Tokens saved to: {cache_file}")
            print("🎉 Authentication successful!")
            
        else:
            print(f"❌ Missing cookies. Found: {found}")
            print("   Please make sure you are fully logged in to NotebookLM")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    finally:
        try:
            driver.quit()
        except:
            pass
    
    return True

if __name__ == "__main__":
    authenticate()
