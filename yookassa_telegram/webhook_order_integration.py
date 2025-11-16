"""
Интеграция webhook с уведомлениями админов и обработкой заказов
"""

import logging
from typing import Optional, Protocol, Any, Callable, Awaitable
from aiogram import Bot

from .models import WebhookNotification
from .enums import PaymentStatus


class OrderDatabaseProtocol(Protocol):
    """Протокол для базы данных заказов"""
    
    def get_order_by_number(self, order_number: int) -> Any:
        """Получить заказ по номеру"""
        ...
    
    def convert_cart_to_order(self, order_id: str) -> None:
        """Конвертировать корзину в заказ"""
        ...
    
    def set_is_payment_done(self, order_id: str, is_done: bool) -> None:
        """Установить статус оплаты заказа"""
        ...


class OrderManagerProtocol(Protocol):
    """Протокол для менеджера заказов"""
    
    def deduct_stock_for_order(self, order_id: str) -> None:
        """Списать товары со склада для заказа"""
        ...
    
    def get_order_as_text(self, order_id: str) -> str:
        """Получить текстовое представление заказа"""
        ...

logger = logging.getLogger(__name__)


# Типы для callback-функций
NotifyUserSuccessCallback = Callable[[Bot, int, int, str], Awaitable[None]]
NotifyUserCanceledCallback = Callable[[Bot, int, Optional[int]], Awaitable[None]]
NotifyAdminsNewOrderCallback = Callable[[Bot, list[int], Any, WebhookNotification], Awaitable[None]]
NotifyAdminsErrorCallback = Callable[[Bot, list[int], Any, str], Awaitable[None]]


