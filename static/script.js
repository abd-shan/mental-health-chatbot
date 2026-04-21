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
    const paragraphs = safeText.split('\n').filter(line => line.trim() !== '');
    if (paragraphs.length === 0) return '<br>';
    return paragraphs.map(p => `<p>${p}</p>`).join('');
}

// =====================================
// متغيرات التحكم والتنعيم (EMA + RAF)
// =====================================
let displayPV = 1.0;
let displayError = 0.0;
let targetPV = 1.0;
let targetError = 0.0;
let animFrame = null;
const ALPHA = 0.12;

function smoothUpdate(newPV, newError) {
    targetPV = newPV;
    targetError = newError;
    if (!animFrame) {
        animFrame = requestAnimationFrame(updateCounters);
    }
}

function updateCounters() {
    displayPV = displayPV + ALPHA * (targetPV - displayPV);
    displayError = displayError + ALPHA * (targetError - displayError);

    pvElement.textContent = displayPV.toFixed(3);
    errorElement.textContent = displayError.toFixed(3);

    const errorClamped = Math.min(displayError, 1.0);
    const hue = 120 * (1 - errorClamped);
    const color = `hsl(${hue}, 85%, 55%)`;
    statusDot.style.backgroundColor = color;
    statusDot.style.boxShadow = `0 0 15px ${color}`;

    if (displayError > 0.55) {
        statusText.textContent = 'خطر';
        dashboard.classList.add('disturbance');
    } else if (displayError > 0.25) {
        statusText.textContent = 'انتباه';
        dashboard.classList.remove('disturbance');
    } else {
        statusText.textContent = 'مستقر';
        dashboard.classList.remove('disturbance');
    }

    const diffPV = Math.abs(targetPV - displayPV);
    const diffErr = Math.abs(targetError - displayError);

    if (diffPV > 0.001 || diffErr > 0.001) {
        animFrame = requestAnimationFrame(updateCounters);
    } else {
        animFrame = null;
        pvElement.textContent = targetPV.toFixed(3);
        errorElement.textContent = targetError.toFixed(3);
    }
}

function updateControlVisuals(status) {
    if (!status) return;
    const sentiment = status.sentiment_score ?? 1.0;
    const error = status.error_level ?? 0.0;
    smoothUpdate(sentiment, error);
    // حفظ الحالة في localStorage
    localStorage.setItem('last_dashboard_state', JSON.stringify({ pv: sentiment, error: error }));
}

