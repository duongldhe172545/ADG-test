
import sys
import os
import json
from pprint import pprint

# Add project root to path
sys.path.insert(0, os.getcwd())

from backend.services.notebooklm_service import NotebookLMService

def debug_sources_deep():
    print("Initializing NotebookLM Service...")
    service = NotebookLMService()
    
    notebook_id = "c109af87-e8b5-4b27-a65a-f202013728f2" # Users specific notebook
    print(f"Getting sources for notebook: {notebook_id}")
    
    try:
        client = service.get_client()
        raw_sources = client.get_notebook_sources_with_types(notebook_id)
        
        print(f"\nFound {len(raw_sources)} raw sources.")
        
        for i, source in enumerate(raw_sources):
            print(f"\n--- Source {i+1} ---")
            print(f"Type: {type(source)}")
            if isinstance(source, dict):
                print(f"Keys: {list(source.keys())}")
                print(f"Content: {json.dumps(source, default=str, indent=2)}")
            else:
                print(f"Dir: {dir(source)}")
                # Try to extract props
                props = {}
                for attr in dir(source):
                    if not attr.startswith('_'):
                        try:
                            val = getattr(source, attr)
                            if not callable(val):
                                props[attr] = val
                        except:
                            pass
                print(f"Properties: {props}")

    except Exception as e:
        print(f"Create Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_sources_deep()
