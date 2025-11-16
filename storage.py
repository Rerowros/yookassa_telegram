"""
Абстракция для хранения данных о платежах
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
import logging

from .models import PaymentData, RefundData
from .enums import PaymentStatus


logger = logging.getLogger(__name__)


class PaymentStorage(ABC):
    """
    Абстрактный класс для хранения данных о платежах
    
    Позволяет использовать разные backend'ы для хранения:
    - In-memory (для тестов)
    - SQLite/PostgreSQL (для production)
    - Redis (для кэширования)
    """
    
    @abstractmethod
    async def save_payment(self, payment: PaymentData) -> bool:
        """Сохранить платеж"""
        pass
    
    @abstractmethod
    async def get_payment(self, payment_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID"""
        pass
    
    @abstractmethod
    async def get_payment_by_order_id(self, order_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID заказа"""
        pass
    
    @abstractmethod
    async def update_payment_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Обновить статус платежа"""
        pass
    
    @abstractmethod
    async def save_refund(self, refund: RefundData) -> bool:
        """Сохранить возврат"""
        pass
    
    @abstractmethod
    async def get_refund(self, refund_id: str) -> Optional[RefundData]:
        """Получить возврат по ID"""
        pass
    
    @abstractmethod
    async def get_payments_by_user(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[PaymentData]:
        """Получить платежи пользователя"""
        pass


class InMemoryPaymentStorage(PaymentStorage):
    """
    In-memory хранилище для платежей
    Подходит для тестирования и разработки
    """
    
    def __init__(self):
        self._payments: Dict[str, PaymentData] = {}
        self._refunds: Dict[str, RefundData] = {}
        self._payment_by_order: Dict[str, str] = {}  # order_id -> payment_id
    
    async def save_payment(self, payment: PaymentData) -> bool:
        """Сохранить платеж"""
        try:
            if payment.payment_id:
                self._payments[payment.payment_id] = payment
                self._payment_by_order[payment.order_id] = payment.payment_id
                logger.debug(f"Payment saved: {payment.payment_id}")
                return True
            logger.error("Cannot save payment without payment_id")
            return False
        except Exception as e:
            logger.error(f"Error saving payment: {e}")
            return False
    
    async def get_payment(self, payment_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID"""
        return self._payments.get(payment_id)
    
    async def get_payment_by_order_id(self, order_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID заказа"""
        payment_id = self._payment_by_order.get(order_id)
        if payment_id:
            return self._payments.get(payment_id)
        return None
    
    async def update_payment_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Обновить статус платежа"""
        try:
            payment = self._payments.get(payment_id)
            if payment:
                payment.status = status
                if metadata:
                    payment.metadata.update(metadata)
                logger.debug(f"Payment status updated: {payment_id} -> {status}")
                return True
            logger.error(f"Payment not found: {payment_id}")
            return False
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            return False
    
    async def save_refund(self, refund: RefundData) -> bool:
        """Сохранить возврат"""
        try:
            if refund.refund_id:
                self._refunds[refund.refund_id] = refund
                logger.debug(f"Refund saved: {refund.refund_id}")
                return True
            logger.error("Cannot save refund without refund_id")
            return False
        except Exception as e:
            logger.error(f"Error saving refund: {e}")
            return False
    
    async def get_refund(self, refund_id: str) -> Optional[RefundData]:
        """Получить возврат по ID"""
        return self._refunds.get(refund_id)
    
    async def get_payments_by_user(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[PaymentData]:
        """Получить платежи пользователя"""
        # Фильтруем платежи по user_id в метаданных
        user_payments = [
            p for p in self._payments.values()
            if p.metadata.get('user_id') == user_id
        ]
        
        # Сортируем по дате создания
        user_payments.sort(
            key=lambda x: x.created_at or datetime.min,
            reverse=True
        )
        
        return user_payments[offset:offset + limit]
    
    def clear(self):
        """Очистить все данные (для тестов)"""
        self._payments.clear()
        self._refunds.clear()
        self._payment_by_order.clear()


class JSONFilePaymentStorage(PaymentStorage):
    """
    Хранилище в JSON файле
    Подходит для простых случаев и прототипирования
    """
    
    def __init__(self, file_path: str = "payments.json"):
        self.file_path = file_path
        self._load_data()
    
    def _load_data(self):
        """Загрузка данных из файла"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._payments = data.get('payments', {})
                self._refunds = data.get('refunds', {})
                self._payment_by_order = data.get('payment_by_order', {})
        except FileNotFoundError:
            self._payments = {}
            self._refunds = {}
            self._payment_by_order = {}
            self._save_data()
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            self._payments = {}
            self._refunds = {}
            self._payment_by_order = {}
    
    def _save_data(self):
        """Сохранение данных в файл"""
        try:
            data = {
                'payments': self._payments,
                'refunds': self._refunds,
                'payment_by_order': self._payment_by_order
            }
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    async def save_payment(self, payment: PaymentData) -> bool:
        """Сохранить платеж"""
        try:
            if payment.payment_id:
                # Конвертируем в dict для сериализации
                payment_dict = {
                    'payment_id': payment.payment_id,
                    'order_id': payment.order_id,
                    'amount': str(payment.amount),
                    'currency': payment.currency.value,
                    'description': payment.description,
                    'status': payment.status.value if payment.status else None,
                    'confirmation_url': payment.confirmation_url,
                    'created_at': payment.created_at.isoformat() if payment.created_at else None,
                    'metadata': payment.metadata,
                    'capture': payment.capture
                }
                
                self._payments[payment.payment_id] = payment_dict
                self._payment_by_order[payment.order_id] = payment.payment_id
                self._save_data()
                logger.debug(f"Payment saved to file: {payment.payment_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error saving payment: {e}")
            return False
    
    async def get_payment(self, payment_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID"""
        payment_dict = self._payments.get(payment_id)
        if payment_dict:
            # Преобразуем обратно в PaymentData (упрощенно)
            # В реальном приложении нужна полная десериализация
            return payment_dict
        return None
    
    async def get_payment_by_order_id(self, order_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID заказа"""
        payment_id = self._payment_by_order.get(order_id)
        if payment_id:
            return await self.get_payment(payment_id)
        return None
    
    async def update_payment_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Обновить статус платежа"""
        try:
            payment = self._payments.get(payment_id)
            if payment:
                payment['status'] = status.value
                if metadata:
                    payment['metadata'].update(metadata)
                self._save_data()
                logger.debug(f"Payment status updated: {payment_id} -> {status}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating payment status: {e}")
            return False
    
    async def save_refund(self, refund: RefundData) -> bool:
        """Сохранить возврат"""
        try:
            if refund.refund_id:
                refund_dict = {
                    'refund_id': refund.refund_id,
                    'payment_id': refund.payment_id,
                    'amount': str(refund.amount),
                    'currency': refund.currency.value,
                    'description': refund.description,
                    'status': refund.status.value if refund.status else None,
                    'created_at': refund.created_at.isoformat() if refund.created_at else None
                }
                
                self._refunds[refund.refund_id] = refund_dict
                self._save_data()
                logger.debug(f"Refund saved to file: {refund.refund_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error saving refund: {e}")
            return False
    
    async def get_refund(self, refund_id: str) -> Optional[RefundData]:
        """Получить возврат по ID"""
        return self._refunds.get(refund_id)
    
    async def get_payments_by_user(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[PaymentData]:
        """Получить платежи пользователя"""
        user_payments = [
            p for p in self._payments.values()
            if p.get('metadata', {}).get('user_id') == user_id
        ]
        
        user_payments.sort(
            key=lambda x: x.get('created_at', ''),
            reverse=True
        )
        
        return user_payments[offset:offset + limit]
