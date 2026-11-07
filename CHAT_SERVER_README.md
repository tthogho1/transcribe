# Chat Server Runner Instructions

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy the environment template and configure your settings:

```bash
cp .env.example .env    # Windows: copy .env.example .env
```

Edit `.env` with your actual credentials (`.env.example` lists every setting with its default):

- `ZILLIZ_URI` - Your Zilliz Cloud URI
- `ZILLIZ_TOKEN` - Your Zilliz Cloud token
- `OPENAI_API_KEY` - Your OpenAI API key

⚠️ **Security Notice**: The `.env` files are excluded from Git via `.gitignore` to protect your sensitive credentials. Never commit actual API keys or tokens to version control.

### 3. Run the Chat Server

```bash
python run_chat_server.py
```

## 📁 Project Structure

```
Transcribe/
├── run_chat_server.py          # Main server runner
├── .env                        # Environment variables (create from template)
├── .env.example               # Environment template
├── requirements.txt           # Python dependencies
└── src/
    ├── api/
    │   └── chat_server.py     # Flask application
    ├── models/
    │   └── conversation_chunk.py
    ├── core/
    │   └── conversation_vectorizer.py
    └── services/
        ├── data/
        ├── processing/
        ├── database/
        └── aws/
```

## 🔧 Configuration Options

### Required Environment Variables

- `ZILLIZ_URI` - Zilliz Cloud connection URI
- `ZILLIZ_TOKEN` - Zilliz Cloud authentication token
- `OPENAI_API_KEY` - OpenAI API key for GPT models

### Optional Environment Variables

- `FLASK_PORT` - Server port (default: 5000)
- `FLASK_DEBUG` - Debug mode (default: false)
- `COHERE_API_KEY` - For Cohere reranking
- `RERANK_METHOD` - "cohere" or "cross_encoder" (default: cross_encoder)

## 🌐 API Endpoints

Once running, the server provides:

- **Web Interface**: `http://localhost:5000`
- **Chat API**: `POST http://localhost:5000/api/chat`
- **Search API**: `POST http://localhost:5000/api/search`
- **Health Check**: `GET http://localhost:5000/health`
- **WebSocket**: Real-time chat via Socket.IO

## 🛠️ Development

### VS Code Debug Configuration

The project includes VS Code launch configurations for debugging:

- **Python: Chat Server** - Debug the chat server
- **Python: Integration Test** - Run integration tests

### Running Individual Components

```bash
# Run from project root
python -m src.api.chat_server

# Or use the runner script
python run_chat_server.py
```

## ❓ Troubleshooting

### Common Issues

1. **Import Errors**: Make sure you're running from the project root
2. **Missing Dependencies**: Run `pip install -r requirements.txt`
3. **Environment Variables**: Check your `.env` file configuration
4. **Port Already in Use**: Change `FLASK_PORT` in `.env`

### Log Output

The server provides detailed logging including:

- ✅ Successful initialization steps
- ⚠️ Warnings for missing optional configuration
- ❌ Errors with specific troubleshooting guidance
