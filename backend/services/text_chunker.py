"""
Text Chunker Service
Split text into overlapping chunks for RAG embedding.
Uses recursive character splitting with configurable size and overlap.
"""

import os
from typing import List, Dict, Any


class TextChunker:
    """
    Recursive character text splitter.
    
    Splits text into chunks of approximately `chunk_size` tokens,
    with `chunk_overlap` tokens of overlap between consecutive chunks.
    
    Split priority: paragraph → newline → sentence → space → character
    """

    DEFAULT_CHUNK_SIZE = 800      # tokens
    DEFAULT_CHUNK_OVERLAP = 200   # tokens
    CHARS_PER_TOKEN = 4           # approximate for English/Vietnamese

    SEPARATORS = [
        "\n\n",     # Paragraph break
        "\n",       # Line break
        ". ",       # Sentence end
        "! ",       # Exclamation
        "? ",       # Question
        "; ",       # Semicolon
        ", ",       # Comma
        " ",        # Word boundary
        "",         # Character level (last resort)
    ]

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or int(os.getenv("RAG_CHUNK_SIZE", self.DEFAULT_CHUNK_SIZE))
        self.chunk_overlap = chunk_overlap or int(os.getenv("RAG_CHUNK_OVERLAP", self.DEFAULT_CHUNK_OVERLAP))
        
        # Convert token counts to character counts (approximate)
        self._max_chars = self.chunk_size * self.CHARS_PER_TOKEN
        self._overlap_chars = self.chunk_overlap * self.CHARS_PER_TOKEN

    def split_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: The full text to split
            
        Returns:
            List of text chunks
        """
        if not text or not text.strip():
            return []

        text = text.strip()
        
        # If text fits in one chunk, return as-is
        if len(text) <= self._max_chars:
            return [text]

        return self._recursive_split(text, self.SEPARATORS)

    def split_text_with_metadata(
        self, 
        text: str, 
        file_id: str, 
        file_name: str,
        folder_id: str = None,
        folder_path: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Split text into chunks with metadata for each chunk.
        
        Returns:
            List of dicts with keys: chunk_text, chunk_index, file_id, file_name, etc.
        """
        chunks = self.split_text(text)
        
        return [
            {
                "chunk_text": chunk,
                "chunk_index": i,
                "file_id": file_id,
                "file_name": file_name,
                "folder_id": folder_id,
                "folder_path": folder_path,
                "token_count": self._estimate_tokens(chunk),
            }
            for i, chunk in enumerate(chunks)
        ]

    def _recursive_split(self, text: str, separators: List[str]) -> List[str]:
        """Recursively split text using separators in priority order."""
        final_chunks = []
        
        # Find the best separator that exists in the text
        separator = ""
        for sep in separators:
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                break

        # Split by the chosen separator
        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # Merge small splits into chunks of appropriate size
        current_chunk = []
        current_length = 0

        for split in splits:
            split_length = len(split) + len(separator)

            if current_length + split_length > self._max_chars and current_chunk:
                # Current chunk is full, finalize it
                merged = separator.join(current_chunk)
                
                if len(merged) > self._max_chars:
                    # Chunk still too big, need to split further
                    remaining_seps = separators[separators.index(separator) + 1:] if separator in separators else [""]
                    if remaining_seps:
                        final_chunks.extend(self._recursive_split(merged, remaining_seps))
                    else:
                        final_chunks.append(merged[:self._max_chars])
                else:
                    final_chunks.append(merged)

                # Start new chunk with overlap
                overlap_text = separator.join(current_chunk[-2:]) if len(current_chunk) >= 2 else ""
                if overlap_text and len(overlap_text) <= self._overlap_chars:
                    current_chunk = [overlap_text, split]
                    current_length = len(overlap_text) + split_length
                else:
                    current_chunk = [split]
                    current_length = split_length
            else:
                current_chunk.append(split)
                current_length += split_length

        # Don't forget the last chunk
        if current_chunk:
            merged = separator.join(current_chunk)
            if merged.strip():
                final_chunks.append(merged)

        return [c for c in final_chunks if c.strip()]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (4 chars ≈ 1 token for mixed content)."""
        return len(text) // 4
