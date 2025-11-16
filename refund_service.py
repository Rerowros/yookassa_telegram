"""
Сервис для работы с возвратами
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from .config import YooKassaConfig
from .enums import RefundStatus, Currency
from .exceptions import RefundError, RefundNotFoundError, ValidationError
from .models import RefundData
from .storage import PaymentStorage, InMemoryPaymentStorage
from .utils import generate_idempotency_key
from .yookassa_client import YooKassaClient


logger = logging.getLogger(__name__)


class RefundService:
    """
    Сервис для создания и управления возвратами
    
    Обеспечивает:
    - Создание полных и частичных возвратов
    - Проверку статуса возвратов
    - Хранение истории возвратов
    """
    
    def __init__(
        self,
        config: YooKassaConfig,
        storage: Optional[PaymentStorage] = None,
        client: Optional[YooKassaClient] = None
    ):
        """
        Инициализация сервиса
        
        Args:
            config: Конфигурация YooKassa
            storage: Хранилище для возвратов (опционально)
            client: Клиент YooKassa (опционально, для тестирования)
        """
        self.config = config
        self.storage = storage or InMemoryPaymentStorage()
        self.client = client or YooKassaClient(config)
        
        logger.info("RefundService initialized")
    
    async def create_refund(
        self,
        payment_id: str,
        amount: Decimal | float | int | str,
        description: str,
        currency: Currency = Currency.RUB
    ) -> RefundData:
        """
        Создание возврата
        
        Args:
            payment_id: ID платежа для возврата
            amount: Сумма возврата
            description: Причина возврата
            currency: Валюта
            
        Returns:
            RefundData: Данные созданного возврата
            
        Raises:
            ValidationError: При невалидных данных
            RefundError: При ошибке создания возврата
        """
        logger.info(
            f"Creating refund for payment: {payment_id}, "
            f"amount: {amount}, reason: {description}"
        )
        
        # Конвертируем amount в Decimal
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        # Проверяем, существует ли платеж
        payment = await self.storage.get_payment(payment_id)
        if not payment:
            logger.warning(f"Payment not found in storage: {payment_id}")
            # Попытаемся получить из API
            try:
                api_payment = await self.client.get_payment(payment_id)
                if not api_payment:
                    raise RefundError(f"Payment not found: {payment_id}")
            except Exception as e:
                logger.error(f"Failed to get payment from API: {e}")
                raise RefundError(f"Payment not found: {payment_id}", e)
        
        # Создаем объект возврата
        refund = RefundData(
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            description=description
        )
        
        # Валидация данных
        is_valid, error_msg = refund.validate()
        if not is_valid:
            logger.error(f"Refund validation failed: {error_msg}")
            raise ValidationError(error_msg or "Invalid refund data")
        
        # Генерируем ключ идемпотентности
        idempotency_key = generate_idempotency_key(
            f"{payment_id}_refund_{amount}",
            datetime.now()
        )
        
        try:
            # Создаем возврат через API
            api_refund = await self.client.create_refund(
                refund.to_api_dict(idempotency_key),
                idempotency_key
            )
            
            # Обновляем данные возврата из ответа API
            refund.refund_id = api_refund.id
            refund.status = RefundStatus(api_refund.status)
            refund.created_at = datetime.fromisoformat(
                api_refund.created_at.replace('Z', '+00:00')
            )
            
            # Сохраняем в хранилище
            await self.storage.save_refund(refund)
            
            logger.info(
                f"Refund created successfully: {refund.refund_id}, "
                f"status: {refund.status}"
            )
            
            return refund
            
        except Exception as e:
            logger.error(f"Failed to create refund: {e}")
            raise RefundError(f"Failed to create refund: {e}", e)
    
    async def create_full_refund(
        self,
        payment_id: str,
        description: str = "Полный возврат"
    ) -> RefundData:
        """
        Создание полного возврата
        
        Args:
            payment_id: ID платежа
            description: Причина возврата
            
        Returns:
            RefundData: Данные созданного возврата
            
        Raises:
            RefundError: При ошибке создания возврата
        """
        logger.info(f"Creating full refund for payment: {payment_id}")
        
        # Получаем информацию о платеже
        payment = await self.storage.get_payment(payment_id)
        if not payment:
            # Попытаемся получить из API
            try:
                api_payment = await self.client.get_payment(payment_id)
                amount = Decimal(api_payment.amount.value)
                currency = Currency(api_payment.amount.currency)
            except Exception as e:
                logger.error(f"Failed to get payment: {e}")
                raise RefundError(f"Payment not found: {payment_id}", e)
        else:
            amount = payment.amount
            currency = payment.currency
        
        return await self.create_refund(
            payment_id=payment_id,
            amount=amount,
            description=description,
            currency=currency
        )
    
    async def get_refund(self, refund_id: str) -> RefundData:
        """
        Получение информации о возврате
        
        Args:
            refund_id: ID возврата
            
        Returns:
            RefundData: Данные возврата
            
        Raises:
            RefundNotFoundError: Если возврат не найден
        """
        logger.info(f"Getting refund: {refund_id}")
        
        # Сначала проверяем в хранилище
        refund = await self.storage.get_refund(refund_id)
        
        try:
            # Получаем актуальные данные из API
            api_refund = await self.client.get_refund(refund_id)
            
            if refund:
                # Обновляем статус
                refund.status = RefundStatus(api_refund.status)
            
            return refund
            
        except Exception as e:
            logger.error(f"Failed to get refund: {e}")
            # Если возврат есть в хранилище, возвращаем его
            if refund:
                return refund
            raise RefundNotFoundError(f"Refund not found: {refund_id}", e)
