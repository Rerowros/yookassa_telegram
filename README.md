# yookassa-telegram

Интеграция платежей YooKassa с Telegram-ботами (aiogram 3.x).

Лёгкая встраиваемая библиотека для создания платежей, формирования чеков (54-ФЗ), обработки вебхуков и управления возвратами.

---

## 🔧 Особенности

- Поддержка создания и подтверждения платежей через YooKassa
- Генерация чеков (54‑ФЗ) и обработка налоговых данных
- Интеграция с aiogram: отправка сообщений с клавиатурами для оплаты
- Встроенная логика retry и обработка ошибок для запросов к YooKassa SDK
- Абстракция хранилища платежей: in-memory, JSON и возможность реализовать своё
- Обработчик webhook с проверкой подписи и callback-ами

---

## Установка

Установите с PyPI:

```bash
pip install yookassa-telegram
```

Требования:
- Python 3.10+
- aiogram
- aiohttp
- yookassa

Зависимости перечислены в `pyproject.toml`.

---

## Быстрый старт

Настройка через переменные окружения (пример `.env`):

```
YOOKASSA_SHOP_ID=123456
YOOKASSA_SECRET_KEY=test_xxxxx
YOOKASSA_RETURN_URL=https://example.com/payment/return
YOOKASSA_WEBHOOK_URL=https://example.com/webhook
YOOKASSA_IS_TEST=true
YOOKASSA_ENABLE_RECEIPTS=true
YOOKASSA_INN=1234567890
```

Пример использования с aiogram:

```python
from aiogram import Bot, Dispatcher
from yookassa_telegram_integration.config import YooKassaConfig
from yookassa_telegram_integration.yookassa_client import YooKassaClient
from yookassa_telegram_integration.payment_service import PaymentService
from yookassa_telegram_integration.receipt_service import ReceiptService
from yookassa_telegram_integration.refund_service import RefundService
from yookassa_telegram_integration.telegram_integration import (
    TelegramPaymentIntegration, create_payment_router
)
from yookassa_telegram_integration.storage import InMemoryPaymentStorage

config = YooKassaConfig.from_env()
client = YooKassaClient(config)
storage = InMemoryPaymentStorage()
payment_service = PaymentService(config, storage, client)
receipt_service = ReceiptService(config)
refund_service = RefundService(config, storage, client)

integration = TelegramPaymentIntegration(
    config,
    payment_service,
    receipt_service,
    refund_service,
    storage
)

router = create_payment_router(integration)
# Включите router в ваш Dispatcher
# dp.include_router(router)
```

Пример отправки сообщения с кнопкой оплаты:

```python
await integration.send_payment_message(
    message,  # aiogram.types.Message
    amount=150.0,
    description='Оплата подписки',
    order_id='order_12345',
    user_email='user@example.com'
)
```

---

## Конфигурация

Ключевые настройки хранятся в `YooKassaConfig`:
- `shop_id` и `secret_key` — данные магазина YooKassa
- `return_url` — URL для возврата пользователя после платежа
- `webhook_url` — URL для webhook уведомлений
- `enable_receipts`, `inn`, `default_tax_system` — опции для 54-ФЗ
- `auto_capture` — автоматически подтверждать платежи

Используйте `YooKassaConfig.from_env()` для загрузки из переменных окружения.

---

## Webhook (обработчик уведомлений)

`WebhookHandler` обеспечивает парсинг уведомлений, проверку и обновление статуса платежа, а также регистрацию Callback-ов для конкретных событий.

Пример использования:

```python
from yookassa_telegram_integration.webhook_handler import (
    create_webhook_handler, WebhookEventType
)

async def on_success(notification):
    print('Оплата успешна', notification.payment_id)

handler = create_webhook_handler(
    config,
    on_payment_succeeded=on_success
)

# В ручном веб-сервере / на фреймворке передайте тело запроса в handler.handle_webhook
# notification = await handler.handle_webhook(payload, headers)
```

---

## Хранилище (Storage)

Доступны реализации:
- `InMemoryPaymentStorage` — для разработки и тестов
- `JSONFilePaymentStorage` — для простого прототипирования

Для production рекомендуется реализовать свой `PaymentStorage` на основе СУБД (Postgres, SQLite) или Redis.

---

## API (кратко)

- `TelegramPaymentIntegration` — основные методы для создания платежей и отправки сообщений в Telegram.
- `PaymentService` — логика создания, подтверждения и отмены платежей.
- `YooKassaClient` — клиент-обёртка вокруг официального SDK с retry-логикой.
- `WebhookHandler` — обработчик webhook уведомлений и callback-ы.
- `YooKassaConfig` — конфигурация для API Клиента и сервисов.
- модели: `CustomerInfo`, `PaymentData`, `ReceiptData`, `PaymentItem`.

Подробная документация и примеры использования — в исходниках и docstrings.

---

## Примеры (расширенно)

Подтверждение платежа:

```python
from yookassa_telegram_integration.payment_service import PaymentService
await payment_service.capture_payment(payment_id)
```

Отмена платежа:

```python
await payment_service.cancel_payment(payment_id)
```

Создание возврата:

```python
from yookassa_telegram_integration.models import RefundData
await refund_service.create_refund(
    RefundData(
        payment_id='payment_123',
        amount=100.0,
        currency='RUB',
        description='Возврат по ошибке'
    ),
    idempotency_key='refund_key_123'
)
```

## Разработка и тесты

Установите dev-зависимости и выполните тесты:

```bash
pip install -e .[dev]
pytest
```
---

## Публикация на PyPI

Создайте билды и опубликуйте пакет с помощью `build` и `twine`:

```bash
python -m build
twine upload dist/*
```

Для предварительной проверки можно загрузить пакет в TestPyPI:

```bash
twine upload --repository testpypi dist/*
```

---

## Contributing

PR и issue приветствуются. Пожалуйста, используйте ветку `main` как основу и следуйте CONTRIBUTING.md (если есть).

Перед PR выполните:

```bash
black .
mypy .
pytest
```

---

## Лицензия

Проект распространяется под лицензией MIT. Подробнее в `LICENSE`.

---

## Контакт

Автор: rerowros  ·  Email: rerowros@gmail.com

Поддержка/Issues: https://github.com/Rerowros/yookassa-telegram/issues
