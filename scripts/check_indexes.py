"""
Check if indexes are properly created in the collection
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
from pymilvus import connections, Collection, utility


def main():
    load_dotenv()

    try:
        print("🔍 Checking collection indexes...")

        # Connect
        connections.connect(
            alias="default",
            uri=os.getenv("ZILLIZ_URI"),
            token=os.getenv("ZILLIZ_TOKEN"),
        )
        print("✅ Connected to Zilliz")

        # Check if collection exists
        collection_name = "conversation_chunks_hybrid"
        if not utility.has_collection(collection_name):
            print(f"❌ Collection '{collection_name}' does not exist")
            return

        print(f"✅ Collection '{collection_name}' exists")

        # Get collection
        col = Collection(collection_name)

        # Check collection schema
        print("\n📋 Collection Schema:")
        for field in col.schema.fields:
            print(f"  - {field.name}: {field.dtype}")

        # Check indexes
        print("\n🔍 Checking indexes:")
        try:
            indexes = col.indexes
            if not indexes:
                print("❌ No indexes found!")
                return

            for index in indexes:
                print(f"✅ Index found:")
                print(f"  - Field: {index.field_name}")
                print(f"  - Index type: {index.index_type}")
                print(f"  - Params: {index.params}")

        except Exception as e:
            print(f"❌ Error getting indexes: {e}")

        # Check if collection is loaded
        print("\n📥 Collection Load Status:")
        try:
            # Try to get stats (this requires collection to be loaded)
            stats = col.num_entities
            print(f"✅ Collection is loaded (entities: {stats})")
        except Exception as e:
            if "not loaded" in str(e):
                print("❌ Collection is not loaded")
                print("💡 Attempting to load...")
                try:
                    col.load()
                    print("✅ Collection loaded successfully")
                except Exception as load_err:
                    print(f"❌ Failed to load: {load_err}")
            else:
                print(f"⚠️ Unknown status: {e}")

        # Check for required indexes
        print("\n🎯 Required Index Check:")
        required_indexes = ["dense_vector", "sparse_vector"]

        existing_fields = [idx.field_name for idx in col.indexes] if col.indexes else []

        for field in required_indexes:
            if field in existing_fields:
                print(f"✅ {field} index exists")
            else:
                print(f"❌ {field} index MISSING")

        if len(existing_fields) == len(required_indexes):
            print("\n🎉 All required indexes are present!")
        else:
            print("\n⚠️ Some indexes are missing. Creating indexes...")
            create_missing_indexes(col, existing_fields, required_indexes)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


def create_missing_indexes(col, existing_fields, required_indexes):
    """Create missing indexes"""
    try:
        from pymilvus import IndexType

        for field in required_indexes:
            if field not in existing_fields:
                print(f"🔧 Creating index for {field}...")

                if field == "dense_vector":
                    index_params = {"index_type": "FLAT", "metric_type": "IP"}
                elif field == "sparse_vector":
                    index_params = {
                        "index_type": "SPARSE_INVERTED_INDEX",
                        "metric_type": "IP",
                    }
                else:
                    continue

                col.create_index(field_name=field, index_params=index_params)
                print(f"✅ Created {field} index")

        print("🔄 Loading collection...")
        col.load()
        print("✅ Collection loaded with new indexes")

    except Exception as e:
        print(f"❌ Error creating indexes: {e}")


if __name__ == "__main__":
    main()
