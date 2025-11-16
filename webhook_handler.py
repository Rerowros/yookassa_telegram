"""
Обработчик webhook уведомлений от YooKassa
"""

import hmac
import hashlib
import logging
from typing import Callable, Dict, Any, Optional, Awaitable
import json

from .config import YooKassaConfig
from .enums import WebhookEventType, PaymentStatus
from .exceptions import WebhookError, ValidationError
from .models import WebhookNotification
from .storage import PaymentStorage, InMemoryPaymentStorage


logger = logging.getLogger(__name__)


# Тип для callback функций
WebhookCallback = Callable[[WebhookNotification], Awaitable[None]]


class WebhookHandler:
    """
    Обработчик webhook уведомлений от YooKassa
    
    Обеспечивает:
    - Проверку подлинности webhook
    - Обработку различных типов событий
    - Callback'и для кастомной обработки
    - Обновление статусов в хранилище
    """
    
    def __init__(
        self,
        config: YooKassaConfig,
        storage: Optional[PaymentStorage] = None
    ):
        """
        Инициализация обработчика
        
        Args:
            config: Конфигурация YooKassa
            storage: Хранилище для платежей
        """
        self.config = config
        self.storage = storage or InMemoryPaymentStorage()
        self._callbacks: Dict[WebhookEventType, list[WebhookCallback]] = {}
        
        logger.info("WebhookHandler initialized")
    
    def register_callback(
        self,
        event_type: WebhookEventType,
        callback: WebhookCallback
    ):
        """
        Регистрация callback функции для события
        
        Args:
            event_type: Тип события
            callback: Async функция-обработчик
            
        Example:
            async def on_payment_succeeded(notification: WebhookNotification):
                print(f"Payment succeeded: {notification.payment_id}")
            
            handler.register_callback(
                WebhookEventType.PAYMENT_SUCCEEDED,
                on_payment_succeeded
            )
        """
        if event_type not in self._callbacks:
            self._callbacks[event_type] = []
        
        self._callbacks[event_type].append(callback)
        logger.info(f"Registered callback for event: {event_type}")
    
    async def handle_webhook(
        self,
        payload: str | bytes | dict,
        headers: Optional[Dict[str, str]] = None
    ) -> WebhookNotification:
        """
        Обработка webhook уведомления
        
        Args:
            payload: Тело запроса (JSON string, bytes или dict)
            headers: Заголовки запроса (для проверки подписи)
            
        Returns:
            WebhookNotification: Обработанное уведомление
            
        Raises:
            WebhookError: При ошибке обработки
            ValidationError: При невалидных данных
        """
        try:
            # Конвертируем payload в dict
            if isinstance(payload, bytes):
                payload_str = payload.decode('utf-8')
                data = json.loads(payload_str)
            elif isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload
            
            # Проверяем структуру данных
            if not isinstance(data, dict) or 'event' not in data:
                logger.error("Invalid webhook payload structure")
                raise ValidationError("Invalid webhook payload structure")
            
            # Создаем объект уведомления
            notification = WebhookNotification.from_api_response(data)
            
            logger.info(
                f"Processing webhook: event={notification.event}, "
                f"payment_id={notification.payment_id}, "
                f"status={notification.status}"
            )
            
            # Обновляем статус в хранилище
            await self._update_payment_status(notification)
            
            # Вызываем зарегистрированные callback'и
            await self._execute_callbacks(notification)
            
            return notification
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse webhook payload: {e}")
            raise WebhookError("Invalid JSON in webhook payload", e)
        
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            raise WebhookError(f"Error processing webhook: {e}", e)
    
    async def _update_payment_status(self, notification: WebhookNotification):
        """Обновление статуса платежа в хранилище"""
        try:
            await self.storage.update_payment_status(
                notification.payment_id,
                notification.status,
                {'last_webhook_event': notification.event}
            )
            logger.debug(
                f"Payment status updated: {notification.payment_id} -> "
                f"{notification.status}"
            )
        except Exception as e:
            logger.warning(f"Failed to update payment status: {e}")
    
    async def _execute_callbacks(self, notification: WebhookNotification):
        """Выполнение зарегистрированных callback'ов"""
        event_type = self._get_event_type(notification.event)
        
        if event_type and event_type in self._callbacks:
            callbacks = self._callbacks[event_type]
            logger.debug(
                f"Executing {len(callbacks)} callbacks for event: {event_type}"
            )
            
            for callback in callbacks:
                try:
                    await callback(notification)
                except Exception as e:
                    logger.error(
                        f"Error in callback for {event_type}: {e}",
                        exc_info=True
                    )
    
    @staticmethod
    def _get_event_type(event: str) -> Optional[WebhookEventType]:
        """Получение типа события из строки"""
        try:
            return WebhookEventType(event)
        except ValueError:
            logger.warning(f"Unknown event type: {event}")
            return None
    
    @staticmethod
    def verify_signature(
        payload: str | bytes,
        signature: str,
        secret_key: str
    ) -> bool:
        """
        Проверка подписи webhook (если YooKassa поддерживает)
        
        Args:
            payload: Тело запроса
            signature: Подпись из заголовков
            secret_key: Секретный ключ
            
        Returns:
            bool: Валидна ли подпись
        """
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)


def create_webhook_handler(
    config: YooKassaConfig,
    storage: Optional[PaymentStorage] = None,
    on_payment_succeeded: Optional[WebhookCallback] = None,
    on_payment_canceled: Optional[WebhookCallback] = None,
    on_payment_waiting_for_capture: Optional[WebhookCallback] = None,
    on_refund_succeeded: Optional[WebhookCallback] = None
) -> WebhookHandler:
    """
    Создание обработчика webhook с предустановленными callback'ами
    
    Args:
        config: Конфигурация YooKassa
        storage: Хранилище
        on_payment_succeeded: Callback для успешных платежей
        on_payment_canceled: Callback для отмененных платежей
        on_payment_waiting_for_capture: Callback для платежей, ожидающих подтверждения
        on_refund_succeeded: Callback для успешных возвратов
        
    Returns:
        WebhookHandler: Настроенный обработчик
        
    Example:
        async def on_success(notification):
            print(f"Payment succeeded: {notification.payment_id}")
        
        handler = create_webhook_handler(
            config,
            on_payment_succeeded=on_success
        )
    """
    handler = WebhookHandler(config, storage)
    
    if on_payment_succeeded:
        handler.register_callback(
            WebhookEventType.PAYMENT_SUCCEEDED,
            on_payment_succeeded
        )
    
    if on_payment_canceled:
        handler.register_callback(
            WebhookEventType.PAYMENT_CANCELED,
            on_payment_canceled
        )
    
    if on_payment_waiting_for_capture:
        handler.register_callback(
            WebhookEventType.PAYMENT_WAITING_FOR_CAPTURE,
            on_payment_waiting_for_capture
        )
    
    if on_refund_succeeded:
        handler.register_callback(
            WebhookEventType.REFUND_SUCCEEDED,
            on_refund_succeeded
        )
    
    return handler
