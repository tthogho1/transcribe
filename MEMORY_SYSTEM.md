# Memory System Documentation

## Overview

This document describes the short-term session memory system for the Flask-SocketIO chatbot. The system maintains conversation history across multiple turns, allowing the chatbot to remember context and provide more coherent responses.

## Architecture

### Session Storage

The system uses a dual-storage approach for maximum reliability:

- **Primary Storage**: Redis (production-grade, persistent, distributed)
- **Fallback Storage**: In-memory dictionary (development, automatic fallback)
- **Automatic Failover**: If Redis is unavailable, the system automatically falls back to in-memory storage

### Storage Selection Logic

```python
try:
    # Attempt Redis connection
    redis_client = redis.from_url(REDIS_URL)
    redis_client.ping()
    storage_type = "redis"
except:
    # Fall back to in-memory
    storage_type = "memory"
```

## Memory Management

### Conversation Limits

- **Max Turns**: 20 conversation turns (10 user + 10 assistant messages)
- **Max Tokens**: 4,000 tokens (~16,000 characters)
- **Session TTL**: 30 minutes of idle time
- **Trimming Strategy**: Sliding window (oldest messages removed first)

### Token Counting

The system uses an approximate token counting method:
```
tokens ≈ text_length / 4
```

For precise token counting with specific models, consider integrating tiktoken.

### Trimming Behavior

When limits are exceeded:

1. **By Turns**: Keep only the most recent 20 turns
2. **By Tokens**: Remove oldest messages until under 4,000 tokens
3. **Minimum**: Always keep at least 2 messages (1 turn)

## Integration with RAG

### Context Window Allocation

For OpenAI GPT-3.5-turbo (4K context) or GPT-4 (8K context):

| Component | Tokens | Description |
|-----------|--------|-------------|
| System Prompt | ~500 | Instructions for the model |
| RAG Context | ~2,000 | Relevant excerpts from Zilliz |
| Conversation History | ~4,000 | Recent conversation turns |
| Current Query | ~100 | User's question |
| Response Buffer | ~1,400 | Model's response |

### Priority Strategy

When building prompts:

1. **System Prompt**: Always included (highest priority)
2. **Conversation History**: Recent turns (high priority)
3. **RAG Context**: Semantic search results (medium priority)
4. **Current Query**: User's question (required)

The model sees: `System + History + RAG + Query`

## API Reference

### POST /api/chat

Chat with the bot using REST API with automatic session management.

**Request:**
```json
{
  "query": "今日の天気は？",
  "user_id": "optional-user-id"
}
```

**Response:**
```json
{
  "answer": "今日は晴れです。",
  "sources": [...],
  "query": "今日の天気は？",
  "timestamp": "2026-01-31T10:00:00Z",
  "tokens_used": 150,
  "file_names": ["source.json"],
  "user_id": "uuid-or-provided-id"
}
```

### SocketIO: chat_message

Chat via WebSocket (uses `request.sid` as user_id).

**Emit:**
```javascript
socket.emit("chat_message", {
  query: "こんにちは"
});
```

**Receive:**
```javascript
socket.on("chat_response", (data) => {
  console.log(data.answer);
});
```

### POST /api/session/clear

Clear conversation history for a user.

**Request:**
```json
{
  "user_id": "user-id-here"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Session cleared for user-id-here"
}
```

### POST /api/session/export

Export complete conversation history.

**Request:**
```json
{
  "user_id": "user-id-here"
}
```

**Response:**
```json
{
  "user_id": "user-id-here",
  "created_at": "2026-01-31T09:30:00Z",
  "last_accessed": "2026-01-31T10:00:00Z",
  "total_tokens": 150,
  "messages": [
    {
      "role": "user",
      "content": "こんにちは",
      "timestamp": "2026-01-31T09:30:00Z",
      "tokens": 5
    },
    {
      "role": "assistant",
      "content": "こんにちは！",
      "timestamp": "2026-01-31T09:30:05Z",
      "tokens": 5
    }
  ]
}
```

### GET /api/session/stats

Get session manager statistics.