class WebhookOrderIntegration:
    """
    Обработка webhook уведомлений с интеграцией в систему заказов
    
    Пакет больше не содержит hardcoded логику уведомлений.
    Все уведомления передаются через callback-функции из вашего проекта.
    """
    
    def __init__(
        self,
        bot: Bot,
        orders_database: OrderDatabaseProtocol,
        orders_manager: OrderManagerProtocol,
        admin_user_ids: list[int],
        notify_user_success: Optional[NotifyUserSuccessCallback] = None,
        notify_user_canceled: Optional[NotifyUserCanceledCallback] = None,
        notify_admins_new_order: Optional[NotifyAdminsNewOrderCallback] = None,
        notify_admins_error: Optional[NotifyAdminsErrorCallback] = None,
    ):
        """
        Args:
            bot: Экземпляр Telegram бота
            orders_database: База данных заказов (должна реализовывать OrderDatabaseProtocol)
            orders_manager: Менеджер заказов (должен реализовывать OrderManagerProtocol)
            admin_user_ids: Список ID администраторов для уведомлений
            notify_user_success: Callback для уведомления пользователя об успешной оплате
            notify_user_canceled: Callback для уведомления пользователя об отмене платежа
            notify_admins_new_order: Callback для уведомления админов о новом заказе
            notify_admins_error: Callback для уведомления админов об ошибке
        """
        self.bot = bot
        self.orders_database = orders_database
        self.orders_manager = orders_manager
        self.admin_user_ids = admin_user_ids
        
        # Callback-функции для уведомлений (опциональны)
        self.notify_user_success = notify_user_success
        self.notify_user_canceled = notify_user_canceled
        self.notify_admins_new_order = notify_admins_new_order
        self.notify_admins_error = notify_admins_error
    
    async def handle_payment_succeeded(self, notification: WebhookNotification):
        """
        Обработка успешного платежа через webhook
        
        - Помечает заказ как оплаченный
        - Списывает товары со склада
        - Уведомляет администраторов
        - Удаляет сообщение с кнопкой "Оплатил"
        """
        logger.info(f"Processing successful payment: {notification.payment_id}")
        
        # Получаем order_id из metadata
        order_number = notification.metadata.get('order_number')
        user_id = notification.metadata.get('user_id')
        
        if not order_number:
            logger.warning(f"No order_number in payment metadata: {notification.payment_id}")
            return
        
        try:
            order_number_int = int(order_number)
        except (ValueError, TypeError):
            logger.error(f"Invalid order_number: {order_number}")
            return
        
        # Получаем заказ из БД
        order = self.orders_database.get_order_by_number(order_number_int)
        
        if not order:
            logger.warning(f"Order not found: {order_number}")
            return
        
        # Проверяем, не был ли уже оплачен
        if order.is_payment_done:
            logger.info(f"Order {order_number} already marked as paid")
            return
        
        # Конвертируем корзину в заказ, если это корзина
        if order.is_cart:
            try:
                # Списываем товары со склада
                self.orders_manager.deduct_stock_for_order(order.order_id)
                
                # Конвертируем корзину в заказ
                self.orders_database.convert_cart_to_order(order.order_id)
                logger.info(f"Cart {order.order_id} converted to order #{order_number}")
            except Exception as e:
                logger.error(f"Error converting cart to order: {e}", exc_info=True)
                # Уведомляем админов об ошибке
                await self._handle_conversion_error(order, str(e))
                return
        
        # Помечаем заказ как оплаченный
        self.orders_database.set_is_payment_done(order.order_id, True)
        logger.info(f"Order #{order_number} marked as paid via webhook")
        
        # Удаляем сообщение с кнопкой "Оплатил" если есть payment_message_id
        if order.payment_message_id and user_id:
            try:
                await self.bot.delete_message(
                    chat_id=int(user_id),
                    message_id=order.payment_message_id
                )
                logger.info(f"Deleted payment message {order.payment_message_id}")
            except Exception as e:
                logger.warning(f"Failed to delete payment message: {e}")
        
        # Отправляем уведомление пользователю через callback
        if user_id and self.notify_user_success:
            try:
                await self.notify_user_success(
                    self.bot,
                    int(user_id),
                    order_number_int,
                    notification.payment_id
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        
        # Уведомляем администраторов о новом заказе через callback
        if self.notify_admins_new_order:
            try:
                await self.notify_admins_new_order(
                    self.bot,
                    self.admin_user_ids,
                    order,
                    notification
                )
            except Exception as e:
                logger.error(f"Failed to notify admins: {e}")
    
    async def handle_payment_canceled(self, notification: WebhookNotification):
        """
        Обработка отмененного платежа
        
        - Уведомляет пользователя об отмене через callback
        - Логирует событие
        """
        logger.info(f"Processing canceled payment: {notification.payment_id}")
        
        user_id = notification.metadata.get('user_id')
        order_number = notification.metadata.get('order_number')
        
        if user_id and self.notify_user_canceled:
            try:
                order_number_int = int(order_number) if order_number else None
                await self.notify_user_canceled(
                    self.bot,
                    int(user_id),
                    order_number_int
                )
            except Exception as e:
                logger.error(f"Failed to notify user about cancellation: {e}")
    
    async def handle_payment_waiting_for_capture(self, notification: WebhookNotification):
        """
        Обработка платежа, ожидающего подтверждения
        
        В зависимости от настроек может автоматически подтверждать платеж
        """
        logger.info(f"Payment waiting for capture: {notification.payment_id}")
        
        # Здесь можно добавить логику автоматического подтверждения
        # или уведомления админов о необходимости подтверждения
    
    async def _handle_conversion_error(self, order, error_message: str):
        """Обработка ошибки при конвертации корзины в заказ"""
        logger.error(f"Error converting cart to order: {error_message}", exc_info=True)
        
        # Уведомляем админов об ошибке через callback
        if self.notify_admins_error:
            try:
                await self.notify_admins_error(
                    self.bot,
                    self.admin_user_ids,
                    order,
                    error_message
                )
            except Exception as e:
                logger.error(f"Failed to notify admins about error: {e}")
