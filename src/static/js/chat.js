// Chat Interface JavaScript
class ChatInterface {
  constructor() {
    this.socket = io();
    this.messagesDiv = document.getElementById('messages');
    this.messageInput = document.getElementById('messageInput');
    this.sendButton = document.getElementById('sendButton');
    this.sourcesContent = document.getElementById('sourcesContent');

    this.initializeEventListeners();
    this.initializeSocketHandlers();

    // Focus input on load
    this.messageInput.focus();
  }

  initializeEventListeners() {
    // Send button click
    this.sendButton.addEventListener('click', () => this.sendMessage());

    // Enter key press
    this.messageInput.addEventListener('keypress', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    // Input validation
    this.messageInput.addEventListener('input', () => {
      this.sendButton.disabled = !this.messageInput.value.trim();
    });
  }

  initializeSocketHandlers() {
    this.socket.on('connect', () => {
      console.log('Connected to chat server');
      this.updateConnectionStatus(true);
    });

    this.socket.on('disconnect', () => {
      console.log('Disconnected from chat server');
      this.updateConnectionStatus(false);
    });

    this.socket.on('chat_response', data => {
      this.handleChatResponse(data);
    });

    this.socket.on('chat_error', data => {
      this.handleChatError(data);
    });

    this.socket.on('status', data => {
      console.log('Server status:', data.message);
    });
  }

  updateConnectionStatus(connected) {
    const header = document.querySelector('.header p');
    if (connected) {
      header.textContent =
        'Ask questions about past conversations - AI will search and provide context-aware answers';
      header.style.opacity = '0.9';
    } else {
      header.textContent = 'Connection lost - Please refresh the page';
      header.style.opacity = '0.7';
    }
  }

  addMessage(content, isUser = false, timestamp = null, tokens = null, related = null) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;

    let html = `<strong>${isUser ? 'You' : 'AI Assistant'}:</strong> ${this.formatMessage(
      content
    )}`;

    if (timestamp) {
      html += `<span class="timestamp">${this.formatTime(timestamp)}</span>`;
    }

    if (tokens) {
      html += `<span class="tokens">Tokens: ${tokens}</span>`;
    }

    if (related) {
      console.log('Related videos:', related);
      const youtubeURL = 'https://www.youtube.com/watch?v=';
      html += `<br><span class="related">Related:</span><br>`;
      related.forEach(item => {
        const youtubeId = item.replace(/\.json$/, '');
        html += `<a href="${youtubeURL + youtubeId}" class="related-item">${
          youtubeURL + youtubeId
        }</a><br>`;
      });
    }

    messageDiv.innerHTML = html;
    this.messagesDiv.appendChild(messageDiv);
    this.scrollToBottom();
  }

  formatMessage(content) {
    // Basic formatting for message content
    return content
      .replace(/\n/g, '<br>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>');
  }

  formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString('ja-JP', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  }

  updateSources(sources) {
    if (!sources || sources.length === 0) {
      this.sourcesContent.innerHTML = `
                <p style="color: #888; font-style: italic;">
                    検索結果がありませんでした。
                </p>
            `;
      return;
    }

    let html = '';
    sources.forEach((source, index) => {
      const scoreClass = source.score > 0.8 ? 'high' : source.score > 0.6 ? 'medium' : 'low';

      html += `
                <div class="source-item" data-index="${index}">
                    <div class="source-meta">
                        <div>
                            <span class="speaker-badge">${this.escapeHtml(source.speaker)}</span>
                            <span class="score-badge">${source.score.toFixed(3)}</span>
                        </div>
                        <div style="font-size: 10px; color: #999;">
                            ${
                              source.timestamp
                                ? this.formatTimestamp(source.timestamp)
                                : 'No timestamp'
                            }
                        </div>
                    </div>
                    <div class="source-text">${this.escapeHtml(source.text)}</div>
                </div>
            `;
    });

    this.sourcesContent.innerHTML = html;

    // Add click handlers for source items
    this.sourcesContent.querySelectorAll('.source-item').forEach(item => {
      item.addEventListener('click', () => {
        item.style.background = '#e3f2fd';
        setTimeout(() => {
          item.style.background = '#f8f9fa';
        }, 200);
      });
    });
  }

