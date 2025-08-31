"""
Create required indexes for conversation_chunks_hybrid collection
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from pymilvus import connections, Collection


def main():
    load_dotenv()

    try:
        print("🔧 Creating required indexes...")

        # Connect
        connections.connect(
            alias="default",
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
        )
        print("✅ Connected to Zilliz")

        # Get collection
        col = Collection("conversation_chunks_hybrid")
        print("✅ Got collection")

        # Create dense vector index
        print("🔧 Creating dense_vector index...")
        dense_index_params = {"index_type": "FLAT", "metric_type": "IP"}
        col.create_index(field_name="dense_vector", index_params=dense_index_params)
        print("✅ Created dense_vector index")

        # Create sparse vector index
        print("🔧 Creating sparse_vector index...")
        sparse_index_params = {
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "IP",
        }
        col.create_index(field_name="sparse_vector", index_params=sparse_index_params)
        print("✅ Created sparse_vector index")

        # Load collection
        print("🔄 Loading collection...")
        col.load()
        print("✅ Collection loaded successfully")

        # Verify indexes
        print("\n🎯 Verifying indexes:")
        indexes = col.indexes
        for index in indexes:
            # Use available attributes (field_name should exist)
            try:
                print(f"✅ Index: {index.field_name}")
            except AttributeError:
                print(f"✅ Index created: {index}")

        # Check collection stats
        entities = col.num_entities
        print(f"\n📊 Collection stats: {entities} entities")

        print("\n🎉 Index creation completed successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
