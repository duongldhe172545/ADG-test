"""
RAG Service — Core RAG orchestration (pgvector + asyncpg)
Handles document indexing (parse → chunk → embed → PostgreSQL pgvector)
and query pipeline (embed query → similarity search → LLM generate).
Uses PostgreSQL + pgvector via asyncpg (same driver as the main app).
"""

import os
import time
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv()  # Load .env vars so os.getenv() works

import asyncpg

from backend.services.document_parser import DocumentParser
from backend.services.text_chunker import TextChunker
from backend.services.embedding_service import EmbeddingService


class RAGService:
    """
    Core RAG orchestration service using PostgreSQL + pgvector.
    
    - Index: Download file → parse → chunk → embed → store in pgvector
    - Query: Embed question → cosine similarity search → build prompt → call Gemini
    """

    EMBEDDING_DIMS = 768  # Gemini text-embedding-004

    def __init__(self):
        self._embedding_service = None
        self._genai = None
        self._parser = DocumentParser()
        self._chunker = TextChunker()
        self._db_url = os.getenv(
            "RAG_DATABASE_URL",
            os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/adg_vectors")
        )
        self._pool = None
        self._initialized = False

    @property
    def embedding_service(self) -> EmbeddingService:
        if self._embedding_service is None:
            self._embedding_service = EmbeddingService()
        return self._embedding_service

    def _generate_text(self, prompt: str) -> str:
        """Generate text using Gemini REST API v1."""
        import requests as req
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        model = os.getenv("RAG_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        resp = req.post(url, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")
        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
        return ""

    def _generate_text_stream(self, prompt: str):
        """Stream text from Gemini REST API. Yields text chunks."""
        import requests as req
        import json as _json
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        model = os.getenv("RAG_MODEL", "gemini-2.0-flash")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?key={api_key}&alt=sse"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        with req.post(url, json=payload, timeout=120, stream=True) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")
            resp.encoding = 'utf-8'  # Force UTF-8 (requests defaults to ISO-8859-1 for streaming)
            for line in resp.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    try:
                        data = _json.loads(line[6:])
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                text = parts[0].get("text", "")
                                if text:
                                    yield text
                    except _json.JSONDecodeError:
                        continue

    async def _get_pool(self):
        """Get or create asyncpg connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._db_url, min_size=1, max_size=5)
        return self._pool

    async def _ensure_table(self):
        """Ensure pgvector extension and document_chunks table exist."""
        if self._initialized:
            return

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Create extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # Create table
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    file_id VARCHAR(255) NOT NULL,
                    file_name VARCHAR(500) NOT NULL,
                    folder_id VARCHAR(255),
                    folder_path VARCHAR(1000),
                    chunk_index INTEGER NOT NULL,
                    chunk_text TEXT NOT NULL,
                    token_count INTEGER,
                    embedding vector({self.EMBEDDING_DIMS}),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    UNIQUE(file_id, chunk_index)
                );
            """)

            # Create indexes
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_file_id 
                ON document_chunks(file_id);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_folder_id 
                ON document_chunks(folder_id);
            """)

        self._initialized = True

    # ========================================================================
    # Indexing
    # ========================================================================

    async def index_file_from_bytes(
        self,
        content: bytes,
        file_id: str,
        file_name: str,
        mime_type: str = None,
        folder_id: str = None,
        folder_path: str = None,
    ) -> Dict[str, Any]:
        """
        Index a file: parse → chunk → embed → store in pgvector.
        """
        start = time.time()
        await self._ensure_table()

        # 1. Parse document
        try:
            text = self._parser.parse_bytes(content, file_name, mime_type)
        except Exception as e:
            return {"success": False, "error": f"Parse failed: {e}", "file_id": file_id}

        if not text.strip():
            return {"success": False, "error": "No text extracted", "file_id": file_id}

        # 2. Chunk text
        chunks = self._chunker.split_text_with_metadata(
            text=text,
            file_id=file_id,
            file_name=file_name,
            folder_id=folder_id,
            folder_path=folder_path,
        )

        if not chunks:
            return {"success": False, "error": "No chunks created", "file_id": file_id}

        # 3. Embed chunks (sync call — Gemini API)
        chunk_texts = [c["chunk_text"] for c in chunks]
        embeddings = self.embedding_service.embed_texts(chunk_texts)

        # 4. Store in PostgreSQL (upsert)
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Delete old chunks for this file (idempotent re-index)
            await conn.execute("DELETE FROM document_chunks WHERE file_id = $1", file_id)

            # Insert new chunks
            for chunk, embedding in zip(chunks, embeddings):
                # Convert embedding list to pgvector string format
                embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                await conn.execute("""
                    INSERT INTO document_chunks 
                    (file_id, file_name, folder_id, folder_path, chunk_index, 
                     chunk_text, token_count, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
                """,
                    chunk["file_id"],
                    chunk["file_name"],
                    chunk.get("folder_id"),
                    chunk.get("folder_path"),
                    chunk["chunk_index"],
                    chunk["chunk_text"],
                    chunk["token_count"],
                    embedding_str,
                )

        elapsed = time.time() - start
        return {
            "success": True,
            "file_id": file_id,
            "file_name": file_name,
            "chunks_count": len(chunks),
            "total_tokens": sum(c["token_count"] for c in chunks),
            "elapsed_seconds": round(elapsed, 2),
        }

    async def index_file_from_drive(
        self,
        file_id: str,
        file_name: str,
        mime_type: str = None,
        folder_id: str = None,
        folder_path: str = None,
    ) -> Dict[str, Any]:
        """Download a file from Google Drive and index it."""
        from backend.api.v1.documents import get_gdrive_service

        try:

            gdrive = get_gdrive_service()
            service = gdrive.service


            # Handle Google Docs (export as text)
            if mime_type == 'application/vnd.google-apps.document':
                request = service.files().export(
                    fileId=file_id, mimeType='text/plain'
                )
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                request = service.files().export(
                    fileId=file_id, mimeType='text/csv'
                )
            else:
                request = service.files().get_media(fileId=file_id)

            import io
            from googleapiclient.http import MediaIoBaseDownload
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            content = fh.getvalue()


            result = await self.index_file_from_bytes(
                content=content,
                file_id=file_id,
                file_name=file_name,
                mime_type=mime_type,
                folder_id=folder_id,
                folder_path=folder_path,
            )

            return result
        except Exception as e:

            return {"success": False, "error": f"Drive download failed: {e}", "file_id": file_id}

    # ========================================================================
    # Query
    # ========================================================================

    async def query(
        self,
        question: str,
        top_k: int = None,
        folder_ids: List[str] = None,
        file_ids: List[str] = None,
        chat_history: List[Dict] = None,
    ) -> Dict[str, Any]:
        """
        RAG query: embed question → pgvector cosine search → generate answer.
        file_ids takes priority over folder_ids for filtering.
        """
        start = time.time()
        top_k = top_k or int(os.getenv("RAG_TOP_K", "8"))
        await self._ensure_table()

        # 1. Embed the question (sync — Gemini API)
        query_embedding = self.embedding_service.embed_text(question)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        # 2. Cosine similarity search in pgvector
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if file_ids:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    WHERE file_id = ANY($2)
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """, embedding_str, file_ids, top_k)
            elif folder_ids:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    WHERE folder_id = ANY($2)
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """, embedding_str, folder_ids, top_k)
            else:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, top_k)

        if not results:
            return {
                "answer": "Không tìm thấy thông tin liên quan trong tài liệu. Hãy thử hỏi cách khác hoặc kiểm tra xem tài liệu đã được index chưa.",
                "citations": [],
                "chunks_used": 0,
                "elapsed_seconds": round(time.time() - start, 2),
            }

        # 3. Build source references (deduplicated by file)
        sources = []
        chunks = []
        metadatas = []
        seen_files = {}  # file_id -> citation index
        for i, row in enumerate(results):
            chunk_text = row["chunk_text"]
            chunks.append(chunk_text)
            metadatas.append(dict(row))

            fid = row["file_id"]
            if fid in seen_files:
                # Same file — increment chunk count
                sources[seen_files[fid]]["chunks_used"] += 1
            else:
                seen_files[fid] = len(sources)
                sources.append({
                    "number": len(sources) + 1,
                    "file_name": row["file_name"],
                    "file_id": fid,
                    "folder_path": row.get("folder_path", ""),
                    "chunk_text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                    "relevance": round(float(row["similarity"]), 3),
                    "chunks_used": 1,
                })

        # 4. Build prompt
        prompt = self._build_prompt(question, chunks, metadatas, chat_history)

        # 5. Generate answer with Gemini (REST API)
        try:
            answer = self._generate_text(prompt)
        except Exception as e:
            answer = f"Lỗi khi tạo câu trả lời: {e}"

        elapsed = time.time() - start
        return {
            "answer": answer,
            "citations": sources,
            "chunks_used": len(chunks),
            "elapsed_seconds": round(elapsed, 2),
        }

    async def query_stream(self, question: str, chat_history: List[Dict],
                           file_ids=None, folder_ids=None):
        """
        Same as query() but streams the answer text chunk by chunk.
        Yields dicts: first {"type":"meta","citations":...} then {"type":"text","chunk":"..."}.
        """
        import time
        start = time.time()
        top_k = int(os.getenv("RAG_TOP_K", "8"))
        await self._ensure_table()

        query_embedding = self.embedding_service.embed_text(question)
        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if file_ids:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    WHERE file_id = ANY($2)
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """, embedding_str, file_ids, top_k)
            elif folder_ids:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    WHERE folder_id = ANY($2)
                    ORDER BY embedding <=> $1::vector
                    LIMIT $3
                """, embedding_str, folder_ids, top_k)
            else:
                results = await conn.fetch("""
                    SELECT file_id, file_name, folder_path, chunk_index, chunk_text,
                           1 - (embedding <=> $1::vector) AS similarity
                    FROM document_chunks
                    ORDER BY embedding <=> $1::vector
                    LIMIT $2
                """, embedding_str, top_k)

        if not results:
            yield {"type": "meta", "citations": [], "chunks_used": 0}
            yield {"type": "text", "chunk": "Không tìm thấy thông tin liên quan trong tài liệu."}
            yield {"type": "done", "elapsed_seconds": round(time.time() - start, 2), "full_answer": ""}
            return

        # Build sources
        sources, chunks, metadatas = [], [], []
        seen_files = {}
        for row in results:
            chunk_text = row["chunk_text"]
            chunks.append(chunk_text)
            metadatas.append(dict(row))
            fid = row["file_id"]
            if fid in seen_files:
                sources[seen_files[fid]]["chunks_used"] += 1
            else:
                seen_files[fid] = len(sources)
                sources.append({
                    "number": len(sources) + 1,
                    "file_name": row["file_name"],
                    "file_id": fid,
                    "folder_path": row.get("folder_path", ""),
                    "chunk_text": chunk_text[:200] + "..." if len(chunk_text) > 200 else chunk_text,
                    "relevance": round(float(row["similarity"]), 3),
                    "chunks_used": 1,
                })

        prompt = self._build_prompt(question, chunks, metadatas, chat_history)

        # Yield metadata first
        yield {"type": "meta", "citations": sources, "chunks_used": len(chunks)}

        # Stream answer text
        full_answer = ""
        try:
            for text_chunk in self._generate_text_stream(prompt):
                full_answer += text_chunk
                yield {"type": "text", "chunk": text_chunk}
        except Exception as e:
            yield {"type": "text", "chunk": f"\n\nLỗi: {e}"}

        elapsed = time.time() - start
        yield {"type": "done", "elapsed_seconds": round(elapsed, 2), "full_answer": full_answer}

    def _build_prompt(
        self,
        question: str,
        chunks: List[str],
        metadatas: List[Dict],
        chat_history: List[Dict] = None,
    ) -> str:
        """Build the RAG prompt with system instruction, sources, and question."""

        # Group chunks by file
        file_chunks = {}
        for chunk, meta in zip(chunks, metadatas):
            fname = meta.get("file_name", "Unknown") if isinstance(meta, dict) else "Unknown"
            if fname not in file_chunks:
                file_chunks[fname] = []
            file_chunks[fname].append(chunk)

        num_files = len(file_chunks)

        prompt = """Bạn là trợ lý AI của ADG Knowledge Hub. Trả lời câu hỏi DỰA TRÊN các nguồn tài liệu được cung cấp.

