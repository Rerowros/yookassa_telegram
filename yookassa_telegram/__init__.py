"""
YooKassa Payment Integration Module for Telegram Bots
Модуль интеграции платежей YooKassa для Telegram ботов

Основной модуль для работы с платежами через YooKassa API.
Поддерживает создание платежей, возвраты, работу с чеками (54-ФЗ) и webhook уведомления.
"""

from .config import YooKassaConfig
from .enums import PaymentStatus, RefundStatus, ReceiptType, VATCode, PaymentSubject, Currency, WebhookEventType
from .exceptions import (
    PaymentError,
    PaymentCreationError,
    PaymentNotFoundError,
    RefundError,
    WebhookError,
    ValidationError
)
from .models import (
    PaymentData,
    PaymentItem,
    CustomerInfo,
    RefundData,
    ReceiptData
)
from .payment_service import PaymentService
from .refund_service import RefundService
from .receipt_service import ReceiptService
from .webhook_handler import WebhookHandler
from .webhook_order_integration import WebhookOrderIntegration
from .telegram_integration import TelegramPaymentIntegration
from .yookassa_client import YooKassaClient
from .storage import PaymentStorage, InMemoryPaymentStorage, JSONFilePaymentStorage
from .database_storage import DatabasePaymentStorage
from .payment_expiration import start_payment_expiration_checker, OrderDatabaseProtocol, OrderManagerProtocol

__version__ = "1.1.0"
__all__ = [
    # Config
    "YooKassaConfig",
    # Enums
    "PaymentStatus",
    "RefundStatus",
    "ReceiptType",
    "VATCode",
    "PaymentSubject",
    "Currency",
    "WebhookEventType",
    # Exceptions
    "PaymentError",
    "PaymentCreationError",
    "PaymentNotFoundError",
    "RefundError",
    "WebhookError",
    "ValidationError",
    # Models
    "PaymentData",
    "PaymentItem",
    "CustomerInfo",
    "RefundData",
    "ReceiptData",
    # Services
    "PaymentService",
    "RefundService",
    "ReceiptService",
    "WebhookHandler",
    "WebhookOrderIntegration",
    "TelegramPaymentIntegration",
    "YooKassaClient",
    # Storage
    "PaymentStorage",
    "InMemoryPaymentStorage",
    "JSONFilePaymentStorage",
    "DatabasePaymentStorage",
    "start_payment_expiration_checker",
    "OrderDatabaseProtocol",
    "OrderManagerProtocol",
]
