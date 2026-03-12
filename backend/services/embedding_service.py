"""
Embedding Service
Direct REST API calls to Gemini Embedding API v1 (bypasses SDK v1beta issue).
Features: batching, retry with backoff, and in-memory caching.
"""

import os
import time
import hashlib
import requests
from typing import List, Optional

from dotenv import load_dotenv
load_dotenv()

from backend.logger import get_logger

logger = get_logger("embedding")


class EmbeddingService:
    """
    Generate embeddings using Google Gemini Embedding API (REST v1).
    Uses direct HTTP calls to avoid SDK v1beta routing issues.
    """

    MODEL = "gemini-embedding-001"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    DIMENSIONS = 768
    BATCH_SIZE = 100
    MAX_RETRIES = 3

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY not found. Set it in .env or pass as argument. "
                "Get a free key at https://aistudio.google.com/apikey"
            )
        self._cache = {}

    def embed_text(self, text: str) -> List[float]:
        """Embed a single text string. Returns 768-dim vector."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        result = self._embed_with_retry([text], task_type="RETRIEVAL_QUERY")
        embedding = result[0]
        
        if len(self._cache) < 2000:
            self._cache[cache_key] = embedding
        
        return embedding

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple texts in batches. Returns list of 768-dim vectors."""
        if not texts:
            return []

        all_embeddings = []
        
        for i in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[i:i + self.BATCH_SIZE]
            batch_embeddings = self._embed_with_retry(batch, task_type="RETRIEVAL_DOCUMENT")
            all_embeddings.extend(batch_embeddings)
            
            if i + self.BATCH_SIZE < len(texts):
                time.sleep(0.1)

        return all_embeddings

    def _embed_with_retry(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """Embed via Gemini REST API v1 with retry."""
        last_error = None
        
        for attempt in range(self.MAX_RETRIES):
            try:
                if len(texts) == 1:
                    return [self._embed_single(texts[0], task_type)]
                else:
                    return self._embed_batch(texts, task_type)
                
            except Exception as e:
                last_error = e
                if "429" in str(e) or "quota" in str(e).lower():
                    wait = (2 ** attempt) * 2
                    logger.warning(f"Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                elif attempt < self.MAX_RETRIES - 1:
                    wait = 2 ** attempt
                    logger.warning(f"Error: {e}, retrying in {wait}s...")
                    time.sleep(wait)

        raise RuntimeError(f"Embedding failed after {self.MAX_RETRIES} retries: {last_error}")

    def _embed_single(self, text: str, task_type: str) -> List[float]:
        """Embed single text via REST API."""
        url = f"{self.BASE_URL}/models/{self.MODEL}:embedContent?key={self.api_key}"
        
        payload = {
            "model": f"models/{self.MODEL}",
            "content": {
                "parts": [{"text": text}]
            },
            "taskType": task_type,
            "outputDimensionality": self.DIMENSIONS,
        }
        
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Embedding API error {resp.status_code}: {resp.text}")
        
        data = resp.json()
        return data["embedding"]["values"]

    def _embed_batch(self, texts: List[str], task_type: str) -> List[List[float]]:
        """Embed batch of texts via REST API (batchEmbedContents)."""
        url = f"{self.BASE_URL}/models/{self.MODEL}:batchEmbedContents?key={self.api_key}"
        
        requests_list = []
        for text in texts:
            requests_list.append({
                "model": f"models/{self.MODEL}",
                "content": {
                    "parts": [{"text": text}]
                },
                "taskType": task_type,
                "outputDimensionality": self.DIMENSIONS,
            })
        
        payload = {"requests": requests_list}
        
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Batch embedding API error {resp.status_code}: {resp.text}")
        
        data = resp.json()
        return [emb["values"] for emb in data["embeddings"]]

    def clear_cache(self):
        """Clear the embedding cache."""
        self._cache.clear()
