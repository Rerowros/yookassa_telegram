# YooKassa Telegram Integration — API Documentation (OpenAPI-style + SDK Reference)

Этот документ содержит OpenAPI-style описание, а также подробную документацию по публичным классам и функциям пакета `yookassa_telegram`.

> Примечание: Пакет предоставляет SDK-стиль функции и сервисы, а не HTTP-сервер. Ниже показаны рекомендованные HTTP маршруты, которые вы можете реализовать в вашем бэкенде (например, FastAPI) для интеграции.

---

## Endpoints (recommended)

### POST /webhook
- Description: Принимает уведомления от YooKassa.
- Headers:
  - `X-Yookassa-Signature` (string) — подпись webhook: hex SHA256(payload + secret)
- Body: YooKassa webhook object (см. `YooKassaWebhook` schema в `openapi.yaml`).
- Behaviour:
  - Верифицирует подпись с помощью `WebhookHandler.verify_signature` или `validate_webhook_signature`.
  - Обрабатывает событие: обновляет статус в storage и вызывает зарегистрированные callbacks.
- Success Response: 200 OK: `{ "ok": true }`
- Error cases: 403 (invalid signature), 400 (bad payload), 500 (internal error)

Example FastAPI handler (from repo docs):
```py
@app.post('/webhook')
async def yookassa_webhook(request: Request, x_yookassa_signature: str = Header(None)):
    body = await request.body()
    if not handler.verify_signature(body, x_yookassa_signature, config.secret_key):
        raise HTTPException(status_code=403, detail='Invalid signature')
    notification = await handler.handle_webhook(body)
    return {'ok': True}
```

---

### POST /payments
- Description: Создание платежа (вызов `PaymentService.create_payment`)
- Request body: JSON matching `PaymentCreate` schema
  - required: amount, order_id, description, customer
- Returns: 201 Created with `PaymentResponse` schema

### GET /payments/{payment_id}
- Description: Получение платежа (вызов `PaymentService.get_payment`)
- Params: payment_id (path)
- Returns: 200 OK with `PaymentResponse` schema

### POST /payments/{payment_id}/capture
- Description: Подтвердить платеж. Если amount передан — частичное подтверждение.
- Request body: { amount?: string }
- Returns: 200 OK with updated `PaymentResponse`

### POST /payments/{payment_id}/cancel
- Description: Отменить платеж (`PaymentService.cancel_payment`)
- Returns: 200 OK with updated `PaymentResponse`

### POST /refunds
- Description: Создание возврата (`RefundService.create_refund`)
- Request body: `RefundCreate` schema
- Returns: 201 Created with `RefundResponse`

### GET /refunds/{refund_id}
- Description: Получение возврата (`RefundService.get_refund`)
- Returns: 200 OK with `RefundResponse`

---

## SDK Public API Reference

Ниже — основные публичные классы и методы для использования в вашем приложении. Для каждого метода указаны аргументы и возвращаемые значения.

### Webhook

#### WebhookHandler (class)
- __init__(config: YooKassaConfig, storage: Optional[PaymentStorage] = None)
  - config: `YooKassaConfig` — конфигурация магазина
  - storage: implementation of `PaymentStorage` (optional)

- register_callback(event_type: WebhookEventType, callback: async function)
  - event_type: one of `WebhookEventType` enum values
  - callback: async function taking `WebhookNotification` as parameter

- handle_webhook(payload: str|bytes|dict, headers: Optional[dict]) -> WebhookNotification
  - payload: webhook body (raw json string / bytes or dict)
  - headers: optional headers dict (to fetch signature)
  - Returns: `WebhookNotification` object created from webhook
  - Raises: `WebhookError` / `ValidationError` on error

- verify_signature(payload: str|bytes, signature: str, secret_key: str) -> bool
  - Verifies HMAC-SHA256 signature: hex digest of (payload bytes + secret_key)
  - Used to validate request authenticity

- create_webhook_handler(...) factory
  - Helper to construct handler with predefined callbacks (on success, cancel, etc.)

---

### Telegram Integration

