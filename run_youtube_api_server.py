#!/usr/bin/env python3
"""
YouTube Video Management API Server Runner
Starts the Flask server for YouTube video data management
"""

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_requirements():
    """Check if required packages are installed"""
    required_packages = [
        ("flask", "flask"),
        ("flask-cors", "flask_cors"),
        ("boto3", "boto3"),
        ("python-dotenv", "dotenv"),
    ]

    missing_packages = []
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
        except ImportError:
            missing_packages.append(package_name)

    if missing_packages:
        logger.error(f"Missing required packages: {', '.join(missing_packages)}")
        logger.error("Install them with: pip install " + " ".join(missing_packages))
        return False

    return True


def check_environment():
    """Check if environment variables are set"""
    load_dotenv()

    # Required environment variables
    required_env_vars = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_DEFAULT_REGION",
    ]

    missing_vars = []
    for var in required_env_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
        logger.error("Please set them in your .env file or environment")
        return False

    # Optional variables with defaults
    table_name = os.getenv("YOUTUBE_DYNAMODB_TABLE", "youtube_videos")
    port = os.getenv("YOUTUBE_API_PORT", "5001")

    logger.info(f"✅ Environment configured:")
    logger.info(f"   - DynamoDB Table: {table_name}")
    logger.info(f"   - API Port: {port}")
    logger.info(f"   - AWS Region: {os.getenv('AWS_DEFAULT_REGION')}")

    return True


def main():
    """Main function to start the YouTube API server"""
    logger.info("🚀 Starting YouTube Video Management API Server")

    # Check requirements
    if not check_requirements():
        logger.error("❌ Requirements check failed")
        sys.exit(1)

    # Check environment
    if not check_environment():
        logger.error("❌ Environment check failed")
        sys.exit(1)

    try:
        # Import and run the server
        from api.youtube_api_server import app

        port = int(os.getenv("YOUTUBE_API_PORT", 5001))
        debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

        logger.info(f"✅ Starting server on http://localhost:{port}")
        logger.info(f"✅ Web interface: http://localhost:{port}/")
        logger.info(f"✅ API endpoints: http://localhost:{port}/api/")
        logger.info(f"✅ Health check: http://localhost:{port}/health")

        app.run(host="0.0.0.0", port=port, debug=debug)

    except ImportError as e:
        logger.error(f"❌ Failed to import server module: {e}")
        logger.error("Make sure you're running this from the project root directory")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