// =====================================
// Add Message (مع حفظ تلقائي)
// =====================================
function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', sender === 'user' ? 'user-message' : 'bot-message');

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

    saveChatHistory();
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
    messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: 'smooth' });

    try {
        const payload = {
            message: text,
            conversation_id: getConversationId(),
            patient_profile: null,
            medical_context: null
        };

        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        document.getElementById('typing')?.remove();

        if (response.ok) {
            if (data.status) {
                updateControlVisuals(data.status);
            }
            setTimeout(() => addMessage(data.response, 'bot'), 300);
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
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn.addEventListener('click', sendMessage);

// =====================================
// LocalStorage: Chat History
// =====================================
const STORAGE_KEY = 'chat_history';

function saveChatHistory() {
    const messages = [];
    document.querySelectorAll('.message').forEach(msgDiv => {
        const isUser = msgDiv.classList.contains('user-message');
        const bubble = msgDiv.querySelector('.bubble');
        if (bubble) {
            messages.push({
                text: bubble.innerText,
                sender: isUser ? 'user' : 'bot'
            });
        }
    });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
}

function loadChatHistory() {
    // إزالة جميع الرسائل الحالية
    while (messagesContainer.firstChild) {
        messagesContainer.removeChild(messagesContainer.firstChild);
    }

    // إعادة إضافة الرسالة الترحيبية الافتراضية
    const welcomeDiv = document.createElement('div');
    welcomeDiv.classList.add('message', 'bot-message');
    const welcomeBubble = document.createElement('div');
    welcomeBubble.classList.add('bubble');
    welcomeBubble.innerText = 'مرحباً! كيف يمكنني مساعدتك اليوم؟';
    welcomeDiv.appendChild(welcomeBubble);
    messagesContainer.appendChild(welcomeDiv);

    // تحميل المحادثة المحفوظة (إن وجدت)
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
        try {
            const messages = JSON.parse(saved);
            // تجاهل الرسالة الترحيبية المحفوظة إذا كانت مطابقة للافتراضية
            const filtered = messages.filter(msg => msg.text !== 'مرحباً! كيف يمكنني مساعدتك اليوم؟');
            filtered.forEach(msg => addMessage(msg.text, msg.sender));
        } catch (e) {
            console.error("Failed to load chat history:", e);
        }
    }

    // استعادة حالة لوحة التحكم
    const savedState = localStorage.getItem('last_dashboard_state');
    if (savedState) {
        try {
            const state = JSON.parse(savedState);
            updateControlVisuals({ sentiment_score: state.pv, error_level: state.error });
        } catch (e) {}
    }

    saveChatHistory(); // مزامنة
}

function clearChatHistory() {
    localStorage.removeItem(STORAGE_KEY);
    // إعادة تعيين الواجهة: الاحتفاظ بالترحيب فقط
    while (messagesContainer.firstChild) {
        messagesContainer.removeChild(messagesContainer.firstChild);
    }
    const welcomeDiv = document.createElement('div');
    welcomeDiv.classList.add('message', 'bot-message');
    const welcomeBubble = document.createElement('div');
    welcomeBubble.classList.add('bubble');
    welcomeBubble.innerText = 'مرحباً! كيف يمكنني مساعدتك اليوم؟';
    welcomeDiv.appendChild(welcomeBubble);
    messagesContainer.appendChild(welcomeDiv);
    saveChatHistory();
}

// =====================================
// إضافة زر إعادة الضبط (Reset) بشكل ديناميكي
// =====================================
function addControlButtons() {
    const container = document.querySelector('.container');
    const btnContainer = document.createElement('div');
    btnContainer.className = 'control-buttons';
    btnContainer.innerHTML = `
        <button id="reset-chat" class="icon-btn" title="مسح المحادثة">🗑️</button>
        <button id="reset-system" class="icon-btn" title="إعادة ضبط النظام">🔄</button>
    `;
    container.appendChild(btnContainer);

    document.getElementById('reset-chat').addEventListener('click', () => {
        if (confirm('هل تريد مسح سجل المحادثة؟')) {
            clearChatHistory();
        }
    });

    document.getElementById('reset-system').addEventListener('click', () => {
        // إعادة ضبط قيم لوحة التحكم إلى الوضع الافتراضي
        updateControlVisuals({ sentiment_score: 1.0, error_level: 0.0 });
        localStorage.removeItem('last_dashboard_state');
        // لا نمسح المحادثة، فقط نعيد المؤشرات
    });
}

// =====================================
// إضافة تلميحات توضيحية للوحة التحكم (Tooltips)
// =====================================
function addDashboardTooltips() {
    const pvLabel = document.querySelector('.metric:first-child .metric-label');
    const errorLabel = document.querySelector('.metric:nth-child(2) .metric-label');
    const statusIndicator = document.querySelector('.status-indicator');

    pvLabel.setAttribute('title', 'Process Variable: مستوى الهدوء الحالي بعد المعالجة الرقمية');
    errorLabel.setAttribute('title', 'Error = Setpoint - PV: مقدار الانحراف عن الهدف (1.0)');
    statusIndicator.setAttribute('title', 'حالة النظام: مستقر (خطأ منخفض) / انتباه / خطر');
}

// =====================================
// بدء التشغيل
// =====================================
window.addEventListener('DOMContentLoaded', () => {
    loadChatHistory();
    addControlButtons();
    addDashboardTooltips();
    userInput.focus();
});
