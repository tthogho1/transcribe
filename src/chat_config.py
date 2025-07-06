"""
Flask Chat Server Configuration
Configuration settings for the chat server application
"""

# Server Configuration
FLASK_PORT = 5000
FLASK_DEBUG = False
FLASK_SECRET_KEY = "your-super-secret-key-change-this"

# OpenAI Configuration
OPENAI_MODEL = "gpt-3.5-turbo"
OPENAI_MAX_TOKENS = 1000
OPENAI_TEMPERATURE = 0.7

# Chat Service Configuration
MAX_SEARCH_RESULTS = 5
DEFAULT_QUERY_LIMIT = 5

# WebSocket Configuration
SOCKETIO_ASYNC_MODE = "threading"

# CORS Configuration (for development)
CORS_ORIGINS = "*"

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Cache Configuration (optional)
CACHE_TYPE = "simple"
CACHE_DEFAULT_TIMEOUT = 300

# Rate Limiting (optional)
RATELIMIT_STORAGE_URL = "memory://"
RATELIMIT_DEFAULT = "100 per hour"
