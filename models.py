"""
Модели данных для работы с платежами
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from .enums import (
    PaymentStatus,
    RefundStatus,
    VATCode,
    PaymentSubject,
    PaymentMode,
    Currency,
    ReceiptType
)


@dataclass
class CustomerInfo:
    """
    Информация о покупателе
    
    Обязательные поля для 54-ФЗ:
    - Хотя бы один контакт: email или phone
    """
    email: Optional[str] = None
    phone: Optional[str] = None
    full_name: Optional[str] = None
    inn: Optional[str] = None
    
    def validate(self) -> bool:
        """Проверка валидности данных покупателя"""
        if not self.email and not self.phone:
            return False
        
        if self.phone and not self._is_valid_phone(self.phone):
            return False
        
        if self.email and not self._is_valid_email(self.email):
            return False
        
        return True
    
    @staticmethod
    def _is_valid_phone(phone: str) -> bool:
        """Проверка формата телефона"""
        # Должен начинаться с 7 и содержать 11 цифр
        clean_phone = ''.join(filter(str.isdigit, phone))
        return len(clean_phone) == 11 and clean_phone.startswith('7')
    
    @staticmethod
    def _is_valid_email(email: str) -> bool:
        """Простая проверка email"""
        return '@' in email and '.' in email.split('@')[-1]
    
    def to_dict(self) -> Dict[str, str]:
        """Конвертация в словарь для API"""
        result = {}
        if self.email:
            result['email'] = self.email
        if self.phone:
            result['phone'] = self.phone
        if self.full_name:
            result['full_name'] = self.full_name
        if self.inn:
            result['inn'] = self.inn
        return result


@dataclass
class PaymentItem:
    """
    Позиция в чеке
    
    Attributes:
        description: Описание товара/услуги
        quantity: Количество
        amount: Цена за единицу (в рублях)
        vat_code: Код НДС
        payment_subject: Предмет расчета
        payment_mode: Признак способа расчета
        product_code: Код товара (GTIN)
        country_of_origin_code: Код страны происхождения
    """
    description: str
    quantity: Decimal
    amount: Decimal
    vat_code: VATCode = VATCode.NO_VAT
    payment_subject: PaymentSubject = PaymentSubject.COMMODITY
    payment_mode: PaymentMode = PaymentMode.FULL_PAYMENT
    product_code: Optional[str] = None
    country_of_origin_code: Optional[str] = None
    
    def __post_init__(self):
        """Конвертация типов"""
        if not isinstance(self.quantity, Decimal):
            self.quantity = Decimal(str(self.quantity))
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
    
    @property
    def total_amount(self) -> Decimal:
        """Общая стоимость позиции"""
        return self.quantity * self.amount
    
    def to_dict(self, currency: Currency = Currency.RUB) -> Dict[str, Any]:
        """Конвертация в словарь для API"""
        result = {
            "description": self.description,
            "quantity": f"{self.quantity:.2f}",
            "amount": {
                "value": f"{self.amount:.2f}",
                "currency": currency.value
            },
            "vat_code": self.vat_code.value,
            "payment_subject": self.payment_subject.value,
            "payment_mode": self.payment_mode.value
        }
        
        if self.product_code:
            result["product_code"] = self.product_code
        if self.country_of_origin_code:
            result["country_of_origin_code"] = self.country_of_origin_code
        
        return result


@dataclass
class ReceiptData:
    """
    Данные чека для 54-ФЗ
    
    Attributes:
        customer: Информация о покупателе
        items: Позиции в чеке
        tax_system_code: Система налогообложения (1-6)
        receipt_type: Тип чека
    """
    customer: CustomerInfo
    items: list[PaymentItem]
    tax_system_code: int = 1  # 1 = УСН доход
    receipt_type: ReceiptType = ReceiptType.PAYMENT
    
    def validate(self) -> bool:
        """Валидация данных чека"""
        if not self.customer.validate():
            return False
        
        if not self.items:
            return False
        
        if self.tax_system_code not in range(1, 7):
            return False
        
        return True
    
    @property
    def total_amount(self) -> Decimal:
        """Общая сумма чека"""
        return sum(item.total_amount for item in self.items)
    
    def to_dict(self, currency: Currency = Currency.RUB) -> Dict[str, Any]:
        """Конвертация в словарь для API"""
        return {
            "customer": self.customer.to_dict(),
            "items": [item.to_dict(currency) for item in self.items],
            "tax_system_code": self.tax_system_code
        }


@dataclass
class PaymentData:
    """
    Данные платежа
    
    Attributes:
        amount: Сумма платежа
        currency: Валюта
        description: Описание платежа
        order_id: ID заказа в вашей системе
        customer: Информация о покупателе
        receipt: Данные чека (для 54-ФЗ)
        metadata: Дополнительные данные (ключ-значение)
        capture: Автоматическое подтверждение
        payment_id: ID платежа в YooKassa (заполняется после создания)
        status: Статус платежа (заполняется после создания)
        confirmation_url: URL для оплаты (заполняется после создания)
        created_at: Дата создания (заполняется после создания)
    """
    amount: Decimal
    currency: Currency
    description: str
    order_id: str
    customer: CustomerInfo
    receipt: Optional[ReceiptData] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    capture: bool = True
    
    # Поля, заполняемые после создания платежа
    payment_id: Optional[str] = None
    status: Optional[PaymentStatus] = None
    confirmation_url: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Конвертация типов"""
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Валидация данных платежа
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if self.amount <= 0:
            return False, "Amount must be greater than 0"
        
        if not self.description:
            return False, "Description is required"
        
        if not self.order_id:
            return False, "Order ID is required"
        
        if not self.customer.validate():
            return False, "Invalid customer data"
        
        if self.receipt and not self.receipt.validate():
            return False, "Invalid receipt data"
        
        if self.receipt and abs(self.receipt.total_amount - self.amount) > Decimal("0.01"):
            return False, "Receipt total doesn't match payment amount"
        
        return True, None
    
    def to_api_dict(self, return_url: str, idempotency_key: str) -> Dict[str, Any]:
        """
        Конвертация в словарь для API запроса
        
        Args:
            return_url: URL для возврата после оплаты
            idempotency_key: Ключ идемпотентности
            
        Returns:
            Dict: Данные для API
        """
        result = {
            "amount": {
                "value": f"{self.amount:.2f}",
                "currency": self.currency.value
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "capture": self.capture,
            "description": self.description,
            "metadata": {
                **self.metadata,
                "order_id": self.order_id
            }
        }
        
        if self.receipt:
            result["receipt"] = self.receipt.to_dict(self.currency)
        
        return result


@dataclass
class RefundData:
    """
    Данные возврата
    
    Attributes:
        payment_id: ID платежа для возврата
        amount: Сумма возврата
        currency: Валюта
        description: Причина возврата
        refund_id: ID возврата (заполняется после создания)
        status: Статус возврата (заполняется после создания)
        created_at: Дата создания (заполняется после создания)
    """
    payment_id: str
    amount: Decimal
    currency: Currency
    description: str
    
    # Поля, заполняемые после создания возврата
    refund_id: Optional[str] = None
    status: Optional[RefundStatus] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Конвертация типов"""
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
    
    def validate(self) -> tuple[bool, Optional[str]]:
        """Валидация данных возврата"""
        if not self.payment_id:
            return False, "Payment ID is required"
        
        if self.amount <= 0:
            return False, "Amount must be greater than 0"
        
        if not self.description:
            return False, "Description is required"
        
        return True, None
    
    def to_api_dict(self, idempotency_key: str) -> Dict[str, Any]:
        """Конвертация в словарь для API запроса"""
        return {
            "payment_id": self.payment_id,
            "amount": {
                "value": f"{self.amount:.2f}",
                "currency": self.currency.value
            },
            "description": self.description
        }


@dataclass
class WebhookNotification:
    """
    Уведомление от webhook
    
    Attributes:
        event: Тип события
        payment_id: ID платежа
        status: Статус платежа
        amount: Сумма
        currency: Валюта
        metadata: Метаданные
        created_at: Дата создания
        raw_data: Сырые данные от API
    """
    event: str
    payment_id: str
    status: PaymentStatus
    amount: Decimal
    currency: Currency
    metadata: Dict[str, Any]
    created_at: datetime
    raw_data: Dict[str, Any]
    
    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "WebhookNotification":
        """Создать объект из ответа API"""
        obj = data.get("object", {})
        
        return cls(
            event=data.get("event", ""),
            payment_id=obj.get("id", ""),
            status=PaymentStatus(obj.get("status", "pending")),
            amount=Decimal(obj.get("amount", {}).get("value", "0")),
            currency=Currency(obj.get("amount", {}).get("currency", "RUB")),
            metadata=obj.get("metadata", {}),
            created_at=datetime.fromisoformat(obj.get("created_at", "").replace("Z", "+00:00")),
            raw_data=data
        )
