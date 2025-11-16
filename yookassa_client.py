"""
Клиент для работы с YooKassa API
"""

import asyncio
import logging
from typing import Any, Dict, Optional
import time

from yookassa import Configuration, Payment, Refund
from yookassa.domain.exceptions import ApiError, UnauthorizedError, BadRequestError

from .config import YooKassaConfig
from .exceptions import (
    AuthenticationError,
    NetworkError,
    PaymentError,
    ValidationError
)
from .utils import mask_sensitive_data


logger = logging.getLogger(__name__)


class YooKassaClient:
    """
    Клиент для работы с YooKassa API
    
    Обеспечивает:
    - Настройку аутентификации
    - Retry логику с экспоненциальной задержкой
    - Логирование запросов и ответов
    - Обработку ошибок
    """
    
    def __init__(self, config: YooKassaConfig):
        """
        Инициализация клиента
        
        Args:
            config: Конфигурация YooKassa
        """
        self.config = config
        self._configure_yookassa()
        self._configure_logger()
    
    def _configure_logger(self):
        """Настройка логгера"""
        if hasattr(self.config, 'enable_logging') and self.config.enable_logging:
            logger.setLevel(self.config.log_level)
            if not logger.handlers:
                handler = logging.StreamHandler()
                handler.setFormatter(
                    logging.Formatter(
                        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                    )
                )
                logger.addHandler(handler)
    
    def _configure_yookassa(self):
        """Настройка YooKassa SDK"""
        try:
            Configuration.configure(
                account_id=self.config.shop_id,
                secret_key=self.config.secret_key
            )
            logger.info(
                f"YooKassa configured: shop_id={self.config.shop_id}, "
                f"test_mode={self.config.is_test}"
            )
        except Exception as e:
            logger.error(f"Failed to configure YooKassa: {e}")
            raise AuthenticationError("Failed to configure YooKassa", e)
    
    def _make_request_with_retry(
        self,
        func,
        *args,
        **kwargs
    ) -> Any:
        """
        Выполнение запроса с retry логикой
        
        Args:
            func: Функция для выполнения
            *args: Позиционные аргументы
            **kwargs: Именованные аргументы
            
        Returns:
            Any: Результат выполнения функции
            
        Raises:
            NetworkError: При сетевых ошибках
            AuthenticationError: При ошибках аутентификации
            ValidationError: При ошибках валидации
            PaymentError: При других ошибках
        """
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                # Логирование запроса
                if self.config.log_requests:
                    logger.debug(
                        f"API Request (attempt {attempt + 1}): "
                        f"{func.__name__} with args: {mask_sensitive_data(kwargs)}"
                    )
                
                # Выполнение запроса
                result = func(*args, **kwargs)
                
                # Логирование ответа
                if self.config.log_responses:
                    logger.debug(f"API Response: {type(result).__name__}")
                
                return result
                
            except UnauthorizedError as e:
                logger.error(f"Authentication error: {e}")
                raise AuthenticationError("Invalid credentials", e)
            
            except BadRequestError as e:
                logger.error(f"Validation error: {e}")
                raise ValidationError(str(e), e)
            
            except ApiError as e:
                last_exception = e
                logger.warning(
                    f"API error on attempt {attempt + 1}/{self.config.max_retries + 1}: {e}"
                )
                
                # Если это последняя попытка, прерываем
                if attempt >= self.config.max_retries:
                    break
                
                # Экспоненциальная задержка
                delay = min(2 ** attempt, 30)  # Максимум 30 секунд
                logger.info(f"Retrying in {delay} seconds...")
                time.sleep(delay)
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                raise PaymentError(f"Unexpected error: {e}", e)
        
        # Если все попытки исчерпаны
        raise NetworkError(
            f"Failed after {self.config.max_retries + 1} attempts",
            last_exception
        )
    
    async def create_payment(self, payment_data: Dict[str, Any], idempotency_key: str) -> Any:
        """
        Создание платежа
        
        Args:
            payment_data: Данные платежа
            idempotency_key: Ключ идемпотентности
            
        Returns:
            PaymentResponse: Объект платежа
        """
        logger.info(f"Creating payment with idempotency_key: {idempotency_key}")
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Payment.create,
            payment_data,
            idempotency_key
        )
    
    async def get_payment(self, payment_id: str) -> Any:
        """
        Получение информации о платеже
        
        Args:
            payment_id: ID платежа
            
        Returns:
            PaymentResponse: Объект платежа
        """
        logger.info(f"Getting payment: {payment_id}")
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Payment.find_one,
            payment_id
        )
    
    async def capture_payment(
        self,
        payment_id: str,
        amount: Optional[Dict[str, str]] = None,
        idempotency_key: Optional[str] = None
    ) -> Any:
        """
        Подтверждение платежа
        
        Args:
            payment_id: ID платежа
            amount: Сумма для подтверждения (опционально, для частичного подтверждения)
            idempotency_key: Ключ идемпотентности
            
        Returns:
            PaymentResponse: Объект платежа
        """
        logger.info(f"Capturing payment: {payment_id}")
        
        capture_data = {}
        if amount:
            capture_data['amount'] = amount
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Payment.capture,
            payment_id,
            capture_data,
            idempotency_key
        )
    
    async def cancel_payment(self, payment_id: str, idempotency_key: Optional[str] = None) -> Any:
        """
        Отмена платежа
        
        Args:
            payment_id: ID платежа
            idempotency_key: Ключ идемпотентности
            
        Returns:
            PaymentResponse: Объект платежа
        """
        logger.info(f"Canceling payment: {payment_id}")
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Payment.cancel,
            payment_id,
            idempotency_key
        )
    
    async def create_refund(self, refund_data: Dict[str, Any], idempotency_key: str) -> Any:
        """
        Создание возврата
        
        Args:
            refund_data: Данные возврата
            idempotency_key: Ключ идемпотентности
            
        Returns:
            RefundResponse: Объект возврата
        """
        logger.info(f"Creating refund with idempotency_key: {idempotency_key}")
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Refund.create,
            refund_data,
            idempotency_key
        )
    
    async def get_refund(self, refund_id: str) -> Any:
        """
        Получение информации о возврате
        
        Args:
            refund_id: ID возврата
            
        Returns:
            RefundResponse: Объект возврата
        """
        logger.info(f"Getting refund: {refund_id}")
        
        return await asyncio.to_thread(
            self._make_request_with_retry,
            Refund.find_one,
            refund_id
        )
    
    def list_payments(self, filters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Получение списка платежей
        
        Args:
            filters: Фильтры для выборки
            
        Returns:
            PaymentListResponse: Список платежей
        """
        logger.info(f"Listing payments with filters: {filters}")
        
        return self._make_request_with_retry(
            Payment.list,
            filters or {}
        )
    
    def list_refunds(self, filters: Optional[Dict[str, Any]] = None) -> Any:
        """
        Получение списка возвратов
        
        Args:
            filters: Фильтры для выборки
            
        Returns:
            RefundListResponse: Список возвратов
        """
        logger.info(f"Listing refunds with filters: {filters}")
        
        return self._make_request_with_retry(
            Refund.list,
            filters or {}
        )