#### TelegramPaymentIntegration (class)
- __init__(config: YooKassaConfig, payment_service: PaymentService, receipt_service: ReceiptService, refund_service: RefundService, storage: Optional[PaymentStorage] = None)
  - Initializes the integration, keeps service references

- create_payment_keyboard(payment_url: str, button_text: str = "💳 Оплатить") -> InlineKeyboardMarkup
  - Returns a keyboard with a button that points to `payment_url`.

- create_payment_for_user(user_id: int, amount, description: str, order_id: str, user_email: Optional[str] = None, user_phone: Optional[str] = None, user_full_name: Optional[str] = None, items: Optional[list[PaymentItem]] = None, metadata: Optional[dict] = None) -> tuple (payment_id: str, confirmation_url: str)
  - Validates customer data (requires email or phone), builds receipts (if configured), calls `PaymentService.create_payment` and returns payment id and url.

- send_payment_message(message: Message, amount, description: str, order_id: str, user_email: Optional[str] = None, user_phone: Optional[str] = None, items: Optional[list[PaymentItem]] = None, custom_text: Optional[str] = None) -> Message
  - Shortcut method that creates a payment and sends a Telegram message with the payment button.

- check_payment_status(payment_id: str) -> tuple[PaymentStatus, Optional[dict]]
  - Returns current `PaymentStatus` and `metadata` for a payment

- send_payment_success_notification(bot, user_id: int, payment_id: str, amount: Decimal, order_id: str)
- send_payment_canceled_notification(bot, user_id: int, payment_id: str, order_id: str)

- create_payment_router(payment_integration) -> Router
  - Returns an aiogram Router with a basic `/pay` command for testing

---

### PaymentService

- create_payment(amount, order_id: str, description: str, customer: CustomerInfo, receipt: Optional[ReceiptData] = None, currency: Currency = Currency.RUB, metadata: Optional[dict] = None, capture: Optional[bool] = None) -> PaymentData
  - Creates a payment using `YooKassaClient`, registers it in storage, validates the data.
  - Raises: `ValidationError`, `PaymentCreationError` on issues

- get_payment(payment_id: str) -> PaymentData
  - Returns `PaymentData` from storage (and updates status by requesting the API)
  - Raises: `PaymentNotFoundError` if not found

- get_payment_by_order_id(order_id: str) -> Optional[PaymentData]

- capture_payment(payment_id: str, amount: Optional[Decimal] = None) -> PaymentData
  - Captures payment; for partial capture pass `amount`.
  - Raises: `PaymentCaptureError` on failure

- cancel_payment(payment_id: str) -> PaymentData
  - Cancels a payment if allowed; raises `PaymentCancelError` on failure

- get_user_payments(user_id: str, limit: int = 10, offset: int = 0) -> list[PaymentData]
  - Retrieve payments for user from storage

---

### ReceiptService

- create_receipt(customer: CustomerInfo, items: list[PaymentItem], tax_system_code: int | None = None) -> ReceiptData
  - Validates receipt data and returns `ReceiptData` object.
  - Raises `ValidationError` on invalid data.

- create_simple_receipt(customer, description, amount, quantity = 1, vat_code=VATCode.NO_VAT, payment_subject=PaymentSubject.COMMODITY, payment_mode=PaymentMode.FULL_PAYMENT) -> ReceiptData
  - Creates a receipt with a single item for quick flows.

- validate_receipt_amount(receipt: ReceiptData, expected_amount: Decimal) -> tuple(bool, error_message)
  - Validates exactness of the receipt sum; returns (True, None) if OK.

- get_vat_amount(amount: Decimal, vat_code: VATCode) -> Decimal
  - Calculates VAT amount according to code semantics.

---

### RefundService

- create_refund(payment_id: str, amount, description: str, currency: Currency = Currency.RUB) -> RefundData
  - Creates a refund using the `YooKassaClient`, validates and stores it.
  - Raises: `ValidationError` or `RefundError` on failure.

- create_full_refund(payment_id: str, description: str = "Полный возврат") -> RefundData
  - Reads payment amount and creates a full refund.

- get_refund(refund_id: str) -> RefundData
  - Returns refund info (from storage or API) and updates status.

---

