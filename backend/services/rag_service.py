"""
RAG Service — Core RAG orchestration (pgvector + psycopg2)
Handles document indexing (parse → chunk → embed → PostgreSQL pgvector)
and query pipeline (embed query → similarity search → LLM generate).
Uses PostgreSQL + pgvector via psycopg2 (sync driver wrapped for async).
Note: asyncpg is incompatible with PG17 on Windows, so we use psycopg2.
"""

import os
import re
import time
import asyncio
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # Load .env vars so os.getenv() works

import psycopg2
import psycopg2.pool
import psycopg2.extras

from backend.services.document_parser import DocumentParser
from backend.services.text_chunker import TextChunker
from backend.services.embedding_service import EmbeddingService


# ============================================================================
# Psycopg2 async adapter — mimics asyncpg pool/connection interface
# ============================================================================

class _Psycopg2Conn:
    """Wraps a psycopg2 connection to provide async fetch/execute/fetchval."""

    def __init__(self, conn):
        self._conn = conn

    async def execute(self, query, *args):
        """Execute a query (no return)."""
        sql, params = _convert_query(query, args)
        def _run():
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
            self._conn.commit()
        await asyncio.to_thread(_run)

    async def fetch(self, query, *args):
        """Fetch all rows as list of dict-like objects."""
        sql, params = _convert_query(query, args)
        def _run():
            with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return cur.fetchall()
        return await asyncio.to_thread(_run)

    async def fetchval(self, query, *args):
        """Fetch single value."""
        sql, params = _convert_query(query, args)
        def _run():
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return row[0] if row else None
        return await asyncio.to_thread(_run)


class _Psycopg2Pool:
    """Wraps psycopg2 SimpleConnectionPool with asyncpg-like interface."""

    def __init__(self, dsn, min_size=1, max_size=5):
        self._pool = psycopg2.pool.ThreadedConnectionPool(min_size, max_size, dsn)

    @asynccontextmanager
    async def acquire(self):
        conn = self._pool.getconn()
        try:
            yield _Psycopg2Conn(conn)
        finally:
            self._pool.putconn(conn)

    async def close(self):
        self._pool.closeall()


