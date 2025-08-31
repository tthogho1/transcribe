"""
Fix collection loading and vectorizer fitting
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from flask.cli import load_dotenv
from pymilvus import connections, Collection
from core.conversation_vectorizer import ConversationVectorizer


def main():
    load_dotenv()

    try:
        print("🔧 Fixing collection and vectorizer...")

        # Connect and load collection
        connections.connect(
            alias="default",
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
        )

        col = Collection("conversation_chunks_hybrid")

        # Load collection (newer pymilvus versions don't have is_loaded method)
        try:
            print("📥 Loading collection into memory...")
            col.load()
            print("✅ Collection loaded")
        except Exception as load_err:
            if "already loaded" in str(load_err).lower():
                print("✅ Collection already loaded")
            else:
                print(f"⚠️ Load warning: {load_err}")
                print("✅ Continuing anyway...")

        # Initialize and fit vectorizer with sample data
        print("🤖 Initializing ConversationVectorizer...")
        cv = ConversationVectorizer(os.getenv("ZILLIZ_URI"), os.getenv("ZILLIZ_TOKEN"))

        # Insert a few sample texts to properly fit the sparse vectorizer
        sample_texts = [
            "これはテスト用のサンプルテキストです。検索機能をテストします。",
            "ハイブリッド検索のテストを行います。密ベクトルとスパースベクトルの両方を使用します。",
            "会話データの検索と生成を行うシステムです。",
        ]

        for i, text in enumerate(sample_texts):
            print(f"📝 Processing sample {i+1}/{len(sample_texts)}...")
            cv.process_monologue(text, f"sample_{i+1}.txt")

        print("✅ Vectorizer fitted with sample data")

        # Test search
        print("🔍 Testing search...")
        results = cv.hybrid_search("テスト", limit=2)
        print(f"✅ Search test successful: found {len(results)} results")

        if results:
            print(f"Sample result: {results[0].text[:50]}...")

        print("🎉 Fix completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
