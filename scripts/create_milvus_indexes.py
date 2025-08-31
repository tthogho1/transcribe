"""
Create Milvus indexes for collection fields used by the app.

Usage:
  & .\.venv\Scripts\Activate.ps1
  python .\scripts\create_milvus_indexes.py

This script will:
- Connect to Milvus using ZILLIZ_URI and ZILLIZ_TOKEN
- Check that the target collection exists
- Create a dense index on `dense_vector` if missing
- Create a sparse index on `sparse_vector` if missing
- Load the collection into memory

This script does not insert data.
"""

import os
import sys
import traceback
from pathlib import Path

# Add project src to path for imports if needed
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from pymilvus import connections, utility, Collection

COLLECTION_NAME = os.getenv("ZILLIZ_COLLECTION_NAME", "conversation_chunks_hybrid")
URI = os.getenv("ZILLIZ_URI")
TOKEN = os.getenv("ZILLIZ_TOKEN")
ALIAS = "default"


def main():
    print("Create Milvus indexes script")
    if not URI or not TOKEN:
        print(
            "⚠️ ZILLIZ_URI or ZILLIZ_TOKEN not set in environment. Please set them (or .env) and retry."
        )
        return

    try:
        print("Connecting to Milvus...", end=" ")
        connections.connect(alias=ALIAS, uri=URI, token=TOKEN)
        print("✅ Connected")
    except Exception:
        print("❌ Connection failed")
        traceback.print_exc()
        return

    try:
        cols = utility.list_collections()
        print("Collections:", cols)
    except Exception as e:
        print("Could not list collections:", e)
        cols = None

    if cols is None or COLLECTION_NAME not in cols:
        print(
            f"❌ Collection '{COLLECTION_NAME}' not found on server. Create or import it first."
        )
        return

    col = Collection(COLLECTION_NAME)

    # Helper to check existing indexes
    def has_index(col_name, field):
        try:
            idxs = utility.list_indexes(col_name)
            # list_indexes returns [] or list of index info; check for field name match
            for info in idxs:
                # info may be a dict or an object
                if isinstance(info, dict):
                    if info.get("field_name") == field:
                        return True
                else:
                    # try attribute access
                    try:
                        if getattr(info, "field_name", None) == field:
                            return True
                    except Exception:
                        continue
            return False
        except Exception:
            # Fallback: try get_index_info or similar
            try:
                info = utility.get_index_info(col_name)
                # if we got info, try to find field
                try:
                    for entry in info:
                        if isinstance(entry, dict) and entry.get("field_name") == field:
                            return True
                except Exception:
                    pass
            except Exception:
                pass
            return False

    # Dense index params (adjust nlist if needed)
    dense_index_params = {
        "index_type": "IVF_FLAT",
        "params": {"nlist": 1024},
        "metric_type": "IP",
    }

    # Sparse index params
    sparse_index_params = {"index_type": "SPARSE_INVERTED_INDEX", "params": {}}

    # Create dense index if missing
    try:
        if has_index(COLLECTION_NAME, "dense_vector"):
            print("✅ dense_vector index already exists")
        else:
            print("Creating dense_vector index...", end=" ")
            col.create_index(field_name="dense_vector", index_params=dense_index_params)
            print("✅ Created")
    except Exception:
        print("❌ Failed to create dense_vector index")
        traceback.print_exc()

    # Create sparse index if missing
    try:
        if has_index(COLLECTION_NAME, "sparse_vector"):
            print("✅ sparse_vector index already exists")
        else:
            print("Creating sparse_vector index...", end=" ")
            col.create_index(
                field_name="sparse_vector", index_params=sparse_index_params
            )
            print("✅ Created")
    except Exception:
        print("❌ Failed to create sparse_vector index")
        traceback.print_exc()

    # Load collection into memory
    try:
        print("Loading collection into memory...", end=" ")
        col.load()
        print("✅ Loaded")
    except Exception:
        print("❌ Failed to load collection")
        traceback.print_exc()

    print("Done")


if __name__ == "__main__":
    main()
