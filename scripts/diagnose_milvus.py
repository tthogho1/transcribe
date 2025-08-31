"""
Milvus / Zilliz diagnostic script

Usage:
  & .\.venv\Scripts\Activate.ps1
  python .\scripts\diagnose_milvus.py

What it does:
- Loads environment variables (.env if available)
- Connects to Zilliz/Milvus using ZILLIZ_URI and ZILLIZ_TOKEN
- Lists collections, checks the target collection (default: conversation_chunks_hybrid)
- Prints schema / basic metadata (num_entities, is_loaded)
- Attempts to describe collection via utility.describe_collection (if available)
- Tries to call load() and reports errors
- If a dense vector field exists, attempts a tiny test search and prints any error

This script is diagnostic only and will not create indexes or write data.
"""

import os
import sys
import traceback
import random
import json

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from pymilvus import connections, Collection

# Some optional imports that may or may not exist in the env
try:
    from pymilvus import utility
except Exception:
    utility = None

COLLECTION_NAME = os.getenv("ZILLIZ_COLLECTION_NAME", "conversation_chunks_hybrid")
URI = os.getenv("ZILLIZ_URI")
TOKEN = os.getenv("ZILLIZ_TOKEN")
ALIAS = "default"


def safe_print(title, obj):
    print("\n---- {} ----".format(title))
    try:
        if isinstance(obj, (dict, list)):
            print(json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            print(obj)
    except Exception:
        try:
            print(str(obj))
        except Exception:
            print(repr(obj))


def main():
    print("Milvus diagnostic script")
    print(f"Target collection: {COLLECTION_NAME}")

    if not URI:
        print("⚠️ ZILLIZ_URI is not set in the environment")
    if not TOKEN:
        print("⚠️ ZILLIZ_TOKEN is not set in the environment")

    try:
        print("Connecting to Zilliz/Milvus...", end=" ")
        connections.connect(alias=ALIAS, uri=URI, token=TOKEN)
        print("✅ Connected")
    except Exception as e:
        print("❌ Connection failed:")
        traceback.print_exc()
        sys.exit(2)

    # List connections (if available)
    try:
        conns = connections.list_connections()
        safe_print("Connections", conns)
    except Exception as e:
        print("Could not list connections:", e)

    # List collections via utility if possible, else try other ways
    try:
        if utility:
            cols = utility.list_collections()
        else:
            # Fallback: try constructing a Collection and catch
            cols = []
        safe_print("Collections (reported)", cols)
    except Exception as e:
        print("Could not list collections via utility:")
        traceback.print_exc()

    # Inspect target collection
    try:
        print(f"Inspecting collection: {COLLECTION_NAME}")
        if utility and COLLECTION_NAME not in utility.list_collections():
            print(f"⚠️ Collection '{COLLECTION_NAME}' not found in server")
        col = Collection(COLLECTION_NAME)

        # Basic introspection
        try:
            is_loaded = getattr(col, "is_loaded", None)
            print("is_loaded:", is_loaded)
        except Exception as e:
            print("Could not get is_loaded:", e)

        # num_entities
        try:
            num = col.num_entities
            print("num_entities:", num)
        except Exception:
            try:
                num = col.num_entities()
                print("num_entities():", num)
            except Exception as e:
                print("Could not get num_entities:", e)

        # Schema introspection
        try:
            schema = getattr(col, "schema", None)
            if schema:
                # Try to print field info
                fields = getattr(schema, "fields", None)
                if fields:
                    out = []
                    for f in fields:
                        try:
                            # Support different field object shapes
                            fname = getattr(f, "name", None) or f.get("name")
                            ftype = getattr(f, "dtype", None) or f.get("type")
                            out.append({"name": fname, "dtype": str(ftype)})
                        except Exception:
                            out.append(str(f))
                    safe_print("Schema fields", out)
                else:
                    safe_print("Schema", schema)
            else:
                # Try to fetch description via utility
                if utility:
                    try:
                        desc = utility.describe_collection(COLLECTION_NAME)
                        safe_print("describe_collection", desc)
                    except Exception as e:
                        print("utility.describe_collection failed:", e)
                else:
                    print("No schema available and utility is not present")
        except Exception as e:
            print("Schema introspection failed:")
            traceback.print_exc()

        # Index information (best-effort)
        try:
            if utility:
                try:
                    idxs = utility.list_indexes(COLLECTION_NAME)
                    safe_print("Indexes (utility.list_indexes)", idxs)
                except Exception:
                    # older/newer pymilvus might not have list_indexes
                    try:
                        idxs = utility.get_index_info(COLLECTION_NAME)
                        safe_print("Indexes (utility.get_index_info)", idxs)
                    except Exception as e:
                        print("Could not retrieve index info via utility:", e)
            else:
                # Try attribute on Collection (best-effort)
                if hasattr(col, "indexes"):
                    try:
                        safe_print("Collection.indexes", col.indexes)
                    except Exception:
                        print("Collection.indexes exists but could not be read")
        except Exception as e:
            print("Index introspection error:", e)

        # Attempt to load collection
        try:
            print("Attempting to load collection into memory...", end=" ")
            col.load()
            print("✅ load() succeeded")
            try:
                print("is_loaded after load:", col.is_loaded)
            except Exception:
                pass
        except Exception as e:
            print("❌ collection.load() error:")
            traceback.print_exc()

        # If dense_vector exists, attempt a tiny test search (safe)
        try:
            # Best-effort find a dense vector field name
            dense_field = None
            fields = []
            try:
                if schema and getattr(schema, "fields", None):
                    fields = schema.fields
                else:
                    # Try describe_collection structure
                    if utility:
                        desc = utility.describe_collection(COLLECTION_NAME)
                        # desc may have 'fields' key
                        fields = (
                            desc.get("fields", []) if isinstance(desc, dict) else []
                        )
            except Exception:
                fields = []

            for f in fields:
                try:
                    fname = getattr(f, "name", None) or f.get("name")
                    if fname == "dense_vector":
                        dense_field = fname
                        break
                except Exception:
                    pass

            if dense_field:
                print(
                    "Found dense vector field 'dense_vector', attempting a small search test..."
                )
                # Create a small random vector (length 768 is common); this is a test and may fail if dim mismatches
                vec = [random.random() for _ in range(768)]
                try:
                    res = col.search(
                        [vec],
                        "dense_vector",
                        {"metric_type": "IP", "params": {"nprobe": 10}},
                        limit=1,
                        output_fields=["text"],
                    )
                    print("Search returned (len):", len(res))
                    try:
                        safe_print("Search sample result", res[0])
                    except Exception:
                        print("Search result printed above or not accessible")
                except Exception as e:
                    print("Test search failed (likely dimension/index issue):")
                    traceback.print_exc()
            else:
                print(
                    "No 'dense_vector' field found in schema (or could not detect). Skipping test search."
                )
        except Exception:
            print("Test search step raised unexpected error:")
            traceback.print_exc()

        print("\nDiagnostic complete.")

    except Exception as e:
        print("Error inspecting collection:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
