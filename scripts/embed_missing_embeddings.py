"""Embed missing transcripts based on DynamoDB embedding flag.

Steps:
 1. Scan DynamoDB table for items where embedding flag is false / 0 / missing.
 2. For each item, attempt to locate its transcript JSON in S3 (several filename patterns tried).
 3. Extract text and feed into ConversationVectorizer to generate / insert vectors into Zilliz Cloud.
 4. Update DynamoDB embedding flag to true on success.

Environment variables required:
  DYNAMO_TABLE_NAME   DynamoDB table name (required)
  S3_BUCKET_NAME      S3 bucket that stores transcript JSONs (required)
  ZILLIZ_URI          Zilliz (Milvus) cloud endpoint URI (required)
  ZILLIZ_TOKEN        Zilliz token (required)
Optional:
  AWS_REGION          Default: ap-northeast-1
  S3_TRANSCRIPT_PREFIX  Prefix for transcript objects
  CHUNK_SIZE / CHUNK_OVERLAP  Override defaults used by ConversationVectorizer
  FILE_PATTERN        Python format pattern (default: {video_id}_transcription.json)

Usage examples:
  python scripts/embed_missing_embeddings.py
  python scripts/embed_missing_embeddings.py --limit 20 --dry-run --verbose
  python scripts/embed_missing_embeddings.py --mode before_transcription
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone
from typing import List, Dict, Optional, Iterator

import boto3
from botocore.exceptions import ClientError

try:  # Optional dependency
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:  # pragma: no cover
    pass

# Add src to path
ROOT = os.path.dirname(os.path.dirname(__file__))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from core.conversation_vectorizer import ConversationVectorizer  # type: ignore  # noqa: E402

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description="Embed transcripts for items with embedding flag false in DynamoDB and insert into Zilliz Cloud"
    )
    p.add_argument(
        "--limit", type=int, default=0, help="Max number of items to process (0 = all)"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Do not write to Zilliz or DynamoDB"
    )
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.add_argument(
        "--file-pattern",
        default=os.getenv("FILE_PATTERN", "{video_id}_transcription.json"),
        help="Format pattern for main transcript key (default: {video_id}_transcription.json)",
    )
    p.add_argument(
        "--s3-prefix",
        default=os.getenv("S3_TRANSCRIPT_PREFIX", ""),
        help="Base prefix in S3 where transcripts live",
    )
    p.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Sleep seconds between items to avoid API bursts",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------


def _aws_credentials_kwargs():
    """Return kwargs for boto3 client/resource with explicit credentials if provided.

    Falls back to normal provider chain if keys are absent (do not raise).
    """
    region = (
        os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-northeast-1"
    )
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")
    kwargs: dict = {"region_name": region}
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return kwargs


def build_dynamodb():
    return boto3.resource("dynamodb", **_aws_credentials_kwargs())


def scan_unembedded(table, limit: int = 0) -> List[Dict]:
    """Scan for items needing embedding.

    Primary attempt: embedding == false (bool)
    Fallback: embedding == 0 (number) or attribute_not_exists(embedding)
    Warning: This is a full table scan; consider a GSI for production scale.
    """
    items: List[Dict] = []
    start_key = None
    # Pass 1: embedding == false
    while True:
        params = {
            "FilterExpression": "attribute_exists(embedding) AND embedding = :false",
            "ExpressionAttributeValues": {":false": False},
        }
        if start_key:
            params["ExclusiveStartKey"] = start_key
        resp = table.scan(**params)
        batch = resp.get("Items", [])
        items.extend(batch)
        if limit and len(items) >= limit:
            return items[:limit]
        start_key = resp.get("LastEvaluatedKey")
        if not start_key:
            break
    # If nothing found, fallback to numeric 0 or missing
    if not items:
        start_key = None
        while True:
            params = {
                "FilterExpression": "(attribute_exists(embedding) AND embedding = :zero) OR attribute_not_exists(embedding)",
                "ExpressionAttributeValues": {":zero": 0},
            }
            if start_key:
                params["ExclusiveStartKey"] = start_key
            resp = table.scan(**params)
            batch = resp.get("Items", [])
            items.extend(batch)
            if limit and len(items) >= limit:
                return items[:limit]
            start_key = resp.get("LastEvaluatedKey")
            if not start_key:
                break
    return items if not limit else items[:limit]


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------


def guess_transcript_keys(video_id: str, file_pattern: str, prefix: str) -> List[str]:
    """Return ONLY the canonical S3 key for the transcript.

    Requirement: The transcript object key format is strictly
        {video_id}_transcription.json (or provided pattern)

    So we no longer try legacy variants or fallbacks. This keeps the
    embedding process deterministic and avoids accidental mixing of
    intermediate / legacy file forms.
    """
    base = file_pattern.format(video_id=video_id)
    key = f"{prefix}{base}" if prefix and not base.startswith(prefix) else base
    return [key]


def fetch_json_from_s3(s3_client, bucket: str, keys: List[str]) -> Optional[Dict]:
    for k in keys:
        try:
            obj = s3_client.get_object(Bucket=bucket, Key=k)
            data = obj["Body"].read().decode("utf-8")
            return json.loads(data)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                continue
            print(f"⚠️  S3 error for key={k}: {e}")
        except Exception as e:  # noqa
            print(f"⚠️  Unexpected error reading {k}: {e}")
    return None


# ---------------------------------------------------------------------------
# Transcript text extraction (flexible for multiple shapes)
# ---------------------------------------------------------------------------


def extract_text(doc: Dict) -> Optional[str]:
    """Return ONLY Gladia style full_transcript.

    Requirement: Embedding target must be strictly
    doc["result"]["transcription"]["full_transcript"].
    If absent or empty -> skip (return None). No fallbacks.
    """
    if not doc:
        return None
    result = doc.get("result") if isinstance(doc, dict) else None
    if not isinstance(result, dict):
        return None
    transcription = result.get("transcription") if isinstance(result, dict) else None
    if not isinstance(transcription, dict):
        return None
    full = transcription.get("full_transcript")
    if isinstance(full, str) and full.strip():
        return full.strip()
    return None


# ---------------------------------------------------------------------------
# DynamoDB update
# ---------------------------------------------------------------------------


def update_embedding_flag(table, video_id: str, dry_run: bool):
    if dry_run:
        print(f"[DRY-RUN] Would set embedding=true for video_id={video_id}")
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        table.update_item(
            Key={"video_id": video_id},
            UpdateExpression="SET #e = :true, #ua = :u",
            ExpressionAttributeNames={"#e": "embedding", "#ua": "updated_at"},
            ExpressionAttributeValues={":true": True, ":u": now_iso},
        )
    except ClientError as e:
        print(f"❌ DynamoDB update failed for {video_id}: {e}")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main():
    args = parse_args()

    bucket = os.getenv("S3_BUCKET_NAME")
    table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE")
    zilliz_uri = os.getenv("ZILLIZ_URI")
    zilliz_token = os.getenv("ZILLIZ_TOKEN")

    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME not set")
    if not table_name:
        raise RuntimeError("DYNAMO_TABLE_NAME not set")
    if not zilliz_uri or not zilliz_token:
        raise RuntimeError("ZILLIZ_URI / ZILLIZ_TOKEN not set")

    print(
        f"▶ Embedding job start bucket={bucket} table={table_name} limit={args.limit or 'ALL'} dry_run={args.dry_run}"
    )

    dynamodb = build_dynamodb()
    table = dynamodb.Table(table_name)
    s3 = boto3.client("s3", **_aws_credentials_kwargs())

    targets = scan_unembedded(table, limit=args.limit)
    print(f"Found {len(targets)} target items (embedding false or missing)")
    if not targets:
        print("No targets. Exit.")
        return

    vectorizer = ConversationVectorizer(
        zilliz_uri=zilliz_uri,
        zilliz_token=zilliz_token,
        chunk_size=int(os.getenv("CHUNK_SIZE", "300")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
    )

    processed = skipped = errors = 0

    for item in targets:
        video_id = item.get("video_id")
        if not video_id:
            print("⚠️  Missing video_id; skipping item")
            skipped += 1
            continue

        print(f"\n▶ Processing video_id={video_id}")
        keys = guess_transcript_keys(video_id, args.file_pattern, args.s3_prefix)
        if args.verbose:
            print("  Candidate keys:", keys)
        doc = fetch_json_from_s3(s3, bucket, keys)
        if not doc:
            print("  ⚠️  Transcript JSON not found; skip")
            skipped += 1
            continue
        text = extract_text(doc)
        if not text or not text.strip():
            print("  ⚠️  No usable text extracted; skip")
            skipped += 1
            continue

        try:
            if args.dry_run:
                print(f"  [DRY-RUN] Would embed {len(text)} chars")
            else:
                # Use a consistent pseudo filename for tracking
                vectorizer.process_monologue(text, f"{video_id}_transcription.json")
            update_embedding_flag(table, video_id, args.dry_run)
            processed += 1
        except Exception as e:  # noqa
            print(f"  ❌ Embedding failed: {e}")
            errors += 1
            continue
        time.sleep(args.sleep)

    print("\n===== Summary =====")
    print(f"Processed: {processed}")
    print(f"Skipped  : {skipped}")
    print(f"Errors   : {errors}")
    print(f"Dry-run  : {args.dry_run}")
    print("===================")


if __name__ == "__main__":  # pragma: no cover
    main()
