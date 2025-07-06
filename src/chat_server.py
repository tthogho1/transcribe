"""
Flask Chat Server with Zilliz Cloud and OpenAI Integration
Provides RAG (Retrieval-Augmented Generation) functionality for conversation search
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import openai
from pymilvus import connections, Collection
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# OpenAI Configuration
openai.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class SearchResult:
    """Data class for search results"""

    text: str
    speaker: str
    timestamp: str
    score: float
    similarity: float


@dataclass
class ChatResponse:
    """Data class for chat responses"""

    answer: str
    sources: List[SearchResult]
    query: str
    timestamp: str
    tokens_used: int


class ZillizSearchEngine:
    """Zilliz Cloud search engine for conversation retrieval"""

    def __init__(self):
        self.zilliz_uri = os.getenv("ZILLIZ_URI")
        self.zilliz_token = os.getenv("ZILLIZ_TOKEN")
        self.embedding_model = None
        self.collection = None
        self.collection_name = "conversation_chunks"

        self._initialize()

    def _initialize(self):
        """Initialize Zilliz connection and embedding model"""
        try:
            # Initialize embedding model
            logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformer(
                "sonoisa/sentence-bert-base-ja-mean-tokens-v2"
            )

            # Connect to Zilliz Cloud
            logger.info("Connecting to Zilliz Cloud...")
            connections.connect(
                alias="default", uri=self.zilliz_uri, token=self.zilliz_token
            )

            # Get collection
            self.collection = Collection(self.collection_name)
            self.collection.load()

            logger.info("✅ Zilliz search engine initialized successfully")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Zilliz search engine: {e}")
            raise

    def search_similar_conversations(
        self, query: str, limit: int = 5
    ) -> List[SearchResult]:
        """
        Search for similar conversations in Zilliz Cloud

        Args:
            query: Search query
            limit: Number of results to return

        Returns:
            List of search results
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])

            # Search parameters
            search_params = {
                "metric_type": "IP",  # Inner Product
                "params": {"nprobe": 10},
            }

            # Perform search
            results = self.collection.search(
                query_embedding,
                "embedding",
                search_params,
                limit=limit,
                output_fields=["text", "speaker", "timestamp"],
            )

            # Convert results to SearchResult objects
            search_results = []
            for hit in results[0]:
                search_results.append(
                    SearchResult(
                        text=hit.entity.get("text", ""),
                        speaker=hit.entity.get("speaker", "Unknown"),
                        timestamp=hit.entity.get("timestamp", ""),
                        score=float(hit.score),
                        similarity=float(
                            hit.score
                        ),  # In case we want to calculate differently
                    )
                )

            logger.info(
                f"Found {len(search_results)} similar conversations for query: {query}"
            )
            return search_results

        except Exception as e:
            logger.error(f"Error searching conversations: {e}")
            return []


