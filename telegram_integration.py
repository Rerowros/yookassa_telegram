"""
Интеграция с Telegram Bot (aiogram 3.x)
"""

import logging
from decimal import Decimal
from typing import Optional, Callable, Awaitable

from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command

from .config import YooKassaConfig
from .enums import PaymentStatus, Currency, VATCode, PaymentSubject
from .models import CustomerInfo, PaymentItem
from .payment_service import PaymentService
from .receipt_service import ReceiptService
from .refund_service import RefundService
from .storage import PaymentStorage


logger = logging.getLogger(__name__)


class TelegramPaymentIntegration:
    """
    Интеграция платежей YooKassa с Telegram ботом
    
    Предоставляет готовые методы для:
    - Создания кнопок оплаты
    - Обработки платежей
    - Отправки уведомлений о статусе
    - Обработки возвратов
    """
    
    def __init__(
        self,
        config: YooKassaConfig,
        payment_service: PaymentService,
        receipt_service: ReceiptService,
        refund_service: RefundService,
        storage: Optional[PaymentStorage] = None
    ):
        """
        Инициализация интеграции
        
        Args:
            config: Конфигурация YooKassa
            payment_service: Сервис платежей
            receipt_service: Сервис чеков
            refund_service: Сервис возвратов
            storage: Хранилище
        """
        self.config = config
        self.payment_service = payment_service
        self.receipt_service = receipt_service
        self.refund_service = refund_service
        self.storage = storage
        
        logger.info("TelegramPaymentIntegration initialized")
    
    @staticmethod
    def create_payment_keyboard(
        payment_url: str,
        button_text: str = "💳 Оплатить"
    ) -> InlineKeyboardMarkup:
        """
        Создание клавиатуры с кнопкой оплаты
        
        Args:
            payment_url: URL для оплаты
            button_text: Текст кнопки
            
        Returns:
            InlineKeyboardMarkup: Клавиатура
        """
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=button_text, url=payment_url)]
            ]
        )
    
    async def create_payment_for_user(
        self,
        user_id: int,
        amount: Decimal | float | int | str,
        description: str,
        order_id: str,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None,
        user_full_name: Optional[str] = None,
        items: Optional[list[PaymentItem]] = None,
        metadata: Optional[dict] = None
    ) -> tuple[str, str]:
        """
        Создание платежа для пользователя Telegram
        
        Args:
            user_id: ID пользователя в Telegram
            amount: Сумма платежа
            description: Описание платежа
            order_id: ID заказа
            user_email: Email пользователя
            user_phone: Телефон пользователя
            user_full_name: ФИО пользователя
            items: Позиции для чека (опционально)
            metadata: Дополнительные данные
            
        Returns:
            tuple: (payment_id, payment_url)
        """
        logger.info(
            f"Creating payment for Telegram user: {user_id}, "
            f"order: {order_id}, amount: {amount}"
        )
        
        # Создаем объект покупателя
        customer = CustomerInfo(
            email=user_email,
            phone=user_phone,
            full_name=user_full_name
        )
        
        # Валидируем данные покупателя
        if not customer.validate():
            raise ValueError(
                "At least email or phone is required for customer"
            )
        
        # Создаем чек, если включены чеки и переданы items
        receipt = None
        if self.config.enable_receipts and items:
            receipt = self.receipt_service.create_receipt(
                customer=customer,
                items=items
            )
        elif self.config.enable_receipts:
            # Создаем простой чек с одной позицией
            receipt = self.receipt_service.create_simple_receipt(
                customer=customer,
                description=description,
                amount=amount,
                vat_code=VATCode.NO_VAT,
                payment_subject=PaymentSubject.SERVICE
            )
        
        # Добавляем user_id в метаданные
        if metadata is None:
            metadata = {}
        metadata['user_id'] = str(user_id)
        
        # Создаем платеж
        payment = await self.payment_service.create_payment(
            amount=amount,
            order_id=order_id,
            description=description,
            customer=customer,
            receipt=receipt,
            currency=Currency.RUB,
            metadata=metadata
        )
        
        if not payment.confirmation_url:
            raise ValueError("Payment URL not received from YooKassa")
        
        logger.info(
            f"Payment created: {payment.payment_id}, "
            f"URL: {payment.confirmation_url}"
        )
        
        return payment.payment_id, payment.confirmation_url
    
    async def send_payment_message(
        self,
        message: Message,
        amount: Decimal | float | int | str,
        description: str,
        order_id: str,
        user_email: Optional[str] = None,
        user_phone: Optional[str] = None,
        items: Optional[list[PaymentItem]] = None,
        custom_text: Optional[str] = None
    ) -> Message:
        """
        Отправка сообщения с кнопкой оплаты
        
        Args:
            message: Сообщение от пользователя
            amount: Сумма платежа
            description: Описание
            order_id: ID заказа
            user_email: Email
            user_phone: Телефон
            items: Позиции для чека
            custom_text: Кастомный текст сообщения
            
        Returns:
            Message: Отправленное сообщение
        """
        try:
            # Создаем платеж
            payment_id, payment_url = await self.create_payment_for_user(
                user_id=message.from_user.id,
                amount=amount,
                description=description,
                order_id=order_id,
                user_email=user_email,
                user_phone=user_phone,
                user_full_name=message.from_user.full_name,
                items=items
            )
            
            # Формируем текст сообщения
            if custom_text:
                text = custom_text
            else:
                if isinstance(amount, str):
                    amount = Decimal(amount)
                elif not isinstance(amount, Decimal):
                    amount = Decimal(str(amount))
                
                text = (
                    f"💰 <b>Счет на оплату</b>\n\n"
                    f"📝 {description}\n"
                    f"💵 Сумма: <b>{amount:.2f} ₽</b>\n"
                    f"🔢 Номер заказа: <code>{order_id}</code>\n\n"
                    f"Нажмите кнопку ниже для оплаты:"
                )
            
            # Создаем клавиатуру
            keyboard = self.create_payment_keyboard(payment_url)
            
            # Отправляем сообщение
            return await message.answer(
                text,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Error sending payment message: {e}")
            await message.answer(
                "❌ Произошла ошибка при создании платежа. "
                "Попробуйте позже."
            )
            raise
    
    async def check_payment_status(
        self,
        payment_id: str
    ) -> tuple[PaymentStatus, Optional[dict]]:
        """
        Проверка статуса платежа
        
        Args:
            payment_id: ID платежа
            
        Returns:
            tuple: (status, metadata)
        """
        payment = await self.payment_service.get_payment(payment_id)
        return payment.status, payment.metadata
    
    async def send_payment_success_notification(
        self,
        bot,
        user_id: int,
        payment_id: str,
        amount: Decimal,
        order_id: str
    ):
        """
        Отправка уведомления об успешной оплате
        
        Args:
            bot: Объект бота
            user_id: ID пользователя
            payment_id: ID платежа
            amount: Сумма
            order_id: ID заказа
        """
        text = (
            f"Платеж успешно выполнен\n\n"
            f"Сумма: {amount:.2f} ₽\n"
            f"Номер заказа: {order_id}\n"
            f"ID {payment_id}\n\n"
        )
        
        await bot.send_message(user_id, text)
    
    async def send_payment_canceled_notification(
        self,
        bot,
        user_id: int,
        payment_id: str,
        order_id: str
    ):
        """
        Отправка уведомления об отмене платежа
        
        Args:
            bot: Объект бота
            user_id: ID пользователя
            payment_id: ID платежа
            order_id: ID заказа
        """
        text = (
            f"❌ <b>Платеж отменен</b>\n\n"
            f"🔢 Номер заказа: <code>{order_id}</code>\n"
            f"🆔 ID платежа: <code>{payment_id}</code>\n\n"
            f"Если у вас возникли вопросы, обратитесь в поддержку."
        )
        
        await bot.send_message(user_id, text)


def create_payment_router(
    payment_integration: TelegramPaymentIntegration
) -> Router:
    """
    Создание роутера с базовыми обработчиками платежей
    
    Args:
        payment_integration: Интеграция платежей
        
    Returns:
        Router: Роутер для регистрации в диспетчере
        
    Example:
        router = create_payment_router(payment_integration)
        dp.include_router(router)
    """
    router = Router(name="payment")
    
    @router.message(Command("pay"))
    async def cmd_pay(message: Message):
        """
        Команда для тестовой оплаты
        
        Использование: /pay <сумма> <описание>
        Пример: /pay 100 Тестовый платеж
        """
        args = message.text.split(maxsplit=2)
        
        if len(args) < 3:
            await message.answer(
                "ℹ️ Использование: /pay <сумма> <описание>\n"
                "Пример: /pay 100 Тестовый платеж"
            )
            return
        
        try:
            amount = Decimal(args[1])
            description = args[2]
            
            # Генерируем order_id
            from .utils import generate_order_id
            order_id = generate_order_id()
            
            # Отправляем платеж (без email/phone для теста)
            # В реальном приложении нужно сначала собрать контакты
            await message.answer(
                "⚠️ Для оплаты необходимо указать email или телефон.\n"
                "Это требование 54-ФЗ для формирования чека."
            )
            
        except ValueError:
            await message.answer("❌ Неверный формат суммы. Используйте число.")
        except Exception as e:
            logger.error(f"Error in /pay command: {e}")
            await message.answer("❌ Произошла ошибка. Попробуйте позже.")
    
    return router
