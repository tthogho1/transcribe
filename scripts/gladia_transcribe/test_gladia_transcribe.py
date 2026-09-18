import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from services.aws.GladiaTranscribe import GladiaTranscriber
from services.database.youtube_dynamodb_client import YouTubeDynamoDBClient
from dotenv import load_dotenv

load_dotenv()

# 対応する音声/動画ファイルの拡張子（優先順）
SUPPORTED_EXTENSIONS = [".m4a", ".mp4"]


def find_existing_s3_key(s3_client, bucket: str, file_id: str):
    """
    file_idに対して、対応する拡張子のファイルがS3に存在するか確認し、
    見つかった最初のS3キーを返す。見つからない場合はNoneを返す。
    """
    for ext in SUPPORTED_EXTENSIONS:
        candidate_key = f"{file_id}{ext}"
        try:
            s3_client.head_object(Bucket=bucket, Key=candidate_key)
            return candidate_key
        except Exception:
            continue
    return None


if __name__ == "__main__":
    s3_bucket = "audio4input"

    # DynamoDBクライアント初期化
    table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE", "YoutubeList")
    dynamodb_client = YouTubeDynamoDBClient(table_name=table_name)

    # transcribedフラグが0またはfalseの動画を取得
    print("🔍 Searching for untranscribed videos...")
    result = dynamodb_client.get_videos(limit=1000, transcribed_filter=0)
    untranscribed_videos = result.get("videos", [])

    if not untranscribed_videos:
        print("✅ No untranscribed videos found.")
        sys.exit(0)

    print(f"📋 Found {len(untranscribed_videos)} untranscribed video(s)")

    # Gladiaトランスクライバー初期化
    transcriber = GladiaTranscriber()

    # 未転写の動画をループ処理
    for idx, video in enumerate(untranscribed_videos, 1):
        file_id = video.get("video_id")

        print(
            f"\n[{idx}/{len(untranscribed_videos)}] Processing: {file_id} - {video.get('title', 'N/A')}"
        )

        # m4a / mp4 のどちらが存在するか確認
        s3_key = find_existing_s3_key(transcriber.s3_client, s3_bucket, file_id)
        if not s3_key:
            print(
                f"⚠️ Skipped: No matching file found for {file_id} "
                f"(tried extensions: {', '.join(SUPPORTED_EXTENSIONS)})"
            )
            continue

        print(f"📁 Found file: s3://{s3_bucket}/{s3_key}")

        try:
            success = transcriber.process_transcription(s3_bucket, s3_key, file_id)
            if success:
                print(f"✅ Successfully transcribed: {file_id}")
            else:
                print(f"❌ Failed to transcribe: {file_id}")
        except Exception as e:
            print(f"❌ Error transcribing {file_id}: {e}")

    print("\n🎉 Batch transcription completed!")
