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

    // Toggle chatbot
    header.addEventListener('click', (e) => {
        if (!e.target.closest('button')) {
            body.classList.toggle('hidden');
            toggleIcon.classList.toggle('fa-chevron-up');
            toggleIcon.classList.toggle('fa-chevron-down');
        }
    });

    // Dark mode toggle
    // Dark mode toggle
themeButton.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    const icon = themeButton.querySelector('i');
    icon.classList.toggle('fa-moon');
    icon.classList.toggle('fa-sun');
    
    // Save preference
    const isDarkMode = document.body.classList.contains('dark-mode');
    localStorage.setItem('darkMode', isDarkMode);
});

// Add this to maintain dark mode preference across page reloads
document.addEventListener('DOMContentLoaded', () => {
    const isDarkMode = localStorage.getItem('darkMode') === 'true';
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
        const icon = themeButton.querySelector('i');
        icon.classList.remove('fa-moon');
        icon.classList.add('fa-sun');
    }
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

    // Text-to-speech toggle
    ttsButton.addEventListener('click', () => {
        isVoiceEnabled = !isVoiceEnabled;
        ttsButton.classList.toggle('active');
        if (!isVoiceEnabled) {
            window.speechSynthesis.cancel(); // Stop any ongoing speech
        }
    });

    // Handle form submission
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = inputField.value.trim();
        if (!message) return;

        // Add user message
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
            
            // Add bot response
            if (data.answer) {
                addMessage(data.answer, 'bot');
                if (isVoiceEnabled) {
                    speakText(data.answer);
                }
            }
        } catch (error) {
            console.error('Error:', error);
            addMessage('Sorry, I encountered an error. Please try again.', 'error');
        }
    });

    function addMessage(text, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        const bubble = document.createElement('div');
        bubble.className = 'message-content';
        
        if (type === 'bot') {
            // Format bot messages with bullet points
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
        } else {
            bubble.textContent = text;
        }

        messageDiv.appendChild(bubble);
        messagesContainer.appendChild(messageDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function speakText(text) {
        if (!('speechSynthesis' in window)) return;

        // Cancel any ongoing speech
        window.speechSynthesis.cancel();

        // Clean text for speech
        const cleanText = text.replace(/-/g, '').replace(/\n/g, ' ');
        const utterance = new SpeechSynthesisUtterance(cleanText);
        utterance.lang = 'en-US';
        utterance.rate = 1;
        utterance.pitch = 1;

        window.speechSynthesis.speak(utterance);
    }

    // Add initial message
    addMessage("Hi! I'm your Canvas assistant. How can I help you today?", 'bot');
});