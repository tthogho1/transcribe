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
from sentence_transformers import SentenceTransformer, CrossEncoder
from dotenv import load_dotenv
import cohere
from langdetect import detect
from deep_translator import GoogleTranslator

# Import from our models
from models.conversation_chunk import SearchResult
from core.conversation_vectorizer import ConversationVectorizer
from services.database.zilliz_client import ZillizClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder="../templates", static_folder="../static")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# OpenAI Configuration
openai.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class ChatResponse:
    """Data class for chat responses"""

    answer: str
    sources: List[SearchResult]
    query: str
    timestamp: str
    tokens_used: int
    file_names: List[str]  # New field to store file names


class ZillizSearchEngine:
    """Zilliz Cloud search engine for conversation retrieval with reranking"""

    def __init__(self):
        self.zilliz_uri = os.getenv("ZILLIZ_URI")
        self.zilliz_token = os.getenv("ZILLIZ_TOKEN")
        self.embedding_model = None
        self.collection = None
        self.collection_name = "conversation_chunks"

        # Reranking configuration
        self.rerank_method = os.getenv(
            "RERANK_METHOD", "cross_encoder"
        )  # "cohere" or "cross_encoder"
        self.cohere_client = None
        self.cross_encoder = None

        # Cross Encoder CPU optimization settings
        self.cross_encoder_device = os.getenv(
            "CROSS_ENCODER_DEVICE", "auto"
        )  # "cpu", "cuda", "auto"
        self.cross_encoder_batch_size = int(
            os.getenv("CROSS_ENCODER_BATCH_SIZE", "8")
        )  # Smaller for CPU
        self.cross_encoder_max_length = int(
            os.getenv("CROSS_ENCODER_MAX_LENGTH", "512")
        )

        # Search parameters
        self.initial_search_multiplier = int(
            os.getenv("INITIAL_SEARCH_MULTIPLIER", "3")
        )  # Search 3x more for reranking

        self._initialize()

    def _initialize(self):
        """Initialize Zilliz connection and embedding model"""
        try:
            # Initialize embedding model
            logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformer(
                "sonoisa/sentence-bert-base-ja-mean-tokens-v2"
            )

            # Initialize reranking models
            self._initialize_reranking()

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

    def _initialize_reranking(self):
        """Initialize reranking models"""
        try:
            if self.rerank_method == "cohere":
                # Initialize Cohere client
                cohere_api_key = os.getenv("COHERE_API_KEY")
                if cohere_api_key:
                    self.cohere_client = cohere.Client(cohere_api_key)
                    logger.info("✅ Cohere reranker initialized")
                else:
                    logger.warning(
                        "⚠️ COHERE_API_KEY not found, falling back to cross encoder"
                    )
                    self.rerank_method = "cross_encoder"

            if self.rerank_method == "cross_encoder":
                # Initialize Cross Encoder model with device optimization
                logger.info("Loading cross encoder model...")

                # Determine device
                import torch

                if self.cross_encoder_device == "auto":
                    device = "cuda" if torch.cuda.is_available() else "cpu"
                else:
                    device = self.cross_encoder_device

                logger.info(f"Using device: {device}")

                # Initialize with device and optimization settings
                self.cross_encoder = CrossEncoder(
                    "cross-encoder/ms-marco-MiniLM-L-6-v2",  # Can be replaced with Japanese-specific model
                    max_length=self.cross_encoder_max_length,
                    device=device,
                )

                # Set batch size for prediction
                if hasattr(self.cross_encoder, "max_batch_size"):
                    self.cross_encoder.max_batch_size = self.cross_encoder_batch_size

                logger.info(
                    f"✅ Cross encoder reranker initialized on {device} (batch_size={self.cross_encoder_batch_size})"
                )

        except Exception as e:
            logger.warning(
                f"⚠️ Reranking initialization failed: {e}, using vector search only"
            )
            self.rerank_method = None

    def _rerank_results(
        self, query: str, search_results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Rerank search results using the configured reranking method

        Args:
            query: Original search query
            search_results: Initial search results from vector search

        Returns:
            Reranked search results
        """
        if not self.rerank_method or len(search_results) <= 1:
            return search_results

        try:
            if self.rerank_method == "cohere" and self.cohere_client:
                return self._rerank_with_cohere(query, search_results)
            elif self.rerank_method == "cross_encoder" and self.cross_encoder:
                return self._rerank_with_cross_encoder(query, search_results)
            else:
                logger.warning(
                    "⚠️ No reranking method available, returning original results"
                )
                return search_results

        except Exception as e:
            logger.error(f"❌ Reranking failed: {e}, returning original results")
            return search_results

    def _rerank_with_cohere(
        self, query: str, search_results: List[SearchResult]
    ) -> List[SearchResult]:
        """Rerank using Cohere Rerank API"""
        try:
            # Prepare documents for reranking
            documents = [result.text for result in search_results]

            # Call Cohere Rerank API
            response = self.cohere_client.rerank(
                model="rerank-multilingual-v2.0",  # Supports Japanese
                query=query,
                documents=documents,
                top_k=len(documents),
            )

            # Reorder results based on Cohere scores
            reranked_results = []
            for result in response.results:
                original_result = search_results[result.index]
                # Update score with rerank score
                reranked_result = SearchResult(
                    text=original_result.text,
                    speaker=original_result.speaker,
                    timestamp=original_result.timestamp,
                    file_name=original_result.file_name,
                    score=float(result.relevance_score),  # Use Cohere rerank score
                    similarity=original_result.similarity,  # Keep original similarity
                    search_type="cohere_rerank",  # Add search type
                )
                reranked_results.append(reranked_result)

            logger.info(f"✅ Reranked {len(reranked_results)} results using Cohere")
            return reranked_results

        except Exception as e:
            logger.error(f"❌ Cohere reranking error: {e}")
            return search_results

    def _rerank_with_cross_encoder(
        self, query: str, search_results: List[SearchResult]
    ) -> List[SearchResult]:
        """Rerank using Cross Encoder model with CPU optimization"""
        try:
            # Prepare query-document pairs
            query_doc_pairs = [(query, result.text) for result in search_results]

            # Get cross encoder scores with batch processing for CPU efficiency
            if len(query_doc_pairs) <= self.cross_encoder_batch_size:
                # Small batch - process all at once
                scores = self.cross_encoder.predict(query_doc_pairs)
            else:
                # Large batch - process in chunks for CPU memory efficiency
                scores = []
                for i in range(0, len(query_doc_pairs), self.cross_encoder_batch_size):
                    batch = query_doc_pairs[i : i + self.cross_encoder_batch_size]
                    batch_scores = self.cross_encoder.predict(batch)
                    scores.extend(batch_scores)

            # Combine results with new scores
            scored_results = []
            for i, result in enumerate(search_results):
                reranked_result = SearchResult(
                    text=result.text,
                    speaker=result.speaker,
                    timestamp=result.timestamp,
                    file_name=result.file_name,
                    score=float(scores[i]),  # Use cross encoder score
                    similarity=result.similarity,  # Keep original similarity
                    search_type="cross_encoder_rerank",  # Add search type
                )
                scored_results.append(reranked_result)

            # Sort by new scores (descending)
            reranked_results = sorted(
                scored_results, key=lambda x: x.score, reverse=True
            )

            logger.info(
                f"✅ Reranked {len(reranked_results)} results using Cross Encoder (batch_size={self.cross_encoder_batch_size})"
            )
            return reranked_results

        except Exception as e:
            logger.error(f"❌ Cross encoder reranking error: {e}")
            return search_results

    def search_similar_conversations(
        self, query: str, limit: int = 5
    ) -> List[SearchResult]:
        """
        Search for similar conversations in Zilliz Cloud with reranking

        Args:
            query: Search query
            limit: Number of final results to return

        Returns:
            List of search results (reranked if enabled)
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_model.encode([query])

            # Ensure L2 normalization for cosine similarity
            import numpy as np

            query_embedding = query_embedding / np.linalg.norm(
                query_embedding, axis=1, keepdims=True
            )

            # Search parameters
            search_params = {
                "metric_type": "IP",  # Inner Product (with normalized vectors = cosine similarity)
                "params": {"nprobe": 20},
            }

            # Search for more results initially if reranking is enabled
            initial_limit = (
                limit * self.initial_search_multiplier if self.rerank_method else limit
            )

            # Perform initial vector search
            results = self.collection.search(
                query_embedding,
                "embedding",
                search_params,
                limit=initial_limit,
                output_fields=[
                    "text",
                    "speaker",
                    "timestamp",
                    "file_name",
                ],  # Include file_name
            )

            # Convert results to SearchResult objects
            search_results = []
            for hit in results[0]:
                search_results.append(
                    SearchResult(
                        text=hit.entity.get("text", ""),
                        speaker=hit.entity.get("speaker", "Unknown"),
                        timestamp=hit.entity.get("timestamp", ""),
                        file_name=hit.entity.get("file_name", "Unknown"),
                        score=float(hit.score),
                        similarity=float(hit.score),
                        search_type="vector_search",  # Add search type
                    )
                )

            logger.info(
                f"Found {len(search_results)} initial results for query: {query}"
            )

            # Apply reranking if enabled
            if self.rerank_method and len(search_results) > 1:
                logger.info(f"Applying {self.rerank_method} reranking...")
                search_results = self._rerank_results(query, search_results)

                # Trim to requested limit after reranking
                search_results = search_results[:limit]

            logger.info(f"Returning {len(search_results)} final results")
            return search_results

        except Exception as e:
            logger.error(f"Error searching conversations: {e}")
            return []


class OpenAIGenerator:
    """OpenAI GPT integration for generating responses"""

    def __init__(self):
        # Note: OpenAI client initialization is handled through openai.api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "1000"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))

    def generate_response(
        self,
        query: str,
        search_results: List[SearchResult],
        is_english_input: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate response using OpenAI with search results as context

        Args:
            query: User's question
            search_results: Relevant conversation excerpts from Zilliz
            is_english_input: Whether the original input was in English

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

            # Create system prompt based on language
            if is_english_input:
                system_prompt = """Answer and guide the user's questions using context provided by your previous conversations.
                    If the context does not include relevant information, clarify it.
                    Also, guide the user to correct their mistake if they misunderstood the context.

                    Important:
                    Speak in the first person as if you experienced the event yourself. When referring to past conversations, explain it as your own experience, not as someone else's.

                    Guidelines:
                    - Answer in English
                    - Answer casually in a natural conversational tone
                """
            else:
                system_prompt = """Answer users' questions by talking about your past experiences.

                    Important:
                    Speak in the first person as if you experienced the event yourself. When referring to past conversations, explain it as your own experience, not as someone else's.

                    Guidelines:
                    - Answer in Japanese
                    - Answer casually in the same tone as the related conversation
                """

            # Create user prompt
            user_prompt = f"""Question: {query}

Context from relevant conversations:
{context}

Please provide a helpful answer based on the above context. If the context doesn't contain enough information to answer the question, please say so."""

            # Generate response
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            answer = response.choices[0].message.content

            # If English input but Japanese response generated, translate back to English
            if is_english_input and detect(answer) == "ja":
                logger.info("Translating response back to English...")
                en_translator = GoogleTranslator(source="ja", target="en")
                answer = en_translator.translate(answer)

            return {
                "answer": answer,
                "tokens_used": response.usage.total_tokens,
                "model": self.model,
            }

        except Exception as e:
            logger.error(f"Error generating OpenAI response: {e}")
            error_message = (
                "Sorry, an error occurred while generating the response."
                if is_english_input
                else "申し訳ございませんが、回答の生成中にエラーが発生しました。"
            )
            return {
                "answer": error_message,
                "tokens_used": 0,
                "model": self.model,
                "error": str(e),
            }


class ChatService:
    """Main chat service combining Zilliz search and OpenAI generation"""

    def __init__(self):
        self.search_engine = ZillizSearchEngine()
        self.ai_generator = OpenAIGenerator()
        self.translator = GoogleTranslator(source="auto", target="ja")

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
            # Detect language for response formatting
            original_query = query
            detected_language = detect(query)
            is_english_input = detected_language != "ja"

            if is_english_input:
                logger.info(
                    "Detected English prompt. Translating to Japanese for search..."
                )
                query = self.translator.translate(query)
                logger.info(f"Translated prompt for search: {query}")

            # Search for relevant conversations
            search_results = self.search_engine.search_similar_conversations(
                query, limit=max_results
            )

            # Generate AI response
            ai_response = self.ai_generator.generate_response(
                query, search_results, is_english_input
            )

            # Collect file names from search results
            file_names = list({result.file_name for result in search_results})

            # Create chat response
            chat_response = ChatResponse(
                answer=ai_response["answer"],
                sources=search_results,
                query=original_query,  # Use original query in response
                timestamp=datetime.now().isoformat(),
                tokens_used=ai_response["tokens_used"],
                file_names=file_names,  # Include file names
            )

            return chat_response

        except Exception as e:
            logger.error(f"Error processing chat query: {e}")
            error_message = (
                "Sorry, an error occurred during processing."
                if "is_english_input" in locals() and is_english_input
                else "申し訳ございませんが、処理中にエラーが発生しました。"
            )
            return ChatResponse(
                answer=error_message,
                sources=[],
                query=original_query if "original_query" in locals() else query,
                timestamp=datetime.now().isoformat(),
                tokens_used=0,
                file_names=[],  # Return empty file names on error
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
                        "file_name": source.file_name,  # Include file name
                    }
                    for source in response.sources
                ],
                "query": response.query,
                "timestamp": response.timestamp,
                "tokens_used": response.tokens_used,
                "file_names": response.file_names,  # Include file names in the response
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
                "reranking": {
                    "method": chat_service.search_engine.rerank_method,
                    "cohere": (
                        "configured"
                        if chat_service.search_engine.cohere_client
                        else "not configured"
                    ),
                    "cross_encoder": (
                        "loaded"
                        if chat_service.search_engine.cross_encoder
                        else "not loaded"
                    ),
                },
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
                        "file_name": source.file_name,  # Include file name
                    }
                    for source in response.sources
                ],
                "query": response.query,
                "timestamp": response.timestamp,
                "tokens_used": response.tokens_used,
                "file_names": response.file_names,  # Include file names in the response
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
