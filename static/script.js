const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const featureBtn = document.getElementById('feature-btn');
const featurePanel = document.getElementById('feature-panel');
const pvElement = document.getElementById('pv-value');
const errorElement = document.getElementById('error-value');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const dashboard = document.getElementById('control-dashboard');


// =====================================
// Conversation Identity
// =====================================

function getConversationId() {
    let conversationId = localStorage.getItem('conversation_id');

    if (!conversationId) {
        conversationId = crypto.randomUUID();
        localStorage.setItem('conversation_id', conversationId);
    }

    return conversationId;
}


// =====================================
// Feature Panel
// =====================================

if (featureBtn && featurePanel) {
    featureBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        featurePanel.classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
        if (!featurePanel.contains(e.target) && !featureBtn.contains(e.target)) {
            featurePanel.classList.remove('show');
        }
    });
}


// =====================================
// Auto Resize Textarea
// =====================================

userInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = `${this.scrollHeight}px`;
});


// =====================================
// Message Formatter
// =====================================

function formatMessageText(text) {
    let safeText = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');

    safeText = safeText.replace(/^#+\s+/gm, '');
    safeText = safeText.replace(/^[-*]\s+/gm, '');

    safeText = safeText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    safeText = safeText.replace(/\*(?!\s)(.*?)\*(?!\s)/g, '<em>$1</em>');

    const paragraphs = safeText
        .split('\n')
        .filter(line => line.trim() !== '');

    if (paragraphs.length === 0) return '<br>';

    return paragraphs.map(p => `<p>${p}</p>`).join('');
}


function updateControlVisuals(status) {
    if (!status) return;

    const sentiment = status.sentiment_score ?? 1.0;
    const error = status.error_level ?? 0.0;


    pvElement.textContent = sentiment.toFixed(2);
    errorElement.textContent = error.toFixed(2);


    const isDisturbance = error > 0.4;

    if (isDisturbance) {
        statusDot.classList.add('error');
        statusText.textContent = 'اضطراب';
        dashboard.classList.add('disturbance');
    } else {
        statusDot.classList.remove('error');
        statusText.textContent = 'مستقر';
        dashboard.classList.remove('disturbance');
    }

}



// =====================================
// Add Message
// =====================================

function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');

    if (sender === 'bot') {
        bubble.innerHTML = formatMessageText(text);
    } else {
        bubble.innerText = text;
    }

    messageDiv.appendChild(bubble);
    messagesContainer.appendChild(messageDiv);

    messagesContainer.scrollTo({
        top: messagesContainer.scrollHeight,
        behavior: 'smooth'
    });
}


// =====================================
// Typing Indicator
// =====================================

function createTypingIndicator() {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.classList.add('message', 'bot-message');
    indicatorDiv.id = 'typing';

    const typingBubble = document.createElement('div');
    typingBubble.classList.add('typing-indicator');

    for (let i = 0; i < 3; i++) {
        const dot = document.createElement('span');
        typingBubble.appendChild(dot);
    }

    indicatorDiv.appendChild(typingBubble);

    return indicatorDiv;
}


// =====================================
// Send Message
// =====================================

async function sendMessage() {
    const text = userInput.value.trim();

    if (text === '' || sendBtn.disabled) return;

    addMessage(text, 'user');

    userInput.value = '';
    userInput.style.height = 'auto';

    sendBtn.disabled = true;

    const typingIndicator = createTypingIndicator();
    messagesContainer.appendChild(typingIndicator);

    messagesContainer.scrollTo({
        top: messagesContainer.scrollHeight,
        behavior: 'smooth'
    });

    try {
        const payload = {
            message: text,
            conversation_id: getConversationId(),

            // جاهزة للتكامل مع NestJS لاحقاً
            patient_profile: null,
            medical_context: null
        };

        const response = await fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        document.getElementById('typing')?.remove();
        
        if (response.ok) {

            if (data.status) {
                updateControlVisuals(data.status);
            }
        
            setTimeout(() => {
                addMessage(data.response, 'bot');
            }, 300);
        } else {
            addMessage('عذراً، حدث خطأ. حاول مرة أخرى.', 'bot');
         }

    } catch (error) {
        document.getElementById('typing')?.remove();
        addMessage('تعذر الاتصال بالخادم.', 'bot');
    } finally {
        sendBtn.disabled = false;
        userInput.focus();
    }
}


// =====================================
// Keyboard Events
// =====================================

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        if (e.shiftKey) {
            return;
        } else {
            e.preventDefault();
            sendMessage();
        }
    }
});


// =====================================
// Events
// =====================================

sendBtn.addEventListener('click', sendMessage);


// =====================================
// Initial Focus
// =====================================

userInput.focus();
