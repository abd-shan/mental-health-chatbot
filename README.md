# Aoun AI Service

خدمة AI داخلية لمنصة عون، مبنية بـFastAPI وLangChain وتتصل بـOpenRouter. لا
يجب نشر منفذها للإنترنت؛ الباك إند الرئيسي هو العميل الوحيد لمسارات `/api/v1`.

> الخدمة تقدم دعماً عاماً وليست أداة تشخيص أو بديلاً عن المختص أو الطوارئ.

## البنية

```text
Frontend -> Main Backend -> http://127.0.0.1:8000/api/v1 -> OpenRouter
```

الباك إند الرئيسي يملك المستخدمين والمحادثات والرسائل والملخصات. خدمة AI تحتفظ
بذاكرة مؤقتة فقط، ويمكن حذفها دون فقدان السجل الدائم.

## إعداد الإنتاج

انسخ `.env.example` إلى `.env` واضبط على الأقل:

```env
APP_ENV=production
ENABLE_TEST_UI=false
ENABLE_API_DOCS=false
OPENROUTER_API_KEY=replace_me
OPENROUTER_MODEL=deepseek/deepseek-chat
OPENROUTER_SUMMARY_MODEL=deepseek/deepseek-chat
AI_SERVICE_API_KEY=replace_with_a_long_random_secret
CORS_ORIGINS=
```

في وضع `production` ترفض الخدمة الإقلاع دون `AI_SERVICE_API_KEY`، ويكون
`/health/ready` غير جاهز دون مفتاح OpenRouter.

## بناء صورة Docker

```powershell
docker build --tag aoun-ai-service:1.1.0 .
docker image inspect aoun-ai-service:1.1.0
```

حفظ الصورة لإرسالها إلى السيرفر:

```powershell
docker save --output aoun-ai-service-1.1.0.tar aoun-ai-service:1.1.0
```

على السيرفر:

```bash
docker load --input aoun-ai-service-1.1.0.tar
docker compose up --detach
```

ملف `docker-compose.yml` يستخدم `network_mode: host` على خادم Linux، ولا يحتوي
`ports`. يربط Uvicorn على loopback فقط:

```text
AI service -> http://127.0.0.1:3000 (Main Backend)
Main Backend -> http://127.0.0.1:8000 (AI service)
```

لا يستمع منفذ AI على واجهة الشبكة العامة، لذلك لا يمكن الوصول إليه من الإنترنت.

## تشغيل واجهة الاختبار

واجهة المتصفح موجودة فقط في `/`، والمسار القديم `/chat` مخصص لها. لتشغيلها
محلياً على `127.0.0.1` فقط:

```powershell
docker compose -f docker-compose.yml -f docker-compose.test.yml up --detach
```

ثم افتح `http://127.0.0.1:8000`. ملف الإنتاج يعطّل الواجهة وOpenAPI افتراضياً.

## مصادقة الباك إند

يرسل الباك إند السر في كل مسار داخلي:

```http
X-Service-Token: <AI_SERVICE_API_KEY>
X-Request-ID: <uuid>
```

استخدام loopback فقط لا يلغي التحقق من هوية الخدمة.

## Endpoints

### إرسال رسالة

```http
POST /api/v1/chat
```

```json
{
  "conversation_id": "018f-chat-id",
  "message": "ما زلت أشعر بالقلق",
  "conversation_summary": "تحدث المستخدم سابقاً عن ضغط الدراسة.",
  "recent_messages": [
    {
      "id": "message-10",
      "role": "user",
      "content": "لدي اختبار قريب"
    },
    {
      "id": "message-11",
      "role": "assistant",
      "content": "ما أكثر جزء يسبب لك الضغط؟"
    }
  ],
  "patient_profile": {
    "name": "أحمد",
    "age": 24,
    "gender": "male"
  },
  "medical_context": {
    "history": "سياق مصرح ومختصر",
    "last_visit": "2026-07-20"
  }
}
```

`recent_messages` تحتوي الرسائل السابقة فقط ولا تتضمن `message` الحالية. يرسل
الباك إند أقل سياق مصرح به، وليس الملف الطبي الكامل.

```json
{
  "conversation_id": "018f-chat-id",
  "response": "أفهم أن القلق ما زال مستمراً...",
  "status": {
    "intent": "support",
    "response_mode": "empathetic_support",
    "emotional_intensity": "elevated",
    "risk_level": "none"
  }
}
```

### إنشاء أو تحديث ملخص

```http
POST /api/v1/conversations/{conversation_id}/summary
```

يستدعيه الباك إند بعد حفظ رسائل المستخدم والمساعد، وليس في كل رسالة. نقطة بداية
مناسبة هي كل 10–12 رسالة أو عند تجاوز الرسائل منذ آخر ملخص 6000 حرف.

```json
{
  "existing_summary": "الملخص السابق أو null",
  "messages": [
    {"id": "m20", "role": "user", "content": "..."},
    {"id": "m21", "role": "assistant", "content": "..."}
  ]
}
```

```json
{
  "conversation_id": "018f-chat-id",
  "summary": "ملخص مدمج ومحدّث...",
  "covered_message_ids": ["m20", "m21"]
}
```

يحفظ الباك إند `summary` ومعرّف آخر رسالة مغطاة. عند فشل التلخيص يحتفظ بالملخص
السابق ويعيد المحاولة لاحقاً؛ لا يمنع ذلك إرسال رد المحادثة.

### حذف ذاكرة المحادثة المؤقتة

```http
DELETE /api/v1/conversations/{conversation_id}
```

المسار idempotent ويعيد `204` حتى إن لم توجد الجلسة. يبدأ الحذف من الباك إند:
يتحقق من ملكية المستخدم، يحذف سجله الدائم، ثم يستدعي هذا المسار لمسح ذاكرة AI.

### الصحة

```text
GET /health/live   -> العملية تعمل
GET /health/ready  -> المفاتيح الضرورية مضبوطة
```

فحص Docker يستخدم `/health/ready`.

### كتالوج الأطباء والدورات

تجلب خدمة AI البيانات العامة من الباك إند على host port `3000` عبر:

```text
GET /api/doctors
GET /api/courses
```

ويستطيع الباك إند فحص الكاش أو تحديثه فوراً:

```text
GET  /api/v1/catalog/status
POST /api/v1/catalog/refresh
```

في إنتاج Linux يستخدم Compose `network_mode: host`، لذلك يصل AI إلى
`http://127.0.0.1:3000` مباشرة.

## التشغيل دون Docker

```powershell
Copy-Item .env.example .env
uv sync
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

## الاختبارات

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## التطوير إلى Agent

طبقة ما قبل الاستعلام في `prompting.py`، ومنطق التلخيص في `summarization.py`.
خطة الانتقال إلى LangGraph Agent موثقة في `docs/CHATBOT_TO_AGENT_PLAN.md`.

دليل التكامل الكامل لفريق الباك إند، بما فيه دورة المحادثة والتلخيص والحذف وحالة
مصدر معرفة المنصة، موجود في `docs/BACKEND_AI_INTEGRATION.md`.
