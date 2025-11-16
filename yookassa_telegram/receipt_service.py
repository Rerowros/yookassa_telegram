"""
Сервис для работы с чеками (54-ФЗ)
"""

import logging
from decimal import Decimal
from typing import List

from .config import YooKassaConfig
from .enums import VATCode, PaymentSubject, PaymentMode, Currency
from .exceptions import ReceiptError, ValidationError
from .models import ReceiptData, PaymentItem, CustomerInfo


logger = logging.getLogger(__name__)


class ReceiptService:
    """
    Сервис для создания и работы с чеками (54-ФЗ)
    
    Помогает правильно формировать чеки для соответствия 54-ФЗ
    """
    
    def __init__(self, config: YooKassaConfig):
        """
        Инициализация сервиса
        
        Args:
            config: Конфигурация YooKassa
        """
        self.config = config
        logger.info("ReceiptService initialized")
    
    def create_receipt(
        self,
        customer: CustomerInfo,
        items: List[PaymentItem],
        tax_system_code: int | None = None
    ) -> ReceiptData:
        """
        Создание чека
        
        Args:
            customer: Информация о покупателе
            items: Позиции в чеке
            tax_system_code: Код системы налогообложения
            
        Returns:
            ReceiptData: Данные чека
            
        Raises:
            ValidationError: При невалидных данных
        """
        logger.info(f"Creating receipt for customer: {customer.email or customer.phone}")
        
        # Используем tax_system_code из конфига, если не передан
        if tax_system_code is None:
            tax_system_code = self.config.default_tax_system
        
        # Создаем чек
        receipt = ReceiptData(
            customer=customer,
            items=items,
            tax_system_code=tax_system_code
        )
        
        # Валидация
        if not receipt.validate():
            logger.error("Receipt validation failed")
            raise ValidationError("Invalid receipt data")
        
        logger.info(
            f"Receipt created: {len(items)} items, "
            f"total: {receipt.total_amount} {Currency.RUB.value}"
        )
        
        return receipt
    
    def create_simple_receipt(
        self,
        customer: CustomerInfo,
        description: str,
        amount: Decimal | float | int | str,
        quantity: Decimal | float | int | str = 1,
        vat_code: VATCode = VATCode.NO_VAT,
        payment_subject: PaymentSubject = PaymentSubject.COMMODITY,
        payment_mode: PaymentMode = PaymentMode.FULL_PAYMENT
    ) -> ReceiptData:
        """
        Создание простого чека с одной позицией
        
        Args:
            customer: Информация о покупателе
            description: Описание товара/услуги
            amount: Цена за единицу
            quantity: Количество
            vat_code: Код НДС
            payment_subject: Предмет расчета
            payment_mode: Признак способа расчета
            
        Returns:
            ReceiptData: Данные чека
        """
        logger.info(f"Creating simple receipt: {description}, amount: {amount}")
        
        # Конвертируем в Decimal
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        if not isinstance(quantity, Decimal):
            quantity = Decimal(str(quantity))
        
        # Создаем позицию
        item = PaymentItem(
            description=description,
            quantity=quantity,
            amount=amount,
            vat_code=vat_code,
            payment_subject=payment_subject,
            payment_mode=payment_mode
        )
        
        return self.create_receipt(customer, [item])
    
    @staticmethod
    def validate_receipt_amount(
        receipt: ReceiptData,
        expected_amount: Decimal
    ) -> tuple[bool, str | None]:
        """
        Проверка соответствия суммы чека ожидаемой сумме
        
        Args:
            receipt: Данные чека
            expected_amount: Ожидаемая сумма
            
        Returns:
            tuple: (is_valid, error_message)
        """
        total = receipt.total_amount
        
        # Разница не должна превышать 0.01 (из-за округления)
        if abs(total - expected_amount) > Decimal("0.01"):
            return False, (
                f"Receipt total ({total}) doesn't match "
                f"expected amount ({expected_amount})"
            )
        
        return True, None
    
    @staticmethod
    def get_vat_amount(
        amount: Decimal,
        vat_code: VATCode
    ) -> Decimal:
        """
        Расчет суммы НДС
        
        Args:
            amount: Сумма
            vat_code: Код НДС
            
        Returns:
            Decimal: Сумма НДС
        """
        vat_rates = {
            VATCode.NO_VAT: Decimal("0"),
            VATCode.VAT_0: Decimal("0"),
            VATCode.VAT_10: Decimal("0.10"),
            VATCode.VAT_20: Decimal("0.20"),
            VATCode.VAT_10_110: Decimal("10") / Decimal("110"),
            VATCode.VAT_20_120: Decimal("20") / Decimal("120"),
        }
        
        rate = vat_rates.get(vat_code, Decimal("0"))
        
        # Для кодов 10/110 и 20/120 НДС уже включен в сумму
        if vat_code in [VATCode.VAT_10_110, VATCode.VAT_20_120]:
            return amount * rate
        
        # Для остальных - НДС сверх суммы
        return amount * rate