## Models (Schemas)

All data models map to dataclasses in `models.py`. Below summarized the main ones with required fields.

### CustomerInfo
- Fields:
  - email: string (optional) — at least email or phone required
  - phone: string (optional) — normalized format 79XXXXXXXXX
  - full_name: string (optional)
  - inn: string (optional)

### PaymentItem
- Fields:
  - description: string (required)
  - quantity: decimal string (required)
  - amount: object { value: string, currency: enum } (required)
  - vat_code: int (VAT code)
  - payment_subject, payment_mode: enums

### ReceiptData
- Fields:
  - customer: CustomerInfo
  - items: list of PaymentItem
  - tax_system_code: int (1–6), default 1

### PaymentData (response)
- Fields:
  - payment_id: string
  - amount: string
  - currency: string
  - description: string
  - order_id: string
  - confirmation_url: string
  - status: enum (pending / waiting_for_capture / succeeded / canceled)
  - metadata: object
  - created_at: datetime

### RefundData (request/response)
- Request: { payment_id: string, amount: string, description: string }
- Response: { refund_id, payment_id, amount, currency, status, created_at }

### WebhookNotification
- Fields parsed from YooKassa webhook:
  - event: string (e.g., 'payment.succeeded')
  - object:
    - id, status, amount { value, currency }, metadata, created_at

---

## Security — Webhook Signature

- Signature generation: `hex(sha256(payload + secret))` — repo provides `validate_webhook_signature(payload, signature, secret)` in `utils.py` and `WebhookHandler.verify_signature`.
- Header name in examples: `X-Yookassa-Signature` (or `x_yookassa_signature` in FastAPI header mapping).
- You must compare signatures using `hmac.compare_digest` (or `secrets.compare_digest`) to avoid timing attacks.

Example verification:
```py
from payment.utils import validate_webhook_signature

if not validate_webhook_signature(body, x_yookassa_signature, config.secret_key):
    raise HTTPException(status_code=403, detail='Invalid signature')
```

---

## Examples

### Create payment request example
Request:
```json
{
  "amount": "100.00",
  "order_id": "order_20251116_abc123",
  "description": "Оплата заказа #123",
  "customer": { "email": "user@example.com", "phone": "79123456789" }
}
```
Response:
```json
{
  "payment_id": "pay_0001",
  "amount": "100.00",
  "currency": "RUB",
  "description": "Оплата заказа #123",
  "order_id": "order_20251116_abc123",
  "confirmation_url": "https://yookassa.example/confirm",
  "status": "pending",
  "created_at": "2025-01-01T00:00:00Z",
  "metadata": { "user_id": "4512345" }
}
```

### Webhook example
Payload body:
```json
{
  "event": "payment.succeeded",
  "object": {
    "id": "pay_0001",
    "status": "succeeded",
    "amount": { "value": "100.00", "currency": "RUB" },
    "metadata": { "order_number": "123", "user_id": "4512345" },
    "created_at": "2025-01-01T00:00:00Z"
  }
}
```

Header `X-Yookassa-Signature`: `hex sha256 of <payload + secret_key>`.

---

## Implementation notes & tips
- Async vs Sync: The SDK calls are synchronous; `YooKassaClient` wraps them with `asyncio.to_thread()` in the repository, so services are declared `async`.
- Idempotency: The SDK uses `idempotency_key` generated with `generate_idempotency_key(order_id)`.
- Validation: All services perform validation — they raise typed exceptions defined in `exceptions.py` (e.g. `ValidationError`, `PaymentError`), and you should map those to HTTP errors.
- Storage: Use `PaymentStorage` interface to persist payments/refunds, or use `InMemoryPaymentStorage` for tests.

---

## Next steps & extras
- If you want, I can generate a more complete `openapi.yaml` including security schemes, auth details for your backend, or auto-generate a FastAPI skeleton (`app.py`) that uses services defined in the package.
- I can also produce a `README` ready for publishing to PyPI or a more detailed developer README.

---

Questions? Напиши, если хочешь, чтобы я сгенерировал FastAPI skeleton или дополнил спецификацию полями/примером payload по ссылке YooKassa (sandbox).