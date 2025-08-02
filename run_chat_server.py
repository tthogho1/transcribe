"""
Chat Server Runner - Execute from project root
This script sets up the Python path and runs the chat server
Usage: python run_chat_server.py
"""

import sys
import os
import logging
from pathlib import Path


def setup_python_path():
    """Add src directory to Python path for imports"""
    # Get the directory where this script is located (project root)
    project_root = Path(__file__).parent.absolute()
    src_path = project_root / "src"

    # Add src to Python path if not already there
    src_str = str(src_path)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)

    print(f"✅ Added to Python path: {src_str}")
    return project_root


def load_environment():
    """Load environment variables"""
    try:
        from dotenv import load_dotenv

        # Load .env file from project root
        project_root = Path(__file__).parent.absolute()
        env_file = project_root / ".env"

        if env_file.exists():
            load_dotenv(env_file)
            print(f"✅ Loaded environment from: {env_file}")
        else:
            print(f"⚠️ No .env file found at: {env_file}")

        # Also try loading from src/.env
        src_env_file = project_root / "src" / ".env"
        if src_env_file.exists():
            load_dotenv(src_env_file)
            print(f"✅ Also loaded environment from: {src_env_file}")

    except ImportError:
        print("⚠️ python-dotenv not installed, skipping .env file loading")


def configure_logging():
    """Configure logging for the application"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Set specific loggers to reduce noise
    logging.getLogger("werkzeug").setLevel(logging.WARNING)  # Reduce Flask noise
    logging.getLogger("engineio").setLevel(logging.WARNING)  # Reduce SocketIO noise
    logging.getLogger("socketio").setLevel(logging.WARNING)  # Reduce SocketIO noise
    logging.getLogger("urllib3").setLevel(logging.WARNING)  # Reduce HTTP noise

    print("✅ Logging configured")


def check_requirements():
    """Check if required packages are available"""
    required_packages = [
        "flask",
        "flask_socketio",
        "flask_cors",
        "openai",
        "pymilvus",
        "sentence_transformers",
        "cohere",
        "langdetect",
        "deep_translator",
    ]

    missing_packages = []

    for package in required_packages:
        try:
            if package == "flask_socketio":
                __import__("flask_socketio")
            elif package == "flask_cors":
                __import__("flask_cors")
            elif package == "deep_translator":
                __import__("deep_translator")
            else:
                __import__(package)
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("Please install them using:")
        print(f"pip install {' '.join(missing_packages)}")
        return False

    print("✅ All required packages are available")
    return True


def main():
    """Main function to run the chat server"""
    print("🚀 Starting Chat Server...")
    print("=" * 50)

    # Setup environment
    project_root = setup_python_path()
    load_environment()
    configure_logging()

    # Check requirements
    if not check_requirements():
        print("❌ Requirements check failed. Exiting.")
        sys.exit(1)

    try:
        # Import after setting up the path
        from api.chat_server import app, socketio

        # Get configuration from environment
        port = int(os.getenv("FLASK_PORT", 5000))
        debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
        host = os.getenv("FLASK_HOST", "0.0.0.0")

        # Log configuration
        logger = logging.getLogger(__name__)
        logger.info("🔧 Chat Server Configuration:")
        logger.info(f"   Host: {host}")
        logger.info(f"   Port: {port}")
        logger.info(f"   Debug: {debug}")
        logger.info(f"   Project Root: {project_root}")

        # Check environment variables
        required_env_vars = ["ZILLIZ_URI", "ZILLIZ_TOKEN", "OPENAI_API_KEY"]
        missing_env_vars = []

        for var in required_env_vars:
            if not os.getenv(var):
                missing_env_vars.append(var)

        if missing_env_vars:
            logger.warning(
                f"⚠️ Missing environment variables: {', '.join(missing_env_vars)}"
            )
            logger.warning(
                "The server may not function properly without these variables."
            )
            logger.warning("Please check your .env file or environment settings.")
        else:
            logger.info("✅ All required environment variables are set")

        # Check optional environment variables
        optional_env_vars = {
            "COHERE_API_KEY": "Cohere reranking",
            "RERANK_METHOD": "Reranking method (cohere/cross_encoder)",
            "OPENAI_MODEL": "OpenAI model selection",
        }

        for var, description in optional_env_vars.items():
            if os.getenv(var):
                logger.info(f"✅ {description}: {os.getenv(var)}")
            else:
                logger.info(f"ℹ️ {description}: Using default")

        # Start the server
        logger.info("🌐 Starting Flask-SocketIO server...")
        logger.info(f"🔗 Access the chat interface at: http://localhost:{port}")
        logger.info("🔗 API endpoints:")
        logger.info(f"   - Chat API: http://localhost:{port}/api/chat")
        logger.info(f"   - Search API: http://localhost:{port}/api/search")
        logger.info(f"   - Health Check: http://localhost:{port}/health")
        logger.info("📡 WebSocket support enabled")
        logger.info("🛑 Press Ctrl+C to stop the server")

        print("=" * 50)

        # Run the server
        socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=True,
            use_reloader=False,  # Disable reloader when running as script
        )

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all required files are in the correct directories.")
        print("Expected structure:")
        print("  src/")
        print("  ├── api/")
        print("  │   └── chat_server.py")
        print("  ├── models/")
        print("  │   └── conversation_chunk.py")
        print("  ├── core/")
        print("  │   └── conversation_vectorizer.py")
        print("  └── services/")
        print("      └── database/")
        print("          └── zilliz_client.py")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed to start chat server: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
