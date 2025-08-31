"""
Simple collection loading fix
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    try:
        print("🔧 Loading collection...")

        from pymilvus import connections, Collection

        # Connect
        print("📡 Connecting to Zilliz...")
        uri = os.getenv("ZILLIZ_URI")
        token = os.getenv("ZILLIZ_TOKEN")

        if not uri or not token:
            print("❌ ZILLIZ_URI or ZILLIZ_TOKEN not found in environment")
            return

        connections.connect(alias="default", uri=uri, token=token)
        print("✅ Connected to Zilliz")

        # Load collection
        col = Collection("conversation_chunks_hybrid")
        if not col.is_loaded():
            print("📥 Loading collection...")
            col.load()
            print("✅ Collection loaded")
        else:
            print("✅ Collection already loaded")

        print("🎉 Collection fix completed!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
