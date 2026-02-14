const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const featureBtn = document.getElementById('feature-btn');
const featurePanel = document.getElementById('feature-panel');


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


userInput.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
});


async function sendMessage() {
    const text = userInput.value.trim();
    if (text === '') return;

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
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });

        const data = await response.json();

        document.getElementById('typing')?.remove();

        if (response.ok) {
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


function formatMessageText(text) {
    let safeText = text.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    safeText = safeText.replace(/^#+\s+/gm, ''); // إزالة علامات العناوين
    safeText = safeText.replace(/^[-*]\s+/gm, ''); // إزالة علامات القوائم
    safeText = safeText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    safeText = safeText.replace(/\*(?!\s)(.*?)\*(?!\s)/g, '<em>$1</em>');
    const paragraphs = safeText.split('\n').filter(line => line.trim() !== '');
    if (paragraphs.length === 0) return '<br>';
    return paragraphs.map(p => `<p>${p}</p>`).join('');
}


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


sendBtn.addEventListener('click', sendMessage);


userInput.focus();