**Response:**
```json
{
  "storage_type": "redis",
  "active_sessions": 42,
  "expiry_seconds": 1800,
  "max_turns": 20,
  "max_tokens": 4000
}
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Session Management
REDIS_URL=redis://localhost:6379/0
SESSION_EXPIRY_SECONDS=1800
MAX_CONVERSATION_TURNS=20
MAX_CONVERSATION_TOKENS=4000
```

### Adjusting Memory Limits

**For GPT-3.5-turbo (4K context):**
```bash
MAX_CONVERSATION_TOKENS=4000  # Conservative
```

**For GPT-4 (8K+ context):**
```bash
MAX_CONVERSATION_TOKENS=8000  # More history
```

**For shorter conversations:**
```bash
MAX_CONVERSATION_TURNS=10  # 5 back-and-forth turns
```

## What the Chatbot Remembers

### Within a Session (30 minutes)

✅ **User preferences** mentioned in conversation
✅ **Previous questions and answers**
✅ **Context from earlier turns**
✅ **Names, dates, and facts** discussed
✅ **Follow-up context** ("それについて教えて")

### What Gets Forgotten

❌ **After 30 minutes** of inactivity (session expires)
❌ **Beyond 20 turns** (oldest messages trimmed)
❌ **Beyond 4,000 tokens** (oldest messages trimmed)
❌ **After manual session clear** (user-initiated)
❌ **Across different user_ids** (sessions are isolated)

## Usage Examples

### Example 1: Simple Conversation

```python
import requests

# First message
response1 = requests.post("http://localhost:7860/api/chat", json={
    "query": "私の名前は太郎です",
    "user_id": "user123"
})

# Follow-up (bot remembers name)
response2 = requests.post("http://localhost:7860/api/chat", json={
    "query": "私の名前は何ですか？",
    "user_id": "user123"
})

print(response2.json()["answer"])  # Should mention "太郎"
```

### Example 2: Clear Session

```python
# Clear conversation history
requests.post("http://localhost:7860/api/session/clear", json={
    "user_id": "user123"
})
```

### Example 3: Export History

```python
# Export for analysis
response = requests.post("http://localhost:7860/api/session/export", json={
    "user_id": "user123"
})

history = response.json()
for msg in history["messages"]:
    print(f"{msg['role']}: {msg['content']}")
```

## Development Guidelines

### Testing with Memory

When writing tests that use session memory:

```python
def test_with_memory():
    user_id = f"test_{int(time.time() * 1000)}"  # Unique ID

    # Send messages
    response1 = chat_with_memory(query="Hello", user_id=user_id)
    response2 = chat_with_memory(query="What did I say?", user_id=user_id)

    # Clean up
    clear_session(user_id)
```

### Debugging Memory Issues

Enable debug logging:
```bash
LOG_LEVEL=DEBUG
```

Check session status:
```bash
curl http://localhost:7860/api/session/stats
```

Inspect specific session:
```bash
curl -X POST http://localhost:7860/api/session/export \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123"}'
```

## Troubleshooting

### Problem: Sessions Not Persisting

**Symptoms**: Bot doesn't remember previous messages

**Causes & Solutions**:

1. **Different user_ids**: Ensure you're using the same `user_id` across requests
   ```python
   # ❌ Wrong: new ID each time
   response = chat(query="Hi")  # auto-generates new ID

   # ✅ Correct: consistent ID
   user_id = "user123"
   response = chat(query="Hi", user_id=user_id)
   ```

2. **Session expired**: Default 30 minutes idle timeout
   - Check `SESSION_EXPIRY_SECONDS` in `.env`
   - Increase if needed: `SESSION_EXPIRY_SECONDS=3600`

3. **Redis unavailable**: Check logs for "using in-memory storage"
   - Verify Redis is running: `redis-cli ping`
   - Check `REDIS_URL` in `.env`

### Problem: Token Limit Exceeded

**Symptoms**: Error "maximum context length exceeded"

**Solutions**:

1. **Reduce history tokens**:
   ```bash
   MAX_CONVERSATION_TOKENS=2000  # More aggressive trimming
   ```

2. **Reduce conversation turns**:
   ```bash
   MAX_CONVERSATION_TURNS=10  # Fewer messages kept
   ```

