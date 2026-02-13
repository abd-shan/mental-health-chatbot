const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');


function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message');
    messageDiv.classList.add(sender === 'user' ? 'user-message' : 'bot-message');

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');
    bubble.innerText = text;

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


async function sendMessage() {
    const text = userInput.value.trim();
    if (text === '') return;


    addMessage(text, 'user');
    userInput.value = '';


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


sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});


userInput.focus();