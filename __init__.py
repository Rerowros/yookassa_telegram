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
from .yookassa_client import YooKassaClient
from .storage import PaymentStorage, InMemoryPaymentStorage, JSONFilePaymentStorage
from .database_storage import DatabasePaymentStorage

__version__ = "1.0.2"
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
    "YooKassaClient",
    # Storage
    "PaymentStorage",
    "InMemoryPaymentStorage",
    "JSONFilePaymentStorage",
    "DatabasePaymentStorage",
]
