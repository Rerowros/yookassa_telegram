"""
Enum'ы для работы с YooKassa API
"""

from enum import Enum


class PaymentStatus(str, Enum):
    """Статусы платежа"""
    PENDING = "pending"  # Ожидает оплаты
    WAITING_FOR_CAPTURE = "waiting_for_capture"  # Ожидает подтверждения
    SUCCEEDED = "succeeded"  # Успешно завершен
    CANCELED = "canceled"  # Отменен


class RefundStatus(str, Enum):
    """Статусы возврата"""
    PENDING = "pending"  # В процессе
    SUCCEEDED = "succeeded"  # Успешно завершен
    CANCELED = "canceled"  # Отменен


class ReceiptType(str, Enum):
    """Типы чеков"""
    PAYMENT = "payment"  # Чек прихода
    REFUND = "refund"  # Чек возврата


class VATCode(int, Enum):
    """Коды НДС (для 54-ФЗ)"""
    NO_VAT = 1  # Без НДС
    VAT_0 = 2  # НДС 0%
    VAT_10 = 3  # НДС 10%
    VAT_20 = 4  # НДС 20%
    VAT_10_110 = 5  # НДС 10/110
    VAT_20_120 = 6  # НДС 20/120


class PaymentSubject(str, Enum):
    """Предмет расчета (для 54-ФЗ)"""
    COMMODITY = "commodity"  # Товар
    EXCISE = "excise"  # Подакцизный товар
    JOB = "job"  # Работа
    SERVICE = "service"  # Услуга
    GAMBLING_BET = "gambling_bet"  # Ставка азартной игры
    GAMBLING_PRIZE = "gambling_prize"  # Выигрыш азартной игры
    LOTTERY = "lottery"  # Лотерейный билет
    LOTTERY_PRIZE = "lottery_prize"  # Выигрыш лотереи
    INTELLECTUAL_ACTIVITY = "intellectual_activity"  # Интеллектуальная деятельность
    PAYMENT = "payment"  # Платеж
    AGENT_COMMISSION = "agent_commission"  # Агентское вознаграждение
    COMPOSITE = "composite"  # Составной предмет расчета
    ANOTHER = "another"  # Другое


class PaymentMode(str, Enum):
    """Признак способа расчета (для 54-ФЗ)"""
    FULL_PREPAYMENT = "full_prepayment"  # Полная предоплата
    PARTIAL_PREPAYMENT = "partial_prepayment"  # Частичная предоплата
    ADVANCE = "advance"  # Аванс
    FULL_PAYMENT = "full_payment"  # Полный расчет
    PARTIAL_PAYMENT = "partial_payment"  # Частичный расчет и кредит
    CREDIT = "credit"  # Кредит
    CREDIT_PAYMENT = "credit_payment"  # Выплата кредита


class ConfirmationType(str, Enum):
    """Типы подтверждения платежа"""
    REDIRECT = "redirect"  # Редирект на страницу оплаты
    EMBEDDED = "embedded"  # Встроенная форма
    EXTERNAL = "external"  # Внешняя форма
    QR = "qr"  # QR-код


class Currency(str, Enum):
    """Валюты"""
    RUB = "RUB"  # Российский рубль
    USD = "USD"  # Доллар США
    EUR = "EUR"  # Евро


class WebhookEventType(str, Enum):
    """Типы webhook событий"""
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_WAITING_FOR_CAPTURE = "payment.waiting_for_capture"
    PAYMENT_CANCELED = "payment.canceled"
    REFUND_SUCCEEDED = "refund.succeeded"