def _convert_query(query, args):
    """Convert asyncpg-style $1, $2 placeholders to psycopg2 %(name)s style.
    
    asyncpg uses $1, $2 etc where the same $N can appear multiple times.
    psycopg2's %s is positional (each %s consumes next arg), so repeated $1 breaks.
    Solution: use %(p1)s named params with a dict.
    """
    if not args:
        return query, None
    # Replace $N with %(pN)s — handles repeated references correctly
    converted = re.sub(r'\$(\d+)', r'%(p\1)s', query)
    params = {f'p{i+1}': arg for i, arg in enumerate(args)}
    return converted, params


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
        """Get or create psycopg2 connection pool (async wrapper)."""
        if self._pool is None:
            self._pool = _Psycopg2Pool(self._db_url, min_size=1, max_size=5)
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

        # 3. Build source references (deduplicated by file) — filter by relevance
        MIN_RELEVANCE = 0.35
        sources = []
        chunks = []
        metadatas = []
        seen_files = {}  # file_id -> citation index
        for i, row in enumerate(results):
            similarity = float(row["similarity"])
            if similarity < MIN_RELEVANCE:
                continue  # Skip low-relevance chunks
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
                    "relevance": round(similarity, 3),
                    "chunks_used": 1,
                })

        # If no chunks pass relevance filter, respond as general assistant
        if not chunks:
            general_prompt = f"Bạn là trợ lý AI thân thiện của ADG Knowledge Hub. Trả lời bằng tiếng Việt.\n\nNgười dùng: {question}\nTrợ lý:"
            try:
                answer = self._generate_text(general_prompt)
            except Exception as e:
                answer = f"Lỗi khi tạo câu trả lời: {e}"
            return {
                "answer": answer,
                "citations": [],
                "chunks_used": 0,
                "elapsed_seconds": round(time.time() - start, 2),
            }

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

        # Build sources — filter by minimum relevance
        MIN_RELEVANCE = 0.35  # Skip chunks with low similarity (e.g. "hello")
        sources, chunks, metadatas = [], [], []
        seen_files = {}
        for row in results:
            similarity = float(row["similarity"])
            if similarity < MIN_RELEVANCE:
                continue  # Skip low-relevance chunks
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
                    "relevance": round(similarity, 3),
                    "chunks_used": 1,
                })
        # If no chunks pass relevance filter, respond as general assistant
        if not chunks:
            yield {"type": "meta", "citations": [], "chunks_used": 0}
            # Respond without RAG context — general conversation
            general_prompt = f"Bạn là trợ lý AI thân thiện của ADG Knowledge Hub. Trả lời bằng tiếng Việt.\n\nNgười dùng: {question}\nTrợ lý:"
            full_answer = ""
            try:
                for text_chunk in self._generate_text_stream(general_prompt):
                    full_answer += text_chunk
                    yield {"type": "text", "chunk": text_chunk}
            except Exception as e:
                yield {"type": "text", "chunk": f"\n\nLỗi: {e}"}
            yield {"type": "done", "elapsed_seconds": round(time.time() - start, 2), "full_answer": full_answer}
            return

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
            link = meta.get("web_link", "") if isinstance(meta, dict) else ""
            if fname not in file_chunks:
                file_chunks[fname] = {"link": link, "chunks": []}
            file_chunks[fname]["chunks"].append(chunk)

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
    # Smart RAG — Auto-search Google Drive + On-Demand Index
    # ========================================================================

    def _extract_keywords(self, question: str) -> str:
        """Extract a single concise search query from the user question."""
        try:
            prompt = (
                "Rút trích các từ khóa quan trọng nhất từ câu hỏi sau để làm chuỗi tìm kiếm Google Drive. "
                "Chỉ trả về 2-3 từ khóa quan trọng nhất, giữ lại nguyên văn, ví dụ 'tủ bếp', 'checkin'. "
                "KHÔNG giải thích, KHÔNG dùng dấu phẩy, dùng khoảng trắng.\n"
                f"Câu hỏi: {question}\n"
                "Từ khóa:"
            )
            result = self._generate_text(prompt)
            if result and len(result) < 50:
                return result.strip()
        except Exception:
            pass
            
        # Fallback
        stop_words = {"tôi", "muốn", "tìm", "hiểu", "về", "cho", "là", "có", "và", 
                      "của", "các", "những", "này", "một", "được", "trong", "hay",
                      "gì", "nào", "như", "thế", "bạn", "hãy", "xin", "ơi", "nhé",
                      "không", "cần", "biết", "học", "hỏi", "thì", "sao"}
        words = [w for w in question.lower().split() if w not in stop_words and len(w) > 1]
        return " ".join(words[-3:]) if words else question

    async def _search_drive_for_query(self, question: str, max_files: int = 5) -> List[Dict]:
        """Search Google Drive for files relevant to the question."""
        from backend.services.gdrive_service import GoogleDriveService

        search_query = self._extract_keywords(question)
        root_folder_id = os.getenv("GDRIVE_ROOT_FOLDER_ID")
        
        all_files = []
        seen_ids = set()
        
        sa_file = os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE", "adg-kms-3eeb5484a2c8.json")
        gdrive = GoogleDriveService.from_service_account(sa_file)
        
        # Strategy 1: Search using the combined precise keyword phrase
        try:
            files = await asyncio.to_thread(
                gdrive.search_files, search_query, max_results=10, root_folder_id=None
            )
            for f in files:
                fid = f.get("id", "")
                if fid and fid not in seen_ids:
                    mime = f.get("mimeType", "")
                    if mime != "application/vnd.google-apps.folder" and self._parser.is_supported(f.get("name", ""), mime):
                        seen_ids.add(fid)
                        all_files.append(f)
        except Exception as e:
            import logging
            logging.getLogger("rag").warning(f"Drive search failed: {e}")
            
        # Strategy 2: If no results, try splitting into individual words and searching (fallback)
        if not all_files and " " in search_query:
            words = search_query.split()
            longest_word = max(words, key=len)
            if len(longest_word) > 4:
                try:
                    files = await asyncio.to_thread(
                        gdrive.search_files, longest_word, max_results=5, root_folder_id=None
                    )
                    for f in files:
                        fid = f.get("id", "")
                        if fid and fid not in seen_ids:
                            mime = f.get("mimeType", "")
                            if mime != "application/vnd.google-apps.folder" and self._parser.is_supported(f.get("name", ""), mime):
                                seen_ids.add(fid)
                                all_files.append(f)
                except Exception:
                    pass
        
        return all_files[:max_files]

    async def _download_and_parse_file(self, file_info: Dict) -> Optional[str]:
        """Download a file from Google Drive and parse it into text."""
        from backend.api.v1.documents import get_gdrive_service
        import io
        from googleapiclient.http import MediaIoBaseDownload

        try:
            gdrive = get_gdrive_service()
            service = gdrive.service
            file_id = file_info["id"]
            mime_type = file_info.get("mimeType", "")
            file_name = file_info.get("name", "file")

            if mime_type == "application/vnd.google-apps.document":
                request = service.files().export(fileId=file_id, mimeType="text/plain")
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                request = service.files().export(fileId=file_id, mimeType="text/csv")
            else:
                request = service.files().get_media(fileId=file_id)

            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            content = fh.getvalue()
            text = await asyncio.to_thread(self._parser.parse_bytes, content, file_name, mime_type)
            return text
        except Exception as e:
            import logging
            logging.getLogger("rag").warning(f"Failed to download/parse {file_info.get('name')}: {e}")
            return None

    async def smart_query_stream(
        self,
        question: str,
        chat_history: List[Dict] = None,
        file_ids: List[str] = None,
        folder_ids: List[str] = None,
    ):
        """
        Smart RAG query with streaming.
        
        If file_ids or folder_ids are specified, behaves like regular query_stream().
        Otherwise, uses hybrid approach:
        1. Try pgvector search first
        2. If no good results, auto-search Google Drive
        3. Download + parse files on-the-fly
        4. Generate answer from parsed content
        5. Auto-index discovered files in background
        """
        import time as _time
        import json as _json

        # If user specified specific sources, use the regular flow
        if file_ids or folder_ids:
            async for event in self.query_stream(question, chat_history, file_ids, folder_ids):
                yield event
            return

        start = _time.time()
        await self._ensure_table()

        # === ALWAYS use Google Drive search (pgvector cache disabled for now) ===
        import logging
        _log = logging.getLogger("rag")
        _log.info(f"[SMART-RAG] Starting Drive search for: {question}")

        # === Step 2: No good pgvector results — Search Google Drive ===
        yield {"type": "status", "message": "🔍 Đang tìm tài liệu liên quan trên Google Drive..."}

        drive_files = await self._search_drive_for_query(question, max_files=3)

        if not drive_files:
            # No files found on Drive either — general assistant mode
            yield {"type": "meta", "citations": [], "chunks_used": 0}
            yield {"type": "status", "message": "📭 Không tìm thấy tài liệu liên quan trên Drive"}
            
            general_prompt = (
                "Bạn là trợ lý AI của ADG Knowledge Hub. "
                "Hệ thống TỰ ĐỘNG TÌM KIẾM tài liệu trên Google Drive nhưng KHÔNG TÌM THẤY file nào khớp với truy vấn của người dùng. "
                "Hãy thông báo lịch sự rằng không tìm thấy tài liệu phù hợp để tham khảo (KHÔNG bịa ra thư mục, tên file hay quy trình không có). "
                "Trả lời bằng tiếng Việt.\n\n"
                f"Người dùng: {question}\nTrợ lý:"
            )
            full_answer = ""
            try:
                for text_chunk in self._generate_text_stream(general_prompt):
                    full_answer += text_chunk
                    yield {"type": "text", "chunk": text_chunk}
            except Exception as e:
                yield {"type": "text", "chunk": f"\n\nLỗi: {e}"}
            yield {"type": "done", "elapsed_seconds": round(_time.time() - start, 2), "full_answer": full_answer}
            return

        # === Step 3: Download + Parse found files ===
        file_names = [f.get("name", "") for f in drive_files[:3]]
        yield {"type": "status", "message": f"📄 Đang đọc {len(file_names)} tài liệu: {', '.join(file_names[:3])}..."}

        sources = []
        all_text_parts = []
        files_to_index = []  # For background indexing

        for f in drive_files[:3]:
            text = await self._download_and_parse_file(f)
            if text and text.strip():
                fname = f.get("name", "Unknown")
                fid = f.get("id", "")
                folder_path = f.get("path", "")
                
                # Truncate text to avoid hitting token limits
                max_chars = 8000
                truncated = text[:max_chars] + "..." if len(text) > max_chars else text
                
                sources.append({
                    "number": len(sources) + 1,
                    "file_name": fname,
                    "file_id": fid,
                    "folder_path": folder_path,
                    "web_link": f.get("webViewLink", ""),
                    "chunk_text": truncated[:200] + "..." if len(truncated) > 200 else truncated,
                    "relevance": 0.8,  # Placeholder since no vector comparison
                    "chunks_used": 1,
                })
                all_text_parts.append({"file_name": fname, "text": truncated, "web_link": f.get("webViewLink", ""), "folder_path": folder_path})
                files_to_index.append({
                    "file_id": fid,
                    "file_name": fname,
                    "mime_type": f.get("mimeType"),
                    "folder_id": f.get("parents", [None])[0] if f.get("parents") else None,
                    "folder_path": folder_path,
                })

        if not all_text_parts:
            yield {"type": "meta", "citations": [], "chunks_used": 0}
            yield {"type": "status", "message": "⚠️ Tìm thấy file nhưng không đọc được nội dung"}
            general_prompt = f"Bạn là trợ lý AI thân thiện của ADG Knowledge Hub. Trả lời bằng tiếng Việt.\n\nNgười dùng: {question}\nTrợ lý:"
            full_answer = ""
            try:
                for text_chunk in self._generate_text_stream(general_prompt):
                    full_answer += text_chunk
                    yield {"type": "text", "chunk": text_chunk}
            except Exception as e:
                yield {"type": "text", "chunk": f"\n\nLỗi: {e}"}
            yield {"type": "done", "elapsed_seconds": round(_time.time() - start, 2), "full_answer": full_answer}
            return

        # === Step 4: Build prompt with parsed file content and generate ===
        yield {"type": "meta", "citations": sources, "chunks_used": len(all_text_parts)}

        # Build the prompt with actual file content
        prompt = """Bạn là trợ lý AI của ADG Knowledge Hub. Trả lời câu hỏi DỰA TRÊN các nguồn tài liệu được cung cấp.

QUY TẮC BẮT BUỘC:
1. Trả lời bằng tiếng Việt, rõ ràng, có cấu trúc (dùng heading, bullet points nếu cần).
2. Nếu người dùng hỏi file NẰM Ở ĐÂU hoặc FOLDER NÀO, hãy trả lời bằng thông tin "Đường dẫn thư mục" và "Link tài liệu gốc" được cung cấp bên dưới.
3. LUÔN hiển thị link tài liệu gốc dưới dạng markdown clickable: [Tên file](Link tài liệu gốc). KHÔNG lấy URL bên trong nội dung file để giả làm link tài liệu.
4. KHÔNG bịa ra thư mục, tên file, hoặc thông tin không có trong nguồn.
"""
        num_files = len(all_text_parts)
        if num_files > 1:
            prompt += "5. Trích dẫn nguồn bằng [1], [2]... tương ứng với số thứ tự nguồn bên dưới.\n\n"
        else:
            prompt += "5. KHÔNG ghi số trích dẫn vì chỉ có một tài liệu duy nhất.\n\n"

        prompt += "NGUỒN TÀI LIỆU:\n"
        for i, part in enumerate(all_text_parts):
            import logging
            logging.getLogger("rag").info(f"[SMART-RAG] Source {i+1}: file={part['file_name']}, path={part.get('folder_path','')}, link={part.get('web_link','')[:80]}")
            link_str = f"\nLink tài liệu gốc: {part.get('web_link', '')}" if part.get('web_link') else ""
            path_str = f"\nĐường dẫn thư mục: {part.get('folder_path', '')}" if part.get('folder_path') else ""
            prompt += f"\n[{i + 1}] Tên file: {part['file_name']}{path_str}{link_str}\nNội dung:\n{part['text']}\n"

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

        # Stream the answer
        full_answer = ""
        try:
            for text_chunk in self._generate_text_stream(prompt):
                full_answer += text_chunk
                yield {"type": "text", "chunk": text_chunk}
        except Exception as e:
            yield {"type": "text", "chunk": f"\n\nLỗi: {e}"}

        elapsed = _time.time() - start
        yield {"type": "done", "elapsed_seconds": round(elapsed, 2), "full_answer": full_answer}

        # === Step 5: Background auto-index discovered files ===
        for fi in files_to_index:
            try:
                await self.index_file_from_drive(
                    file_id=fi["file_id"],
                    file_name=fi["file_name"],
                    mime_type=fi.get("mime_type"),
                    folder_id=fi.get("folder_id"),
                    folder_path=fi.get("folder_path"),
                )
            except Exception:
                pass  # Don't break if indexing fails

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
