import os
import sys
import argparse
from typing import Iterator

import boto3
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv, find_dotenv  # type: ignore

    load_dotenv(find_dotenv(usecwd=True))
except Exception:
    # dotenv が無くても続行（環境変数直接設定前提）
    pass


def build_s3_client():
    """環境変数から明示的にクライアントを生成。資格情報未設定なら通常の探索順序にフォールバック。"""
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    session_token = os.getenv("AWS_SESSION_TOKEN")
    region = os.getenv("AWS_REGION", "ap-northeast-1")

    kwargs = {"region_name": region}
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return boto3.client("s3", **kwargs)


def list_objects(s3, bucket: str, prefix: str = "") -> Iterator[str]:
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            yield obj["Key"]


def compute_new_key(key: str, mode: str) -> str | None:
    """変換後のキーを返す。変化が無ければ None。

    mode:
      remove_any   -> 文字列中の'.m4a'すべて削除
      before_transcription -> '_transcription' の直前にある '.m4a' のみ削除
    """
    if ".m4a" not in key:
        return None
    if mode == "before_transcription":
        # 例: abc.m4a_transcription.json -> abc_transcription.json
        return (
            key.replace(".m4a_transcription", "_transcription")
            if ".m4a_transcription" in key
            else None
        )
    # デフォルト: すべて削除
    new_key = key.replace(".m4a", "")
    return new_key if new_key != key else None


def rename_object(s3, bucket: str, old_key: str, new_key: str, dry_run: bool):
    if dry_run:
        print(f"[DRY-RUN] Would rename: {old_key} -> {new_key}")
        return
    s3.copy_object(
        Bucket=bucket, CopySource={"Bucket": bucket, "Key": old_key}, Key=new_key
    )
    s3.delete_object(Bucket=bucket, Key=old_key)
    print(f"Renamed: {old_key} -> {new_key}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="S3 object key bulk renamer (.m4a remover)"
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("S3_BUCKET_NAME", "audio4gladia"),
        help="Target S3 bucket",
    )
    parser.add_argument(
        "--prefix", default=os.getenv("S3_PREFIX", ""), help="Key prefix filter"
    )
    parser.add_argument(
        "--mode",
        choices=["remove_any", "before_transcription"],
        default="remove_any",
        help="Rename strategy",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not actually modify objects"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max number of objects to process (0 = all)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    s3 = build_s3_client()

    processed = 0
    skipped_exist = 0
    changed = 0
    nochange = 0
    errors = 0

    print(
        f"Start rename bucket={args.bucket} prefix='{args.prefix}' mode={args.mode} dry_run={args.dry_run}"
    )

    for key in list_objects(s3, args.bucket, args.prefix):
        new_key = compute_new_key(key, args.mode)
        if not new_key:
            nochange += 1
            continue
        if new_key == key:
            nochange += 1
            continue
        # 既存チェック
        try:
            s3.head_object(Bucket=args.bucket, Key=new_key)
            print(f"Skip (exists): {new_key}")
            skipped_exist += 1
            continue
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in (
                "404",
                "NotFound",
                "NoSuchKey",
            ):
                print(f"Head error {new_key}: {e}")
                errors += 1
                continue
        try:
            rename_object(s3, args.bucket, key, new_key, args.dry_run)
            changed += 1
        except Exception as e:  # noqa
            print(f"Rename failed {key} -> {new_key}: {e}")
            errors += 1
        processed += 1
        if args.limit and processed >= args.limit:
            print("Reached processing limit.")
            break

    print("\nSummary")
    print(f"  Changed : {changed}")
    print(f"  Skipped(existing target): {skipped_exist}")
    print(f"  No change needed : {nochange}")
    print(f"  Errors  : {errors}")
    if args.dry_run:
        print("  (Dry-run mode: no objects were actually modified)")


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        sys.exit(130)
