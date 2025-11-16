"""
Задача для автоматической обработки отмененных платежей YooKassa
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Protocol
from aiogram import Bot

from .payment_service import PaymentService
from .enums import PaymentStatus


logger = logging.getLogger(__name__)


class OrderDatabaseProtocol(Protocol):
    """Протокол для базы данных заказов"""
    
    def get_unpaid_orders_needing_action(self) -> list[Any]:
        """Получить неоплаченные заказы, требующие действия"""
        ...
    
    def set_is_payment_done(self, order_id: str, is_done: bool) -> None:
        """Установить статус оплаты заказа"""
        ...
    
    def delete_order(self, order_id: str) -> None:
        """Удалить заказ"""
        ...
    
    def get_order_by_number(self, order_number: int) -> Any:
        """Получить заказ по номеру"""
        ...
    
    def convert_cart_to_order(self, order_id: str) -> None:
        """Конвертировать корзину в заказ"""
        ...


class OrderManagerProtocol(Protocol):
    """Протокол для менеджера заказов"""
    
    def return_stock_for_order(self, order_id: str) -> None:
        """Вернуть товары на склад для заказа"""
        ...
    
    def deduct_stock_for_order(self, order_id: str) -> None:
        """Списать товары со склада для заказа"""
        ...
    
    def get_order_as_text(self, order_id: str) -> str:
        """Получить текстовое представление заказа"""
        ...


class PaymentExpirationChecker:
    """
    Проверяет статусы платежей в YooKassa и обрабатывает отмененные заказы.
    
    Вместо таймера полагается на статус платежа в YooKassa.
    YooKassa автоматически отменяет неоплаченные платежи через определенное время.
    """
    
    def __init__(
        self,
        bot: Bot,
        orders_database: OrderDatabaseProtocol,
        orders_manager: OrderManagerProtocol,
        payment_service: PaymentService,
        check_interval_seconds: int = 60,
        min_order_age_minutes: int = 5  # минимальный возраст заказа для проверки
    ):
        """
        Args:
            bot: Экземпляр Telegram бота
            orders_database: База данных заказов (должна реализовывать OrderDatabaseProtocol)
            orders_manager: Менеджер заказов (должна реализовывать OrderManagerProtocol)
            payment_service: Сервис платежей
            check_interval_seconds: Интервал проверки в секундах
            min_order_age_minutes: Минимальный возраст заказа для проверки (избегаем проверки совсем свежих заказов)
        """
        self.bot = bot
        self.orders_database = orders_database
        self.orders_manager = orders_manager
        self.payment_service = payment_service
        self.check_interval_seconds = check_interval_seconds
        self.min_order_age_minutes = min_order_age_minutes
        self._running = False
        self._task = None
    
    async def start(self):
        """Запуск периодической проверки"""
        if self._running:
            logger.warning("Payment expiration checker already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(
            f"Payment status checker started "
            f"(check interval: {self.check_interval_seconds} sec, "
            f"min order age: {self.min_order_age_minutes} min)"
        )
    
    async def stop(self):
        """Остановка проверки"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Payment expiration checker stopped")
    
    async def _check_loop(self):
        """Основной цикл проверки"""
        while self._running:
            try:
                await self._check_payment_statuses()
            except Exception as e:
                logger.error(f"Error in payment status check: {e}", exc_info=True)
            
            # Ждём перед следующей проверкой
            await asyncio.sleep(self.check_interval_seconds)
    
    async def _check_payment_statuses(self):
        """Проверка статусов платежей через YooKassa API"""
        
        # Получаем все неоплаченные заказы (не корзины) с payment_id
        unpaid_orders = self.orders_database.get_unpaid_orders_needing_action()
        
        now = datetime.now(timezone.utc)
        min_age_delta = timedelta(minutes=self.min_order_age_minutes)
        
        for order in unpaid_orders:
            # Пропускаем заказы без payment_id
            if not order.payment_id:
                logger.debug(f"Order #{order.order_number} has no payment_id, skipping")
                continue
            
            # Пропускаем слишком свежие заказы (даем пользователю время на оплату)
            if order.created_at:
                order_age = now - order.created_at
                if order_age < min_age_delta:
                    continue
            
            # Проверяем статус платежа в YooKassa
            try:
                await self._process_order_payment(order)
            except Exception as e:
                logger.error(f"Error processing order #{order.order_number}: {e}", exc_info=True)
    
    async def _process_order_payment(self, order):
        """Обработка статуса платежа для конкретного заказа"""
        
        try:
            payment_data = await self.payment_service.get_payment(order.payment_id)
            
            if not payment_data:
                logger.warning(f"Could not get payment data for order #{order.order_number}, payment_id={order.payment_id}")
                return
            
            # Обрабатываем разные статусы
            if payment_data.status == PaymentStatus.SUCCEEDED:
                # Платёж успешно оплачен, но почему-то is_payment_done=False
                # Возможно webhook не сработал
                logger.warning(
                    f"Order #{order.order_number} has SUCCEEDED payment "
                    f"but is_payment_done=False. Marking as paid. "
                    f"Payment ID: {order.payment_id}"
                )
                self.orders_database.set_is_payment_done(order.order_id, True)
                
                # Уведомляем пользователя
                try:
                    await self.bot.send_message(
                        chat_id=order.user_id,
                        text=f"✅ Ваш заказ №{order.order_number} оплачен!\n\n"
                             f"Товар будет отправлен в течение двух недель.\n"
                             f"Спасибо за покупку!"
                    )
                    logger.info(f"Notified user {order.user_id} about successful payment")
                except Exception as e:
                    logger.error(f"Failed to notify user {order.user_id}: {e}")
            
            elif payment_data.status == PaymentStatus.CANCELED:
                # Платёж отменен YooKassa (истекло время или пользователь отменил)
                logger.info(
                    f"Order #{order.order_number} has CANCELED payment. "
                    f"Canceling order and returning stock. Payment ID: {order.payment_id}"
                )
                await self._cancel_order(order, reason="платеж отменен")
            
            elif payment_data.status == PaymentStatus.PENDING:
                # Платёж в обработке, ничего не делаем
                logger.debug(f"Order #{order.order_number} payment is PENDING")
                
            elif payment_data.status == PaymentStatus.WAITING_FOR_CAPTURE:
                # Платёж ожидает подтверждения (двухстадийный платеж)
                logger.debug(f"Order #{order.order_number} payment is WAITING_FOR_CAPTURE")
            
            else:
                logger.warning(
                    f"Order #{order.order_number} has unexpected payment status: {payment_data.status}. "
                    f"Payment ID: {order.payment_id}"
                )
                
        except Exception as e:
            logger.error(f"Error checking payment status for order #{order.order_number}: {e}", exc_info=True)
    
    async def _cancel_order(self, order, reason: str = "неизвестная причина"):
        """Отмена заказа и возврат товаров"""
        
        logger.info(f"Canceling order #{order.order_number}, reason: {reason}")
    async def _cancel_order(self, order, reason: str = "неизвестная причина"):
        """Отмена заказа и возврат товаров"""
        
        logger.info(f"Canceling order #{order.order_number}, reason: {reason}")
        
        # Возвращаем товары на склад
        try:
            self.orders_manager.return_stock_for_order(order.order_id)
            logger.info(f"Stock returned for order #{order.order_number}")
        except Exception as e:
            logger.error(f"Error returning stock for order #{order.order_number}: {e}", exc_info=True)
        
        # Удаляем заказ из БД
        try:
            self.orders_database.delete_order(order.order_id)
            logger.info(f"Deleted canceled order #{order.order_number}")
        except Exception as e:
            logger.error(f"Error deleting order #{order.order_number}: {e}", exc_info=True)
        
        # Уведомляем пользователя
        try:
            await self.bot.send_message(
                chat_id=order.user_id,
                text=f"❌ Заказ №{order.order_number} отменен.\n\n"
                     f"Платеж был отменен (возможно, истекло время на оплату).\n"
                     f"Товары возвращены на склад.\n\n"
                     f"Вы можете оформить новый заказ в любое время.",
                reply_markup=None
            )
            logger.info(f"Notified user {order.user_id} about order cancellation")
        except Exception as e:
            logger.error(f"Failed to notify user {order.user_id}: {e}")


async def start_payment_expiration_checker(
    bot: Bot,
    orders_database: OrderDatabaseProtocol,
    orders_manager: OrderManagerProtocol,
    payment_service: PaymentService,
    check_interval_seconds: int = 60,
    min_order_age_minutes: int = 10
) -> PaymentExpirationChecker:
    """
    Создаёт и запускает проверку статусов платежей в YooKassa
    
    Args:
        bot: Telegram бот
        orders_database: База данных заказов (должна реализовывать OrderDatabaseProtocol)
        orders_manager: Менеджер заказов (должна реализовывать OrderManagerProtocol)
        payment_service: Сервис платежей
        check_interval_seconds: Интервал проверки в секундах
        min_order_age_minutes: Минимальный возраст заказа для проверки
    
    Returns:
        PaymentExpirationChecker: Запущенный checker
    """
    checker = PaymentExpirationChecker(
        bot=bot,
        orders_database=orders_database,
        orders_manager=orders_manager,
        payment_service=payment_service,
        check_interval_seconds=check_interval_seconds,
        min_order_age_minutes=min_order_age_minutes
    )
    
    await checker.start()
    return checker