class OpenAIGenerator:
    """OpenAI GPT integration for generating responses"""

    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    def generate_response(
        self, query: str, search_results: List[SearchResult]
    ) -> Dict[str, Any]:
        """
        Generate response using OpenAI with search results as context

        Args:
            query: User's question
            search_results: Relevant conversation excerpts from Zilliz

        Returns:
            Dictionary containing response and metadata
        """
        try:
            # Prepare context from search results
            context_parts = []
            for i, result in enumerate(search_results, 1):
                context_parts.append(
                    f"[Context {i}] Speaker: {result.speaker}\n"
                    f"Content: {result.text}\n"
                    f"Timestamp: {result.timestamp}\n"
                    f"Relevance Score: {result.score:.3f}\n"
                )

            context = "\n".join(context_parts)

            # Create system prompt
            system_prompt = """You are a helpful AI assistant that answers questions based on conversation transcripts. 
            Use the provided context from past conversations to answer the user's question. 
            If the context doesn't contain relevant information, say so clearly.
            Always be helpful, accurate, and cite the context when possible.
            
            Guidelines:
            - Answer in the same language as the question
            - Be concise but comprehensive
            - If multiple speakers discussed the topic, mention different perspectives
            - Include relevant quotes from the conversations when helpful
            """

            # Create user prompt
            user_prompt = f"""Question: {query}

Context from relevant conversations:
{context}

Please provide a helpful answer based on the above context. If the context doesn't contain enough information to answer the question, please say so."""

            # Generate response
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            return {
                "answer": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error generating OpenAI response: {e}")
            return {
                "answer": "申し訳ございませんが、回答の生成中にエラーが発生しました。",
                "tokens_used": 0,
                "model": self.model,
                "error": str(e),
            }


class ChatService:
    """Main chat service combining Zilliz search and OpenAI generation"""

    def __init__(self):
        self.search_engine = ZillizSearchEngine()
        self.ai_generator = OpenAIGenerator()

    def process_chat_query(self, query: str, max_results: int = 5) -> ChatResponse:
        """
        Process a chat query with RAG (Retrieval-Augmented Generation)

        Args:
            query: User's question
            max_results: Maximum number of search results to use

        Returns:
            ChatResponse with answer and sources
        """
        try:
            # Search for relevant conversations
            search_results = self.search_engine.search_similar_conversations(
                query, limit=max_results
            )

            # Generate AI response
            ai_response = self.ai_generator.generate_response(query, search_results)

            # Create chat response
            chat_response = ChatResponse(
                answer=ai_response["answer"],
                sources=search_results,
                query=query,
                timestamp=datetime.now().isoformat(),
                tokens_used=ai_response["tokens_used"],
            )

            return chat_response

        except Exception as e:
            logger.error(f"Error processing chat query: {e}")
            return ChatResponse(
                answer="申し訳ございませんが、処理中にエラーが発生しました。",
                sources=[],
                query=query,
                timestamp=datetime.now().isoformat(),
                tokens_used=0,
            )


# Initialize chat service
chat_service = ChatService()


# Flask Routes
@app.route("/")
def index():
    """Serve the chat interface"""
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """REST API endpoint for chat"""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()

        if not query:
            return jsonify({"error": "Query is required"}), 400

        # Process chat query
        response = chat_service.process_chat_query(query)

        # Convert to JSON-serializable format
        return jsonify(
            {
                "answer": response.answer,
                "sources": [
                    {
                        "text": source.text,
                        "speaker": source.speaker,
                        "timestamp": source.timestamp,
                        "score": source.score,
                    }
                    for source in response.sources
                ],
                "query": response.query,
                "timestamp": response.timestamp,
                "tokens_used": response.tokens_used,
            }
        )

    except Exception as e:
        logger.error(f"API chat error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/search", methods=["POST"])
def api_search():
    """REST API endpoint for conversation search only"""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        limit = data.get("limit", 5)

        if not query:
            return jsonify({"error": "Query is required"}), 400

        # Search conversations
        results = chat_service.search_engine.search_similar_conversations(query, limit)

        return jsonify(
            {
                "query": query,
                "results": [
                    {
                        "text": result.text,
                        "speaker": result.speaker,
                        "timestamp": result.timestamp,
                        "score": result.score,
                    }
                    for result in results
                ],
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health_check():
    """Health check endpoint"""
    return jsonify(
        {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "zilliz": (
                    "connected"
                    if chat_service.search_engine.collection
                    else "disconnected"
                ),
                "openai": "configured" if openai.api_key else "not configured",
            },
        }
    )


# Socket.IO Events
@socketio.on("connect")
def handle_connect():
    """Handle client connection"""
    logger.info(f"Client connected: {request.sid}")
    emit("status", {"message": "Connected to chat server"})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {request.sid}")


@socketio.on("chat_message")
def handle_chat_message(data):
    """Handle chat message via WebSocket"""
    try:
        query = data.get("query", "").strip()

        if not query:
            emit("chat_error", {"error": "Query is required"})
            return

        logger.info(f"Processing chat query: {query}")

        # Process chat query
        response = chat_service.process_chat_query(query)

        # Send response
        emit(
            "chat_response",
            {
                "answer": response.answer,
                "sources": [
                    {
                        "text": source.text,
                        "speaker": source.speaker,
                        "timestamp": source.timestamp,
                        "score": source.score,
                    }
                    for source in response.sources
                ],
                "query": response.query,
                "timestamp": response.timestamp,
                "tokens_used": response.tokens_used,
            },
        )

    except Exception as e:
        logger.error(f"WebSocket chat error: {e}")
        emit("chat_error", {"error": str(e)})


if __name__ == "__main__":
    """Run the Flask chat server"""
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"

    logger.info(f"Starting Flask chat server on port {port}")
    logger.info(f"Debug mode: {debug}")

    socketio.run(
        app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True
    )
