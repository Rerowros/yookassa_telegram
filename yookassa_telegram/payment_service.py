"""
Сервис для работы с платежами
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from .config import YooKassaConfig
from .enums import PaymentStatus, Currency
from .exceptions import (
    PaymentCreationError,
    PaymentNotFoundError,
    PaymentCaptureError,
    PaymentCancelError,
    ValidationError
)
from .models import PaymentData, CustomerInfo, ReceiptData
from .storage import PaymentStorage, InMemoryPaymentStorage
from .utils import generate_idempotency_key
from .yookassa_client import YooKassaClient


logger = logging.getLogger(__name__)


class PaymentService:
    """
    Сервис для создания и управления платежами
    
    Обеспечивает:
    - Создание платежей с валидацией
    - Проверку статуса платежей
    - Подтверждение платежей
    - Отмену платежей
    - Хранение истории платежей
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
            storage: Хранилище для платежей (опционально)
            client: Клиент YooKassa (опционально, для тестирования)
        """
        self.config = config
        self.storage = storage or InMemoryPaymentStorage()
        self.client = client or YooKassaClient(config)
        
        logger.info("PaymentService initialized")
    
    async def create_payment(
        self,
        amount: Decimal | float | int | str,
        order_id: str,
        description: str,
        customer: CustomerInfo,
        receipt: Optional[ReceiptData] = None,
        currency: Currency = Currency.RUB,
        metadata: Optional[dict] = None,
        capture: Optional[bool] = None
    ) -> PaymentData:
        """
        Создание платежа
        
        Args:
            amount: Сумма платежа
            order_id: ID заказа в вашей системе
            description: Описание платежа
            customer: Информация о покупателе
            receipt: Данные чека (для 54-ФЗ)
            currency: Валюта платежа
            metadata: Дополнительные метаданные
            capture: Автоматическое подтверждение (если None, берется из config)
            
        Returns:
            PaymentData: Данные созданного платежа
            
        Raises:
            ValidationError: При невалидных данных
            PaymentCreationError: При ошибке создания платежа
        """
        logger.info(f"Creating payment for order: {order_id}, amount: {amount}")
        
        # Конвертируем amount в Decimal
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        
        # Проверяем, не создан ли уже платеж для этого заказа
        existing_payment = await self.storage.get_payment_by_order_id(order_id)
        if existing_payment:
            logger.warning(f"Payment already exists for order: {order_id}")
            return existing_payment
        
        # Используем capture из конфига, если не передан
        if capture is None:
            capture = self.config.auto_capture
        
        # Создаем объект платежа
        payment = PaymentData(
            amount=amount,
            currency=currency,
            description=description,
            order_id=order_id,
            customer=customer,
            receipt=receipt,
            metadata=metadata or {},
            capture=capture
        )
        
        # Валидация данных
        is_valid, error_msg = payment.validate()
        if not is_valid:
            logger.error(f"Payment validation failed: {error_msg}")
            raise ValidationError(error_msg or "Invalid payment data")
        
        # Если включены чеки, но receipt не передан, логируем предупреждение
        if self.config.enable_receipts and not receipt:
            logger.warning("Receipts are enabled but no receipt data provided")
        
        # Генерируем ключ идемпотентности
        idempotency_key = generate_idempotency_key(order_id)
        
        try:
            # Создаем платеж через API
            api_payment = await self.client.create_payment(
                payment.to_api_dict(self.config.return_url, idempotency_key),
                idempotency_key
            )
            
            # Обновляем данные платежа из ответа API
            payment.payment_id = api_payment.id
            payment.status = PaymentStatus(api_payment.status)
            payment.created_at = datetime.fromisoformat(
                api_payment.created_at.replace('Z', '+00:00')
            )
            
            # Получаем URL для оплаты
            if hasattr(api_payment, 'confirmation') and api_payment.confirmation:
                payment.confirmation_url = api_payment.confirmation.confirmation_url
            
            # Сохраняем в хранилище
            await self.storage.save_payment(payment)
            
            logger.info(
                f"Payment created successfully: {payment.payment_id}, "
                f"status: {payment.status}, url: {payment.confirmation_url}"
            )
            
            return payment
            
        except Exception as e:
            logger.error(f"Failed to create payment: {e}")
            raise PaymentCreationError(f"Failed to create payment: {e}", e)
    
    async def get_payment(self, payment_id: str) -> PaymentData:
        """
        Получение информации о платеже
        
        Args:
            payment_id: ID платежа
            
        Returns:
            PaymentData: Данные платежа
            
        Raises:
            PaymentNotFoundError: Если платеж не найден
        """
        logger.info(f"Getting payment: {payment_id}")
        
        # Сначала проверяем в хранилище
        payment = await self.storage.get_payment(payment_id)
        
        try:
            # Получаем актуальные данные из API
            api_payment = await self.client.get_payment(payment_id)
            
            if payment:
                # Обновляем статус в хранилище
                new_status = PaymentStatus(api_payment.status)
                if payment.status != new_status:
                    await self.storage.update_payment_status(payment_id, new_status)
                    payment.status = new_status
                    logger.info(f"Payment status updated: {payment_id} -> {new_status}")
            
            return payment
            
        except Exception as e:
            logger.error(f"Failed to get payment: {e}")
            # Если платеж есть в хранилище, возвращаем его
            if payment:
                return payment
            raise PaymentNotFoundError(f"Payment not found: {payment_id}", e)
    
    async def get_payment_by_order_id(self, order_id: str) -> Optional[PaymentData]:
        """
        Получение платежа по ID заказа
        
        Args:
            order_id: ID заказа
            
        Returns:
            PaymentData: Данные платежа или None
        """
        logger.info(f"Getting payment by order_id: {order_id}")
        return await self.storage.get_payment_by_order_id(order_id)
    
    async def capture_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal | float | int | str] = None
    ) -> PaymentData:
        """
        Подтверждение платежа
        
        Args:
            payment_id: ID платежа
            amount: Сумма для подтверждения (для частичного подтверждения)
            
        Returns:
            PaymentData: Обновленные данные платежа
            
        Raises:
            PaymentCaptureError: При ошибке подтверждения
        """
        logger.info(f"Capturing payment: {payment_id}, amount: {amount}")
        
        # Получаем платеж
        payment = await self.get_payment(payment_id)
        
        # Проверяем статус
        if payment.status != PaymentStatus.WAITING_FOR_CAPTURE:
            logger.error(
                f"Cannot capture payment in status: {payment.status}"
            )
            raise PaymentCaptureError(
                f"Payment cannot be captured in status: {payment.status}"
            )
        
        try:
            # Подготавливаем данные для подтверждения
            amount_dict = None
            if amount is not None:
                if not isinstance(amount, Decimal):
                    amount = Decimal(str(amount))
                amount_dict = {
                    "value": f"{amount:.2f}",
                    "currency": payment.currency.value
                }
            
            # Генерируем ключ идемпотентности
            idempotency_key = generate_idempotency_key(
                f"{payment.order_id}_capture",
                datetime.now()
            )
            
            # Подтверждаем платеж через API
            api_payment = await self.client.capture_payment(
                payment_id,
                amount_dict,
                idempotency_key
            )
            
            # Обновляем статус
            new_status = PaymentStatus(api_payment.status)
            await self.storage.update_payment_status(payment_id, new_status)
            payment.status = new_status
            
            logger.info(f"Payment captured successfully: {payment_id}")
            
            return payment
            
        except Exception as e:
            logger.error(f"Failed to capture payment: {e}")
            raise PaymentCaptureError(f"Failed to capture payment: {e}", e)
    
    async def cancel_payment(self, payment_id: str) -> PaymentData:
        """
        Отмена платежа
        
        Args:
            payment_id: ID платежа
            
        Returns:
            PaymentData: Обновленные данные платежа
            
        Raises:
            PaymentCancelError: При ошибке отмены
        """
        logger.info(f"Canceling payment: {payment_id}")
        
        # Получаем платеж
        payment = await self.get_payment(payment_id)
        
        # Проверяем статус
        if payment.status not in [
            PaymentStatus.PENDING,
            PaymentStatus.WAITING_FOR_CAPTURE
        ]:
            logger.error(f"Cannot cancel payment in status: {payment.status}")
            raise PaymentCancelError(
                f"Payment cannot be canceled in status: {payment.status}"
            )
        
        try:
            # Генерируем ключ идемпотентности
            idempotency_key = generate_idempotency_key(
                f"{payment.order_id}_cancel",
                datetime.now()
            )
            
            # Отменяем платеж через API
            api_payment = await self.client.cancel_payment(payment_id, idempotency_key)
            
            # Обновляем статус
            new_status = PaymentStatus(api_payment.status)
            await self.storage.update_payment_status(payment_id, new_status)
            payment.status = new_status
            
            logger.info(f"Payment canceled successfully: {payment_id}")
            
            return payment
            
        except Exception as e:
            logger.error(f"Failed to cancel payment: {e}")
            raise PaymentCancelError(f"Failed to cancel payment: {e}", e)
    
    async def get_user_payments(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[PaymentData]:
        """
        Получение платежей пользователя
        
        Args:
            user_id: ID пользователя
            limit: Лимит выборки
            offset: Смещение
            
        Returns:
            List[PaymentData]: Список платежей
        """
        logger.info(f"Getting payments for user: {user_id}")
        return await self.storage.get_payments_by_user(user_id, limit, offset)
