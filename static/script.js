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


// ====================== إضافة المتغيرات العامة في بداية الملف ======================
let displayPV = 1.0;        // القيمة المعروضة حالياً للـ PV (بعد التنعيم)
let displayError = 0.0;     // القيمة المعروضة حالياً للـ Error (بعد التنعيم)
let targetPV = 1.0;         // القيمة الهدف القادمة من السيرفر
let targetError = 0.0;      // قيمة الخطأ القادمة من السيرفر
let animFrame = null;       // مؤشر إطار الرسوم المتحركة
const ALPHA = 0.12;         // معامل التنعيم (كلما قل كان التنعيم أبطأ وأكثر سلاسة)

// =====================================
// دالة التنعيم والرسوم المتحركة (EMA + RAF)
// =====================================
function smoothUpdate(newPV, newError) {
    // تحديث القيم الهدف
    targetPV = newPV;
    targetError = newError;

    // إذا لم تكن هناك حركة متحركة نشطة، ابدأ واحدة
    if (!animFrame) {
        animFrame = requestAnimationFrame(updateCounters);
    }
}

function updateCounters() {
    // تطبيق Exponential Moving Average
    displayPV = displayPV + ALPHA * (targetPV - displayPV);
    displayError = displayError + ALPHA * (targetError - displayError);

    // تحديث عناصر HTML بالقيم الجديدة (بتنسيق رقمي)
    pvElement.textContent = displayPV.toFixed(3);
    errorElement.textContent = displayError.toFixed(3);

    // ===== تطبيق الألوان المتدرجة (Gradient) =====
    // تحويل قيمة الخطأ (0.0 إلى 1.0) إلى درجة لون من الأخضر (120) إلى الأحمر (0)
    // نربط الخطأ بـ HSL: Hue = 120 * (1 - min(error, 1.0))
    const errorClamped = Math.min(displayError, 1.0);
    const hue = 120 * (1 - errorClamped); // 120 = أخضر، 0 = أحمر
    const saturation = 85;
    const lightness = 55;

    // تطبيق اللون على النقطة والنص
    const color = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    statusDot.style.backgroundColor = color;
    statusDot.style.boxShadow = `0 0 15px ${color}`;

    // تغيير نص الحالة بناءً على الخطأ
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

    // التحقق من الوصول إلى الهدف (بفارق بسيط) لإنهاء الأنيميشن
    const diffPV = Math.abs(targetPV - displayPV);
    const diffErr = Math.abs(targetError - displayError);

    if (diffPV > 0.001 || diffErr > 0.001) {
        // استمرار الحركة
        animFrame = requestAnimationFrame(updateCounters);
    } else {
        // إنهاء الحركة
        animFrame = null;
        // ضبط القيمة النهائية بدقة
        pvElement.textContent = targetPV.toFixed(3);
        errorElement.textContent = targetError.toFixed(3);
    }
}

// =====================================
// تعديل دالة updateControlVisuals لاستدعاء نظام التنعيم
// =====================================
function updateControlVisuals(status) {
    if (!status) return;

    const sentiment = status.sentiment_score ?? 1.0;
    const error = status.error_level ?? 0.0;

    // بدلاً من التحديث المباشر، نرسل القيم إلى نظام التنعيم
    smoothUpdate(sentiment, error);
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
