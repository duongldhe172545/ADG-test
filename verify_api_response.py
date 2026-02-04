
import requests
import json
import sys

def verify_api():
    url = "http://localhost:8080/api/v1/chat/sources/c109af87-e8b5-4b27-a65a-f202013728f2"
    try:
        print(f"Calling {url}...")
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Response JSON:")
            print(json.dumps(data, indent=2))
            
            # Validation
            sources = data.get('sources', [])
            if not sources:
                print("❌ No sources found in response.")
            else:
                valid = True
                for s in sources:
                    if s.get('title') == 'Untitled' or s.get('type') == 'unknown':
                        print(f"❌ Invalid source found: {s}")
                        valid = False
                if valid:
                    print("✅ All sources appear valid (Title present, Type present).")
        else:
            print(f"❌ Error response: {response.text}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    verify_api()
