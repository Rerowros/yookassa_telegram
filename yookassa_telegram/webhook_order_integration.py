"""
Интеграция webhook с уведомлениями админов и обработкой заказов
"""

import logging
from typing import Optional, Protocol, Any
from aiogram import Bot
from aiogram.utils import markdown as md

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


class WebhookOrderIntegration:
    """
    Обработка webhook уведомлений с интеграцией в систему заказов
    """
    
    def __init__(
        self,
        bot: Bot,
        orders_database: OrderDatabaseProtocol,
        orders_manager: OrderManagerProtocol,
        admin_user_ids: list[int]
    ):
        """
        Args:
            bot: Экземпляр Telegram бота
            orders_database: База данных заказов (должна реализовывать OrderDatabaseProtocol)
            orders_manager: Менеджер заказов (должен реализовывать OrderManagerProtocol)
            admin_user_ids: Список ID администраторов для уведомлений
        """
        self.bot = bot
        self.orders_database = orders_database
        self.orders_manager = orders_manager
        self.admin_user_ids = admin_user_ids
    
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
                await self._notify_admins_error(order, str(e))
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
        
        # Отправляем уведомление пользователю
        if user_id:
            try:
                await self.bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Оплата получена!\n\n"
                         f"Заказ №{order_number} успешно оплачен.\n"
                         f"Товар будет отправлен в течение двух недель.\n\n"
                         f"Спасибо за покупку!"
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        
        # Уведомляем администраторов о новом заказе
        await self._notify_admins_new_order(order, notification)
    
    async def handle_payment_canceled(self, notification: WebhookNotification):
        """
        Обработка отмененного платежа
        
        - Уведомляет пользователя об отмене
        - Логирует событие
        """
        logger.info(f"Processing canceled payment: {notification.payment_id}")
        
        user_id = notification.metadata.get('user_id')
        order_number = notification.metadata.get('order_number')
        
        if user_id:
            try:
                await self.bot.send_message(
                    chat_id=int(user_id),
                    text=f"❌ Платеж отменен\n\n"
                         f"Заказ №{order_number or 'N/A'} не был оплачен.\n"
                         f"Вы можете попробовать оформить заказ снова."
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
    
    async def _notify_admins_new_order(
        self,
        order,
        notification: WebhookNotification
    ):
        """Отправка уведомлений администраторам о новом оплаченном заказе"""
        
        # Получаем текст заказа
        try:
            order_text = self.orders_manager.get_order_as_text(order.order_id)
        except Exception as e:
            logger.error(f"Error getting order text: {e}")
            order_text = f"Заказ #{order.order_number}"
        
        order_address = order.order_address or "Адрес не указан"
        
        # Получаем username пользователя (если доступен)
        username = notification.metadata.get('username', 'неизвестен')
        
        message_text = f"""🎉 Новый заказ #{md.hbold(str(order.order_number))} (оплачен через ЮKassa)

👤 От пользователя: @{username} (ID {order.user_id})

{order_text}

📍 Данные: {order_address}

💳 Payment ID: {md.hcode(notification.payment_id)}
💰 Сумма: {notification.amount} {notification.currency.value}

✅ Заказ автоматически подтвержден. Требуется отправка."""
        
        # Отправляем уведомление каждому админу
        for admin_id in self.admin_user_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=message_text,
                    parse_mode="HTML"
                )
                logger.info(f"Notified admin {admin_id} about order #{order.order_number}")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    async def _notify_admins_error(self, order, error_message: str):
        """Уведомление админов об ошибке при обработке платежа"""
        
        message_text = f"""⚠️ ОШИБКА при обработке платежа

Заказ #{order.order_number}
Пользователь ID: {order.user_id}

Ошибка: {error_message}

Требуется ручная проверка!"""
        
        for admin_id in self.admin_user_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id,
                    text=message_text
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id} about error: {e}")