  formatTimestamp(timestamp) {
    try {
      return new Date(timestamp).toLocaleString('ja-JP', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (e) {
      return timestamp;
    }
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  sendMessage() {
    const message = this.messageInput.value.trim();
    if (!message) return;

    // Add user message to UI
    this.addMessage(message, true);

    // Clear input and update UI state
    this.messageInput.value = '';
    this.setLoadingState(true);

    // Send to server
    this.socket.emit('chat_message', {
      query: message,
      timestamp: new Date().toISOString(),
    });
  }

  setLoadingState(loading) {
    this.sendButton.disabled = loading;
    this.sendButton.textContent = loading ? 'Thinking...' : 'Send';
    this.messageInput.disabled = loading;

    if (loading) {
      this.sendButton.classList.add('loading');
      this.showTypingIndicator();
    } else {
      this.sendButton.classList.remove('loading');
      this.hideTypingIndicator();
      this.messageInput.focus();
    }
  }

  showTypingIndicator() {
    const typingDiv = document.createElement('div');
    typingDiv.id = 'typing-indicator';
    typingDiv.className = 'message ai-message';
    typingDiv.innerHTML = '<strong>AI Assistant:</strong> <em>考えています...</em>';
    typingDiv.style.opacity = '0.7';

    this.messagesDiv.appendChild(typingDiv);
    this.scrollToBottom();
  }

  hideTypingIndicator() {
    const typingIndicator = document.getElementById('typing-indicator');
    if (typingIndicator) {
      typingIndicator.remove();
    }
  }

  handleChatResponse(data) {
    this.hideTypingIndicator();
    this.addMessage(data.answer, false, data.timestamp, data.tokens_used, data.file_names);
    this.updateSources(data.sources);
    this.setLoadingState(false);

    // Log response for debugging
    console.log('Chat response received:', {
      query: data.query,
      sourcesCount: data.sources?.length || 0,
      tokensUsed: data.tokens_used,
    });
  }

  handleChatError(data) {
    this.hideTypingIndicator();
    this.addMessage(`エラーが発生しました: ${data.error}`, false);
    this.setLoadingState(false);

    console.error('Chat error:', data.error);
  }

  scrollToBottom() {
    this.messagesDiv.scrollTop = this.messagesDiv.scrollHeight;
  }

  // Public methods for external access
  clearChat() {
    this.messagesDiv.innerHTML = `
            <div class="message ai-message">
                <strong>AI Assistant:</strong> こんにちは！過去の会話を検索して質問にお答えします。何でもお聞きください。
            </div>
        `;
    this.sourcesContent.innerHTML = `
            <p style="color: #888; font-style: italic;">
                質問すると、関連する会話の検索結果がここに表示されます。
            </p>
        `;
  }

  exportChatHistory() {
    const messages = Array.from(this.messagesDiv.querySelectorAll('.message')).map(msg => {
      return {
        content: msg.textContent,
        timestamp: new Date().toISOString(),
        type: msg.classList.contains('user-message') ? 'user' : 'ai',
      };
    });

    const blob = new Blob([JSON.stringify(messages, null, 2)], {
      type: 'application/json',
    });

    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat-history-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
}

// Initialize chat interface when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  window.chatInterface = new ChatInterface();

  // Add keyboard shortcuts
  document.addEventListener('keydown', e => {
    // Ctrl+L to clear chat
    if (e.ctrlKey && e.key === 'l') {
      e.preventDefault();
      window.chatInterface.clearChat();
    }

    // Ctrl+E to export chat history
    if (e.ctrlKey && e.key === 'e') {
      e.preventDefault();
      window.chatInterface.exportChatHistory();
    }
  });
});

// Export for external use
window.ChatInterface = ChatInterface;
