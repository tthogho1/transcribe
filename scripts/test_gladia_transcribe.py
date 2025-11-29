import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
from services.aws.GladiaTranscribe import GladiaTranscriber
from services.database.youtube_dynamodb_client import YouTubeDynamoDBClient
from dotenv import load_dotenv

load_dotenv()

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
        s3_key = f"{file_id}.m4a"

        print(
            f"\n[{idx}/{len(untranscribed_videos)}] Processing: {file_id} - {video.get('title', 'N/A')}"
        )

        try:
            success = transcriber.process_transcription(s3_bucket, s3_key, file_id)
            if success:
                print(f"✅ Successfully transcribed: {file_id}")
            else:
                print(f"❌ Failed to transcribe: {file_id}")
        except Exception as e:
            print(f"❌ Error transcribing {file_id}: {e}")

    print("\n🎉 Batch transcription completed!")
