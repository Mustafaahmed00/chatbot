document.addEventListener('DOMContentLoaded', function() {
    const chatbotContainer = document.getElementById('chatbot-container');
    let isVoiceEnabled = false;
    
    // Initialize speech recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = SpeechRecognition ? new SpeechRecognition() : null;

    if (recognition) {
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = 'en-US';
    }
    
    // Initialize chatbot UI
    chatbotContainer.innerHTML = `
        <div class="chatbot-wrapper">
            <div class="header">
                <div class="flex items-center">
                    <i class="fas fa-robot mr-2"></i>
                    <span>Canvas Assistant</span>
                </div>
                <div class="flex items-center">
                    <button class="theme-btn mr-2">
                        <i class="fas fa-moon"></i>
                    </button>
                    <i class="fas fa-chevron-up toggle-icon"></i>
                </div>
            </div>
            
            <div class="body">
                <div class="messages"></div>
                
                <div class="input-area">
                    <form id="chat-form">
                        <div class="input-group">
                            <input type="text" placeholder="Type your message...">
                            <button type="button" class="voice-btn" aria-label="Voice input">
                                <i class="fas fa-microphone" aria-hidden="true"></i>
                            </button>
                            <button type="button" class="tts-btn" aria-label="Text to speech">
                                <i class="fas fa-volume-up" aria-hidden="true"></i>
                            </button>
                            <button type="submit" class="send-btn" aria-label="Send message">
                                <i class="fas fa-paper-plane" aria-hidden="true"></i>
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;

    // Get DOM elements
    const header = chatbotContainer.querySelector('.header');
    const body = chatbotContainer.querySelector('.body');
    const toggleIcon = chatbotContainer.querySelector('.toggle-icon');
    const messagesContainer = chatbotContainer.querySelector('.messages');
    const chatForm = document.getElementById('chat-form');
    const inputField = chatForm.querySelector('input');
    const voiceButton = chatForm.querySelector('.voice-btn');
    const ttsButton = chatForm.querySelector('.tts-btn');
    const themeButton = chatbotContainer.querySelector('.theme-btn');

    // Feedback functionality
    function createFeedbackButtons(responseId) {
        if (!responseId) return ''; // Don't show feedback for non-DB responses
        
        return `
            <div class="feedback-buttons" data-response-id="${responseId}">
                <button class="feedback-btn positive">
                    <i class="fas fa-thumbs-up"></i>
                </button>
                <button class="feedback-btn negative">
                    <i class="fas fa-thumbs-down"></i>
                </button>
            </div>
        `;
    }

    async function submitFeedback(responseId, isPositive) {
        const feedbackContainer = document.querySelector(`[data-response-id="${responseId}"]`);
        if (!feedbackContainer || feedbackContainer.classList.contains('feedback-submitted')) {
            return;
        }

        try {
            const response = await fetch('/submit_feedback', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    responseId: responseId,
                    isPositive: isPositive,
                    sessionId: generateSessionId(),
                    metadata: {
                        timestamp: new Date().toISOString(),
                        userAgent: navigator.userAgent
                    }
                })
            });

            if (response.ok) {
                feedbackContainer.innerHTML = '<p class="feedback-thank-you">Thank you for your feedback!</p>';
                feedbackContainer.classList.add('feedback-submitted');
            } else {
                console.error('Failed to submit feedback');
            }
        } catch (error) {
            console.error('Error submitting feedback:', error);
        }
    }

    function generateSessionId() {
        return 'session_' + Math.random().toString(36).substr(2, 9);
    }

    // Message handling
    function addMessage(text, type, responseId = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        const bubble = document.createElement('div');
        bubble.className = 'message-content';
        
        if (type === 'bot') {
            const lines = text.split('\n').map(line => {
                line = line.trim();
                if (line.startsWith('-')) {
                    return `<li>${line.substring(1).trim()}</li>`;
                }
                return `<p>${line}</p>`;
            });

            const hasBullets = lines.some(line => line.includes('<li>'));
            bubble.innerHTML = hasBullets 
                ? `<ul>${lines.join('')}</ul>` 
                : lines.join('');
                
            // Add feedback buttons for bot messages
            if (responseId) {
                const feedbackHtml = createFeedbackButtons(responseId);
                bubble.innerHTML += feedbackHtml;

                // Add event listeners after the buttons are added to the DOM
                setTimeout(() => {
                    const feedbackContainer = bubble.querySelector('.feedback-buttons');
                    if (feedbackContainer) {
                        const positiveBtn = feedbackContainer.querySelector('.positive');
                        const negativeBtn = feedbackContainer.querySelector('.negative');
                        
                        positiveBtn.addEventListener('click', () => submitFeedback(responseId, true));
                        negativeBtn.addEventListener('click', () => submitFeedback(responseId, false));
                    }
                }, 0);
            }
        } else {
            bubble.textContent = text;
        }

        
    messageDiv.appendChild(bubble);
    messagesContainer.appendChild(messageDiv);
    
    // Scroll calculation
    const messageHeight = messageDiv.offsetHeight;
    const containerHeight = messagesContainer.offsetHeight;
    const scrollPosition = messagesContainer.scrollTop;
    const totalScrollHeight = messagesContainer.scrollHeight;
    
    // If it's a bot message, scroll to show just the start of the message
    if (type === 'bot') {
        const newScrollPosition = totalScrollHeight - containerHeight - messageHeight;
        messagesContainer.scrollTop = newScrollPosition;
    } else {
        // For user messages, scroll to bottom as before
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

    // Event listeners
    header.addEventListener('click', (e) => {
        if (!e.target.closest('button')) {
            body.classList.toggle('hidden');
            toggleIcon.classList.toggle('fa-chevron-up');
            toggleIcon.classList.toggle('fa-chevron-down');
        }
    });

    themeButton.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        const icon = themeButton.querySelector('i');
        icon.classList.toggle('fa-moon');
        icon.classList.toggle('fa-sun');
        
        const isDarkMode = document.body.classList.contains('dark-mode');
        localStorage.setItem('darkMode', isDarkMode);
    });

    // Voice input handling
    if (recognition) {
        voiceButton.addEventListener('click', () => {
            if (voiceButton.classList.contains('recording')) {
                recognition.stop();
            } else {
                recognition.start();
            }
        });

        recognition.onstart = () => {
            voiceButton.classList.add('recording');
            voiceButton.querySelector('i').classList.remove('fa-microphone');
            voiceButton.querySelector('i').classList.add('fa-stop');
            inputField.placeholder = 'Listening...';
        };

        recognition.onend = () => {
            voiceButton.classList.remove('recording');
            voiceButton.querySelector('i').classList.remove('fa-stop');
            voiceButton.querySelector('i').classList.add('fa-microphone');
            inputField.placeholder = 'Type your message...';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            inputField.value = transcript;
            chatForm.dispatchEvent(new Event('submit'));
        };

        recognition.onerror = (event) => {
            console.error('Speech recognition error:', event.error);
            addMessage('Failed to recognize speech. Please try again.', 'error');
            recognition.stop();
        };
    } else {
        voiceButton.style.display = 'none';
    }

    // Text-to-speech handling
    function speakText(text) {
        if (!('speechSynthesis' in window)) return;

        window.speechSynthesis.cancel();
        const cleanText = text.replace(/-/g, '').replace(/\n/g, ' ');
        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = 'en-US';
        utterance.rate = 1;
        utterance.pitch = 1;

        window.speechSynthesis.speak(utterance);
    }

    ttsButton.addEventListener('click', () => {
        isVoiceEnabled = !isVoiceEnabled;
        ttsButton.classList.toggle('active');
        if (!isVoiceEnabled) {
            window.speechSynthesis.cancel();
        }
    });

    // Form submission
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = inputField.value.trim();
        if (!message) return;

        addMessage(message, 'user');
        inputField.value = '';

        try {
            const response = await fetch('/get_response', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `message=${encodeURIComponent(message)}`
            });

            const data = await response.json();
            
            if (data.answer) {
                addMessage(data.answer, 'bot', data.responseId);
                if (isVoiceEnabled) {
                    speakText(data.answer);
                }
            }
        } catch (error) {
            console.error('Error:', error);
            addMessage('Sorry, I encountered an error. Please try again.', 'error');
        }
    });

    // Initialize dark mode if previously set
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
        const icon = themeButton.querySelector('i');
        icon.classList.remove('fa-moon');
        icon.classList.add('fa-sun');
    }

    // Add initial message
    addMessage("Hi! I'm your Canvas assistant. How can I help you today?", 'bot');
});