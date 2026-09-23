import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

conn = psycopg.connect(os.environ["DATABASE_URL"])

print("=== RAG TABLE ===")

row = conn.execute("""
    SELECT
        EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'rag_documents'
        )
""").fetchone()

print("rag_documents exists:", row[0])

if row[0]:
    row = conn.execute("""
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        WHERE c.relname = 'rag_documents'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
    """).fetchone()

    print("embedding type:", row[0] if row else "not found")

    rows = conn.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'rag_documents'
    """).fetchall()

    print("\n=== INDEXES ===")
    for name, definition in rows:
        print(name)
        print(definition)

    count = conn.execute(
        "SELECT COUNT(*) FROM rag_documents"
    ).fetchone()[0]

    print("\nrows:", count)

conn.close()