"""
Response Modifier for NotebookLM Chatbot
Customize and transform responses before sending to client
"""

import os
import re
from typing import Optional, Callable, List
from dotenv import load_dotenv

load_dotenv()


class ResponseModifier:
    """
    Modifies NotebookLM responses before sending to the frontend.
    
    Features:
    - Add custom branding/footer
    - Filter unwanted content
    - Format transformations
    - Custom plugins
    """
    
    def __init__(self):
        self.branding_enabled = os.getenv("ENABLE_BRANDING", "false").lower() == "true"
        self.branding_text = os.getenv("BRANDING_TEXT", "")
        self.filter_patterns: List[str] = []
        self.custom_modifiers: List[Callable[[str], str]] = []
        
        # Load filter patterns from env
        filter_env = os.getenv("FILTER_PATTERNS", "")
        if filter_env:
            self.filter_patterns = filter_env.split("|")
    
    def add_modifier(self, modifier: Callable[[str], str]):
        """Add a custom modifier function"""
        self.custom_modifiers.append(modifier)
    
    def modify(self, response: str) -> str:
        """
        Apply all modifications to the response
        
        Args:
            response: Raw response from NotebookLM
            
        Returns:
            Modified response
        """
        if not response:
            return response
        
        result = response
        
        # 1. Apply content filters
        result = self._apply_filters(result)
        
        # 2. Apply custom modifiers
        for modifier in self.custom_modifiers:
            try:
                result = modifier(result)
            except Exception as e:
                print(f"Warning: Custom modifier failed: {e}")
        
        # 3. Add branding if enabled
        if self.branding_enabled and self.branding_text:
            result = self._add_branding(result)
        
        return result
    
    def _apply_filters(self, text: str) -> str:
        """Remove unwanted content based on filter patterns"""
        result = text
        
        for pattern in self.filter_patterns:
            if pattern.strip():
                try:
                    result = re.sub(pattern, "", result, flags=re.IGNORECASE)
                except re.error:
                    # If regex is invalid, try simple string replace
                    result = result.replace(pattern, "")
        
        return result.strip()
    
    def _add_branding(self, text: str) -> str:
        """Add branding footer to response"""
        return f"{text}\n\n---\n{self.branding_text}"


# Pre-built modifier functions
def add_emoji_headers(text: str) -> str:
    """Add emojis to markdown headers"""
    emoji_map = {
        "# ": "# 📌 ",
        "## ": "## 📝 ",
        "### ": "### 💡 ",
    }
    result = text
    for old, new in emoji_map.items():
        result = result.replace(old, new)
    return result


def format_code_blocks(text: str) -> str:
    """Ensure code blocks have proper formatting"""
    # Add language hints to bare code blocks
    return re.sub(r'```\n', '```plaintext\n', text)


def sanitize_html(text: str) -> str:
    """Remove any HTML tags from response"""
    return re.sub(r'<[^>]+>', '', text)


def truncate_response(max_length: int = 2000) -> Callable[[str], str]:
    """Create a truncation modifier with specified max length"""
    def truncator(text: str) -> str:
        if len(text) > max_length:
            return text[:max_length] + "...\n\n*[Response truncated]*"
        return text
    return truncator


# Example usage and configuration
def create_default_modifier() -> ResponseModifier:
    """Create a modifier with common defaults"""
    modifier = ResponseModifier()
    
    # Add some built-in modifiers
    # modifier.add_modifier(add_emoji_headers)  # Uncomment to enable
    # modifier.add_modifier(format_code_blocks)
    # modifier.add_modifier(truncate_response(3000))
    
    return modifier


if __name__ == "__main__":
    # Test the modifier
    modifier = ResponseModifier()
    modifier.branding_enabled = True
    modifier.branding_text = "🤖 Powered by NotebookLM"
    
    test_response = """
    # Test Response
    
    This is a test response from NotebookLM.
    
    ## Key Points
    - Point 1
    - Point 2
    
    ```
    code example
    ```
    """
    
    modified = modifier.modify(test_response)
    print("Modified response:")
    print(modified)
