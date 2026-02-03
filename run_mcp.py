
import sys
import io

# Simple delegation approach
class SimpleFilteredStdout:
    def __init__(self, original):
        self.original = original
        # Copy encoding if available, otherwise default to utf-8
        self.encoding = getattr(original, 'encoding', 'utf-8')
        
    def write(self, s):
        # Filter out banner lines
        if any(c in s for c in ['╭', '│', '╰', '─']):
            return len(s)
        if "FastMCP server" in s:
            return len(s)
        return self.original.write(s)
        
    def flush(self):
        if hasattr(self.original, 'flush'):
            self.original.flush()
        
    def __getattr__(self, name):
        return getattr(self.original, name)

# Patch stdout BEFORE importing notebooklm_mcp.server
# because FastMCP initializes at module level
original_stdout = sys.stdout
sys.stdout = SimpleFilteredStdout(original_stdout)

from notebooklm_mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