3. **Clear old sessions**:
   ```python
   requests.post("/api/session/clear", json={"user_id": user_id})
   ```

### Problem: Memory Usage Growing

**Symptoms**: High memory usage over time (in-memory mode)

**Solutions**:

1. **Use Redis** instead of in-memory:
   ```bash
   REDIS_URL=redis://localhost:6379/0
   ```

2. **Reduce session expiry**:
   ```bash
   SESSION_EXPIRY_SECONDS=900  # 15 minutes
   ```

3. **Monitor sessions**:
   ```bash
   watch -n 5 'curl -s http://localhost:7860/api/session/stats'
   ```

### Problem: Redis Connection Errors

**Symptoms**: "Redis unavailable" in logs

**Solutions**:

1. **System uses automatic fallback** to in-memory (no action needed for basic functionality)

2. **Fix Redis connection** for production:
   ```bash
   # Check Redis is running
   redis-cli ping  # Should return "PONG"

   # Install Redis if needed
   brew install redis  # macOS
   sudo apt install redis  # Linux

   # Start Redis
   brew services start redis  # macOS
   sudo systemctl start redis  # Linux
   ```

3. **Update REDIS_URL** if using remote Redis:
   ```bash
   REDIS_URL=redis://username:password@host:6379/0
   ```

## Best Practices

### 1. User ID Management

**DO:**
- Generate UUID for new users: `str(uuid.uuid4())`
- Store user_id on client side (localStorage, cookie)
- Use consistent user_id across requests

**DON'T:**
- Use sensitive data as user_id
- Share user_ids between different users
- Rely on auto-generation for persistent sessions

### 2. Session Lifecycle

**DO:**
- Offer users a "Clear History" button
- Explain memory limits in UI
- Export history for users on request

**DON'T:**
- Store sensitive data without user consent
- Keep sessions indefinitely
- Mix conversation contexts

### 3. Production Deployment

**DO:**
- Use Redis for multi-instance deployments
- Monitor Redis memory usage
- Set up Redis persistence (RDB/AOF)
- Configure Redis maxmemory-policy

**DON'T:**
- Rely on in-memory mode in production
- Ignore Redis connection errors
- Skip Redis backups

### 4. Performance Optimization

**DO:**
- Use connection pooling for Redis
- Monitor token usage trends
- Cache session reads when possible

**DON'T:**
- Fetch session on every request unnecessarily
- Store large binary data in sessions
- Ignore memory cleanup

## Monitoring

### Key Metrics to Track

1. **Active Sessions**: Number of concurrent users
2. **Storage Type**: Redis vs in-memory
3. **Average Tokens**: Per session
4. **Session Duration**: How long users chat
5. **Memory Usage**: Redis memory consumption

### Health Check

```bash
curl http://localhost:7860/health | jq '.services'
```

Expected output:
```json
{
  "zilliz": "connected",
  "openai": "configured",
  "session_storage": "redis",
  "active_sessions": 42,
  "reranking": {...}
}
```

## Security Considerations

### Data Privacy

- Sessions expire automatically after 30 minutes
- No persistent storage of conversations (unless using Redis with persistence)
- Sessions isolated by user_id
- No cross-user data leakage

### Recommendations

1. **Encrypt Redis connections** in production:
   ```bash
   REDIS_URL=rediss://user:pass@host:6380/0  # Note: rediss (TLS)
   ```

2. **Implement rate limiting** to prevent abuse

3. **Add authentication** if exposing publicly

4. **Sanitize user inputs** before storing

5. **Comply with data retention policies** (GDPR, etc.)

## Future Enhancements

Potential improvements to consider:

- **Persistent long-term memory** (beyond 30 minutes)
- **User profiles** with preferences
- **Conversation branching** (tree structure)
- **Semantic compression** of old messages
- **Multi-modal memory** (images, files)
- **Cross-session context** (with user consent)

## Support

For issues or questions:

1. Check this documentation first
2. Review logs: `docker logs <container>` or check console output
3. Test with minimal examples
4. Report issues with full error messages and environment details

---

**Version**: 1.0
**Last Updated**: 2026-01-31
**Compatibility**: Flask 3.0+, OpenAI 1.58+, Redis 5.0+
