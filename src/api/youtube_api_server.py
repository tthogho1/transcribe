"""
YouTube Video Management API Server
Provides REST API for YouTube video data stored in DynamoDB
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import boto3
from botocore.exceptions import ClientError

from services.database.youtube_dynamodb_client import YouTubeDynamoDBClient, VideoRecord

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Get absolute paths for templates and static files
current_dir = Path(__file__).parent.absolute()
template_dir = current_dir.parent / "templates"
static_dir = current_dir.parent / "static"

# Initialize Flask app
app = Flask(__name__, template_folder=str(template_dir), static_folder=str(static_dir))
CORS(app)

# Log template and static directories for debugging
logger.info(f"Template directory: {template_dir}")
logger.info(f"Static directory: {static_dir}")
logger.info(f"Template directory exists: {template_dir.exists()}")
logger.info(f"Static directory exists: {static_dir.exists()}")

# Initialize DynamoDB client
table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE", "youtube_videos")
dynamodb_client = YouTubeDynamoDBClient(table_name)

# Initialize S3 client for transcription text files
s3_bucket_name = os.getenv("S3_BUCKET_NAME")
s3_client = boto3.client("s3") if s3_bucket_name else None

if s3_bucket_name:
    logger.info(f"S3 bucket configured: {s3_bucket_name}")
else:
    logger.warning(
        "S3_BUCKET_NAME not configured - transcription text viewing will be disabled"
    )


@app.route("/")
def index():
    """Serve the video management interface"""
    try:
        logger.info("Attempting to render youtube_videos.html template")
        return render_template("youtube_videos.html")
    except Exception as e:
        logger.error(f"Failed to render template: {e}")
        logger.error(f"Template folder: {app.template_folder}")
        logger.error(
            f"Available templates: {list(Path(app.template_folder).glob('*.html')) if Path(app.template_folder).exists() else 'Template folder not found'}"
        )
        return jsonify({"error": f"Template not found: {str(e)}"}), 500


@app.route("/api/videos", methods=["GET"])
def get_videos():
    """
    Get videos with pagination and optional filtering
    Query parameters:
    - limit: Number of videos per page (default: 50)
    - last_key: Base64 encoded pagination key
    - transcribed: Filter by transcription status (true/false)
    - search: Search term for title/author
    """
    try:
        # Get query parameters
        limit = min(int(request.args.get("limit", 50)), 100)  # Max 100 per request
        last_key_param = request.args.get("last_key")
        transcribed_param = request.args.get("transcribed")
        search_term = request.args.get("search", "").strip()

        # Parse last_evaluated_key
        last_evaluated_key = None
        if last_key_param:
            try:
                import base64

                decoded_key = base64.b64decode(last_key_param).decode("utf-8")
                last_evaluated_key = json.loads(decoded_key)
            except Exception as e:
                logger.warning(f"Invalid pagination key: {e}")

        # Parse transcribed filter
        transcribed_filter = None
        if transcribed_param is not None:
            transcribed_filter = transcribed_param.lower() == "true"

        # Perform search or regular listing
        if search_term:
            result = dynamodb_client.search_videos(
                search_term=search_term,
                limit=limit,
                last_evaluated_key=last_evaluated_key,
            )
        else:
            result = dynamodb_client.get_videos(
                limit=limit,
                last_evaluated_key=last_evaluated_key,
                transcribed_filter=transcribed_filter,
            )

        # Encode pagination key for response
        if result.get("last_evaluated_key"):
            import base64

            encoded_key = base64.b64encode(
                json.dumps(result["last_evaluated_key"]).encode("utf-8")
            ).decode("utf-8")
            result["next_page_key"] = encoded_key
            del result["last_evaluated_key"]  # Remove internal key

        # Add request metadata
        result["request_params"] = {
            "limit": limit,
            "transcribed_filter": transcribed_filter,
            "search_term": search_term if search_term else None,
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting videos: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>", methods=["GET"])
def get_video_by_id(video_id: str):
    """Get a specific video by ID"""
    try:
        video = dynamodb_client.get_video_by_id(video_id)

        if not video:
            return jsonify({"error": "Video not found"}), 404

        return jsonify({"video": video.to_dict(), "video_id": video_id})

    except Exception as e:
        logger.error(f"Error getting video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/<video_id>/transcription", methods=["GET"])
def get_video_transcription(video_id: str):
    """Get transcription text for a specific video from S3"""
    try:
        if not s3_client or not s3_bucket_name:
            return jsonify({"error": "S3 configuration not available"}), 500

        # S3 object key is the same as video ID (assuming .json extension)
        object_key = f"{video_id}.json"

        logger.info(
            f"Attempting to fetch transcription from S3: {s3_bucket_name}/{object_key}"
        )

        try:
            # Get object from S3
            response = s3_client.get_object(Bucket=s3_bucket_name, Key=object_key)
            transcription_text = response["Body"].read().decode("utf-8")

            logger.info(f"Successfully retrieved transcription for video {video_id}")

            return jsonify(
                {
                    "video_id": video_id,
                    "transcription": transcription_text,
                    "s3_bucket": s3_bucket_name,
                    "s3_key": object_key,
                    "last_modified": (
                        response.get("LastModified").isoformat()
                        if response.get("LastModified")
                        else None
                    ),
                    "content_length": response.get("ContentLength", 0),
                }
            )

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchKey":
                logger.warning(
                    f"Transcription file not found for video {video_id}: {object_key}"
                )
                return jsonify({"error": "Transcription file not found"}), 404
            else:
                logger.error(f"S3 error retrieving transcription for {video_id}: {e}")
                return jsonify({"error": f"S3 error: {error_code}"}), 500

    except Exception as e:
        logger.error(f"Error getting transcription for video {video_id}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/transcription/<video_id>")
def view_transcription(video_id: str):
    """Serve transcription viewer page for a specific video"""
    try:
        return render_template("transcription_viewer.html", video_id=video_id)
    except Exception as e:
        logger.error(f"Failed to render transcription viewer template: {e}")
        return jsonify({"error": "Template not found"}), 500


@app.route("/api/stats", methods=["GET"])
def get_video_stats():
    """Get video statistics"""
    try:
        stats = dynamodb_client.get_videos_stats()

        return jsonify({"stats": stats, "timestamp": datetime.now().isoformat()})

    except Exception as e:
        logger.error(f"Error getting video statistics: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/transcribed", methods=["GET"])
def get_transcribed_videos():
    """Get only transcribed videos"""
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
        last_key_param = request.args.get("last_key")

        last_evaluated_key = None
        if last_key_param:
            try:
                import base64

                decoded_key = base64.b64decode(last_key_param).decode("utf-8")
                last_evaluated_key = json.loads(decoded_key)
            except Exception as e:
                logger.warning(f"Invalid pagination key: {e}")

        result = dynamodb_client.get_videos(
            limit=limit, last_evaluated_key=last_evaluated_key, transcribed_filter=True
        )

        if result.get("last_evaluated_key"):
            import base64

            encoded_key = base64.b64encode(
                json.dumps(result["last_evaluated_key"]).encode("utf-8")
            ).decode("utf-8")
            result["next_page_key"] = encoded_key
            del result["last_evaluated_key"]

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting transcribed videos: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/videos/untranscribed", methods=["GET"])
def get_untranscribed_videos():
    """Get only untranscribed videos"""
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
        last_key_param = request.args.get("last_key")

        last_evaluated_key = None
        if last_key_param:
            try:
                import base64

                decoded_key = base64.b64decode(last_key_param).decode("utf-8")
                last_evaluated_key = json.loads(decoded_key)
            except Exception as e:
                logger.warning(f"Invalid pagination key: {e}")

        result = dynamodb_client.get_videos(
            limit=limit, last_evaluated_key=last_evaluated_key, transcribed_filter=False
        )

        if result.get("last_evaluated_key"):
            import base64

            encoded_key = base64.b64encode(
                json.dumps(result["last_evaluated_key"]).encode("utf-8")
            ).decode("utf-8")
            result["next_page_key"] = encoded_key
            del result["last_evaluated_key"]

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting untranscribed videos: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/search", methods=["GET"])
def search_videos():
    """Search videos by title or author"""
    try:
        search_term = request.args.get("q", "").strip()

        if not search_term:
            return jsonify({"error": "Search term is required"}), 400

        limit = min(int(request.args.get("limit", 50)), 100)
        last_key_param = request.args.get("last_key")

        last_evaluated_key = None
        if last_key_param:
            try:
                import base64

                decoded_key = base64.b64decode(last_key_param).decode("utf-8")
                last_evaluated_key = json.loads(decoded_key)
            except Exception as e:
                logger.warning(f"Invalid pagination key: {e}")

        result = dynamodb_client.search_videos(
            search_term=search_term, limit=limit, last_evaluated_key=last_evaluated_key
        )

        if result.get("last_evaluated_key"):
            import base64

            encoded_key = base64.b64encode(
                json.dumps(result["last_evaluated_key"]).encode("utf-8")
            ).decode("utf-8")
            result["next_page_key"] = encoded_key
            del result["last_evaluated_key"]

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error searching videos: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    try:
        # Test DynamoDB connection
        db_status = dynamodb_client.test_connection()

        return jsonify(
            {
                "status": "healthy" if db_status else "degraded",
                "timestamp": datetime.now().isoformat(),
                "services": {
                    "dynamodb": "connected" if db_status else "disconnected",
                    "table_name": table_name,
                },
                "version": "1.0.0",
            }
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )


if __name__ == "__main__":
    """Run the YouTube video management server"""
    port = int(os.getenv("YOUTUBE_API_PORT", 5001))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    logger.info(f"Starting YouTube Video Management API server on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"DynamoDB table: {table_name}")

    # Test DynamoDB connection on startup
    if dynamodb_client.test_connection():
        logger.info("✅ DynamoDB connection successful")
    else:
        logger.warning("⚠️ DynamoDB connection failed - server starting anyway")

    app.run(host="0.0.0.0", port=port, debug=debug)
