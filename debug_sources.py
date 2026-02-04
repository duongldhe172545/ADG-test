
import sys
import os
from pprint import pprint

# Add project root to path
sys.path.insert(0, os.getcwd())

from backend.services.notebooklm_service import NotebookLMService

def debug_sources():
    service = NotebookLMService()
    
    # Get first notebook to test
    try:
        notebooks = service.list_notebooks()
        if not notebooks:
            print("No notebooks found to test.")
            return

        notebook_id = notebooks[0].id
        print(f"Testing with notebook: {notebooks[0].title} ({notebook_id})")
        
        # Get client and raw sources
        client = service.get_client()
        raw_sources = client.get_notebook_sources_with_types(notebook_id)
        
        print(f"\nFound {len(raw_sources)} sources.")
        
        if raw_sources:
            first_source = raw_sources[0]
            print("\n--- First Source Object Inspector ---")
            print(f"Type: {type(first_source)}")
            
            if isinstance(first_source, dict):
                print("Keys:", first_source.keys())
                print("Content:", first_source)
            else:
                print(f"Dir: {dir(first_source)}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_sources()