QUY TẮC:
1. Chỉ trả lời dựa trên thông tin trong nguồn. Nếu không tìm thấy, nói rõ "Không tìm thấy thông tin trong tài liệu".
2. Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc (dùng heading, bullet points, bảng markdown nếu cần).
3. Nếu câu hỏi mơ hồ, hỏi lại để làm rõ.
4. KHÔNG bịa thông tin không có trong nguồn.
"""

        if num_files > 1:
            prompt += "5. Trích dẫn nguồn bằng [1], [2]... tương ứng với số thứ tự nguồn bên dưới.\n\n"
        else:
            prompt += "5. KHÔNG ghi số trích dẫn [1], [2]... vì chỉ có một tài liệu duy nhất.\n\n"

        # Add source documents grouped by file
        prompt += "NGUỒN TÀI LIỆU:\n"
        for i, (fname, fchunks) in enumerate(file_chunks.items()):
            prompt += f"\n[{i+1}] {fname}:\n"
            for chunk in fchunks:
                prompt += f"{chunk}\n"

        # Add chat history (last 5 turns)
        if chat_history:
            prompt += "\nLỊCH SỬ CHAT:\n"
            for turn in chat_history[-5:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role == "user":
                    prompt += f"Người dùng: {content}\n"
                else:
                    prompt += f"Trợ lý: {content}\n"

        prompt += f"\nCÂU HỎI: {question}\n"
        if num_files > 1:
            prompt += "\nTRẢ LỜI (trích dẫn nguồn [1], [2]... nếu có nhiều tài liệu):\n"
        else:
            prompt += "\nTRẢ LỜI:\n"

        return prompt

    # ========================================================================
    # Status & Management
    # ========================================================================

    async def get_status(self) -> Dict[str, Any]:
        """Get indexing status and stats."""
        await self._ensure_table()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            total_chunks = await conn.fetchval("SELECT COUNT(*) FROM document_chunks;")
            total_files = await conn.fetchval("SELECT COUNT(DISTINCT file_id) FROM document_chunks;")

            return {
                "status": "ready",
                "total_chunks": total_chunks,
                "total_files": total_files,
                "vector_db": "pgvector (PostgreSQL Docker)",
            }

    async def is_file_indexed(self, file_id: str) -> Dict[str, Any]:
        """Check if a file is already indexed."""
        await self._ensure_table()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM document_chunks WHERE file_id = $1", file_id
            )
            return {"indexed": count > 0, "chunks": count, "file_id": file_id}

    async def delete_file(self, file_id: str) -> Dict[str, Any]:
        """Delete all chunks for a file."""
        await self._ensure_table()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM document_chunks WHERE file_id = $1", file_id)
            deleted = int(result.split()[-1]) if result else 0
            return {"success": True, "file_id": file_id, "deleted_chunks": deleted}

    async def clear_all(self) -> Dict[str, Any]:
        """Clear all indexed data."""
        await self._ensure_table()
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("TRUNCATE TABLE document_chunks;")
            return {"success": True, "message": "All data cleared"}


# Singleton instance
_rag_service = None

def get_rag_service() -> RAGService:
    """Get the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
