"""
Ingest a small sample document to the Milvus collection using ConversationVectorizer.
This will help fit the sparse TF-IDF vectorizer (sparse_vector) and ensure num_entities>0.

Usage:
  & .venv/Scripts/Activate.ps1
  python ./scripts/ingest_sample.py

Note: This script will insert one sample conversation chunk into the collection.
Ensure the collection exists and indexes are created (or create them after insertion).
"""

import os
import sys
from pathlib import Path
import traceback

# Add src to path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from core.conversation_vectorizer import ConversationVectorizer

SAMPLE_TEXT = "これはテスト用のサンプルテキストです。検索とスパースベクトルのフィッティングを行います。"


def main():
    uri = os.getenv("ZILLIZ_URI")
    token = os.getenv("ZILLIZ_TOKEN")
    if not uri or not token:
        print("⚠️ ZILLIZ_URI or ZILLIZ_TOKEN not set in environment")
        return

    try:
        print("Initializing ConversationVectorizer...", end=" ")
        cv = ConversationVectorizer(uri, token)
        print("✅ Initialized")
    except Exception:
        print("❌ Failed to initialize ConversationVectorizer")
        traceback.print_exc()
        return

    try:
        print("Processing sample monologue and inserting...", end=" ")
        # process_monologue should chunk, vectorize, and insert to Milvus
        # Signature: process_monologue(text: str, file_name: str)
        chunks = cv.process_monologue(SAMPLE_TEXT, "sample.txt")
        # Optionally flush/confirm entities in collection
        try:
            stats = cv.get_stats()
            print("\nInserted chunks:", len(chunks))
            print("Collection stats after insert:")
            print(stats.get("zilliz_stats", {}))
        except Exception:
            pass
        print("✅ Inserted sample")
    except Exception:
        print("❌ Failed to insert sample")
        traceback.print_exc()

    print("Done")


if __name__ == "__main__":
    main()
