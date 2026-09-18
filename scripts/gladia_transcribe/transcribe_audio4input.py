"""
audio4input バケット内の mp4 ファイルを Gladia で文字起こしし、
結果を audio4gladia バケットに保存するスクリプト。

使い方:
    python scripts/transcribe_audio4input.py
    python scripts/transcribe_audio4input.py --prefix some/prefix/ --limit 5
"""

import argparse
import logging
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from dotenv import load_dotenv

from services.aws.GladiaTranscribe import GladiaTranscriber

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# 入力バケット（mp4が格納されている）
INPUT_BUCKET = os.getenv("S3_INPUT_BUCKET", "audio4input")


def list_mp4_files(transcriber: GladiaTranscriber, bucket: str, prefix: str = ""):
    """S3バケット内のmp4ファイル一覧を取得"""
    keys = []
    continuation_token = None

    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = transcriber.s3_client.list_objects_v2(**kwargs)

        for obj in response.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".mp4"):
                keys.append(key)

        if response.get("IsTruncated"):
            continuation_token = response.get("NextContinuationToken")
        else:
            break

    return keys


def main():
    parser = argparse.ArgumentParser(
        description="audio4input の mp4 を Gladia で文字起こしし、audio4gladia に結果を保存する"
    )
    parser.add_argument(
        "--bucket", default=INPUT_BUCKET, help="入力S3バケット名 (デフォルト: audio4input)"
    )
    parser.add_argument("--prefix", default="", help="S3キーのプレフィックス(フォルダ)絞り込み")
    parser.add_argument(
        "--limit", type=int, default=None, help="処理するファイル数の上限（テスト用）"
    )
    args = parser.parse_args()

    transcriber = GladiaTranscriber()

    logger.info(f"🔍 Listing mp4 files in s3://{args.bucket}/{args.prefix}")
    mp4_keys = list_mp4_files(transcriber, args.bucket, args.prefix)
    logger.info(f"📋 Found {len(mp4_keys)} mp4 file(s)")

    if args.limit:
        mp4_keys = mp4_keys[: args.limit]

    success_count = 0
    failure_count = 0

    for s3_key in mp4_keys:
        file_id = os.path.splitext(os.path.basename(s3_key))[0]
        logger.info(f"🎬 Processing: s3://{args.bucket}/{s3_key} (file_id={file_id})")

        try:
            success = transcriber.process_transcription(args.bucket, s3_key, file_id)
        except Exception as e:
            logger.error(f"❌ Unexpected error while processing {s3_key}: {e}")
            success = False

        if success:
            success_count += 1
            logger.info(f"✅ Done: {file_id}")
        else:
            failure_count += 1
            logger.error(f"❌ Failed: {file_id}")

    logger.info(
        f"🏁 Finished. success={success_count}, failure={failure_count}, total={len(mp4_keys)}"
    )


if __name__ == "__main__":
    main()
