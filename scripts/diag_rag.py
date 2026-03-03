"""Quick diagnostic to test the RAG pipeline end-to-end."""
import os, sys, asyncio
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv()

async def main():
    print("=" * 60)
    print("RAG Pipeline Diagnostic")
    print("=" * 60)
    
    # 1. Test embedding
    print("\n[1] Testing embedding API...")
    try:
        from backend.services.embedding_service import EmbeddingService
        embed = EmbeddingService()
        vec = embed.embed_text("test question")
        print(f"  ✅ Embedding OK — {len(vec)} dimensions")
    except Exception as e:
        print(f"  ❌ Embedding FAILED: {e}")
        return
    
    # 2. Test pgvector connection
    print("\n[2] Testing pgvector connection...")
    try:
        import asyncpg
        db_url = os.getenv("RAG_DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/adg_vectors")
        conn = await asyncpg.connect(db_url)
        
        # Check table exists
        exists = await conn.fetchval("""
            SELECT EXISTS (SELECT FROM pg_tables WHERE tablename = 'document_chunks');
        """)
        print(f"  Table exists: {exists}")
        
        if exists:
            count = await conn.fetchval("SELECT COUNT(*) FROM document_chunks")
            print(f"  Total chunks: {count}")
            
            # Check column dimensions
            col_info = await conn.fetchval("""
                SELECT atttypmod FROM pg_attribute 
                WHERE attrelid = 'document_chunks'::regclass 
                AND attname = 'embedding'
            """)
            print(f"  Embedding column typmod: {col_info}")
        
        await conn.close()
        print("  ✅ DB connection OK")
    except Exception as e:
        print(f"  ❌ DB FAILED: {e}")
        return
    
    # 3. Test insert with correct dimensions
    print("\n[3] Testing vector insert...")
    try:
        conn = await asyncpg.connect(db_url)
        embedding_str = "[" + ",".join(str(x) for x in vec) + "]"
        
        # Try insert test chunk
        await conn.execute("""
            INSERT INTO document_chunks 
            (file_id, file_name, chunk_index, chunk_text, token_count, embedding)
            VALUES ('_test_diag', '_test_diag.txt', 0, 'test text', 5, $1::vector)
            ON CONFLICT (file_id, chunk_index) DO UPDATE SET embedding = $1::vector
        """, embedding_str)
        
        # Verify inserted
        test_count = await conn.fetchval(
            "SELECT COUNT(*) FROM document_chunks WHERE file_id = '_test_diag'"
        )
        print(f"  Insert test: {test_count} chunk(s)")
        
        # Test similarity search
        results = await conn.fetch("""
            SELECT file_id, chunk_text, 1 - (embedding <=> $1::vector) AS similarity
            FROM document_chunks
            ORDER BY embedding <=> $1::vector
            LIMIT 3
        """, embedding_str)
        print(f"  Query test: {len(results)} results")
        for r in results:
            print(f"    - {r['file_id']}: sim={r['similarity']:.3f}")
        
        # Cleanup
        await conn.execute("DELETE FROM document_chunks WHERE file_id = '_test_diag'")
        await conn.close()
        print("  ✅ Insert + Query OK")
    except Exception as e:
        print(f"  ❌ Insert FAILED: {e}")
        return
    
    # 4. Test full index from drive
    print("\n[4] Testing full file indexing...")
    try:
        from backend.services.rag_service import get_rag_service
        rag = get_rag_service()
        # Check status
        status = await rag.get_status()
        print(f"  Status: {status}")
    except Exception as e:
        print(f"  ❌ Service FAILED: {e}")
    
    print("\n" + "=" * 60)
    print("Diagnostic complete!")

asyncio.run(main())
