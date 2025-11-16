"""
Хранилище платежей на базе SQLite через существующую Database
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any

from .storage import PaymentStorage
from .models import PaymentData, RefundData
from .enums import PaymentStatus, Currency


logger = logging.getLogger(__name__)


class DatabasePaymentStorage(PaymentStorage):
    """
    SQLite хранилище для платежей через существующую базу данных
    """
    
    def __init__(self, db):
        """
        Args:
            db: Экземпляр Database из db/Database.py
        """
        self.db = db
        self._init_tables()
    
    def _init_tables(self):
        """Создание таблиц для хранения платежей и возвратов"""
        # Таблица платежей
        self.db.query("""
CREATE TABLE IF NOT EXISTS payments (
    payment_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    user_id TEXT,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    description TEXT,
    status TEXT,
    confirmation_url TEXT,
    created_at TEXT,
    updated_at TEXT,
    metadata TEXT,
    capture INTEGER DEFAULT 1,
    customer_email TEXT,
    customer_phone TEXT,
    customer_full_name TEXT
);
        """)
        
        # Таблица возвратов
        self.db.query("""
CREATE TABLE IF NOT EXISTS refunds (
    refund_id TEXT PRIMARY KEY,
    payment_id TEXT NOT NULL,
    amount TEXT NOT NULL,
    currency TEXT NOT NULL,
    description TEXT,
    status TEXT,
    created_at TEXT,
    FOREIGN KEY (payment_id) REFERENCES payments(payment_id)
);
        """)
        
        # Индекс для быстрого поиска по order_id
        self.db.query("""
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
        """)
        
        # Индекс для быстрого поиска по user_id
        self.db.query("""
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
        """)
        
        logger.info("Payment tables initialized")
    
    async def save_payment(self, payment: PaymentData) -> bool:
        """Сохранить платеж"""
        try:
            if not payment.payment_id:
                logger.error("Cannot save payment without payment_id")
                return False
            
            # Извлекаем user_id из metadata
            user_id = payment.metadata.get('user_id') if payment.metadata else None
            
            # Сериализуем metadata в JSON
            import json
            metadata_json = json.dumps(payment.metadata) if payment.metadata else None
            
            # Извлекаем данные customer
            customer_email = payment.customer.email if payment.customer else None
            customer_phone = payment.customer.phone if payment.customer else None
            customer_full_name = payment.customer.full_name if payment.customer else None
            
            self.db.query("""
INSERT OR REPLACE INTO payments 
(payment_id, order_id, user_id, amount, currency, description, status, 
 confirmation_url, created_at, updated_at, metadata, capture, customer_email, customer_phone, customer_full_name)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, values=(
                payment.payment_id,
                payment.order_id,
                user_id,
                str(payment.amount),
                payment.currency.value,
                payment.description,
                payment.status.value if payment.status else None,
                payment.confirmation_url,
                payment.created_at.isoformat() if payment.created_at else None,
                datetime.now().isoformat(),
                metadata_json,
                1 if payment.capture else 0,
                customer_email,
                customer_phone,
                customer_full_name
            ))
            
            logger.debug(f"Payment saved: {payment.payment_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving payment: {e}", exc_info=True)
            return False
    
    async def get_payment(self, payment_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID"""
        try:
            row = self.db.fetchone("""
SELECT payment_id, order_id, user_id, amount, currency, description, status,
       confirmation_url, created_at, metadata, capture, customer_email, customer_phone, customer_full_name
FROM payments WHERE payment_id = ?
            """, values=(payment_id,))
            
            if not row:
                return None
            
            return self._row_to_payment_data(row)
            
        except Exception as e:
            logger.error(f"Error getting payment: {e}", exc_info=True)
            return None
    
    async def get_payment_by_order_id(self, order_id: str) -> Optional[PaymentData]:
        """Получить платеж по ID заказа"""
        try:
            row = self.db.fetchone("""
SELECT payment_id, order_id, user_id, amount, currency, description, status,
       confirmation_url, created_at, metadata, capture, customer_email, customer_phone, customer_full_name
FROM payments WHERE order_id = ?
ORDER BY created_at DESC LIMIT 1
            """, values=(order_id,))
            
            if not row:
                return None
            
            return self._row_to_payment_data(row)
            
        except Exception as e:
            logger.error(f"Error getting payment by order_id: {e}", exc_info=True)
            return None
    
    async def update_payment_status(
        self,
        payment_id: str,
        status: PaymentStatus,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Обновить статус платежа"""
        try:
            # Получаем текущий платеж для обновления metadata
            current_payment = await self.get_payment(payment_id)
            if not current_payment:
                logger.warning(f"Payment not found for status update: {payment_id}")
                return False
            
            # Обновляем metadata если переданы
            import json
            if metadata:
                current_metadata = current_payment.metadata or {}
                current_metadata.update(metadata)
                metadata_json = json.dumps(current_metadata)
            else:
                metadata_json = json.dumps(current_payment.metadata) if current_payment.metadata else None
            
            self.db.query("""
UPDATE payments 
SET status = ?, updated_at = ?, metadata = ?
WHERE payment_id = ?
            """, values=(
                status.value,
                datetime.now().isoformat(),
                metadata_json,
                payment_id
            ))
            
            logger.debug(f"Payment status updated: {payment_id} -> {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating payment status: {e}", exc_info=True)
            return False
    
    async def save_refund(self, refund: RefundData) -> bool:
        """Сохранить возврат"""
        try:
            if not refund.refund_id:
                logger.error("Cannot save refund without refund_id")
                return False
            
            self.db.query("""
INSERT OR REPLACE INTO refunds
(refund_id, payment_id, amount, currency, description, status, created_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
            """, values=(
                refund.refund_id,
                refund.payment_id,
                str(refund.amount),
                refund.currency.value,
                refund.description,
                refund.status.value if refund.status else None,
                refund.created_at.isoformat() if refund.created_at else None
            ))
            
            logger.debug(f"Refund saved: {refund.refund_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving refund: {e}", exc_info=True)
            return False
    
    async def get_refund(self, refund_id: str) -> Optional[RefundData]:
        """Получить возврат по ID"""
        try:
            row = self.db.fetchone("""
SELECT refund_id, payment_id, amount, currency, description, status, created_at
FROM refunds WHERE refund_id = ?
            """, values=(refund_id,))
            
            if not row:
                return None
            
            return self._row_to_refund_data(row)
            
        except Exception as e:
            logger.error(f"Error getting refund: {e}", exc_info=True)
            return None
    
    async def get_payments_by_user(
        self,
        user_id: str,
        limit: int = 10,
        offset: int = 0
    ) -> List[PaymentData]:
        """Получить платежи пользователя"""
        try:
            rows = self.db.fetchall("""
SELECT payment_id, order_id, user_id, amount, currency, description, status,
       confirmation_url, created_at, metadata, capture, customer_email, customer_phone, customer_full_name
FROM payments 
WHERE user_id = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?
            """, values=(user_id, limit, offset))
            
            return [self._row_to_payment_data(row) for row in rows]
            
        except Exception as e:
            logger.error(f"Error getting payments by user: {e}", exc_info=True)
            return []
    
    def _row_to_payment_data(self, row) -> PaymentData:
        """Преобразование строки БД в PaymentData"""
        import json
        from .models import CustomerInfo
        
        metadata = None
        if row[9]:  # metadata column
            try:
                metadata = json.loads(row[9])
            except:
                pass
        
        # Создаём CustomerInfo из сохранённых данных
        customer = CustomerInfo(
            email=row[11] if len(row) > 11 else None,
            phone=row[12] if len(row) > 12 else None,
            full_name=row[13] if len(row) > 13 else None
        )
        
        return PaymentData(
            payment_id=row[0],
            order_id=row[1],
            amount=Decimal(row[3]),
            currency=Currency(row[4]),
            description=row[5],
            status=PaymentStatus(row[6]) if row[6] else None,
            confirmation_url=row[7],
            created_at=datetime.fromisoformat(row[8]) if row[8] else None,
            metadata=metadata,
            capture=bool(row[10]) if row[10] is not None else True,
            customer=customer
        )
    
    def _row_to_refund_data(self, row) -> RefundData:
        """Преобразование строки БД в RefundData"""
        return RefundData(
            refund_id=row[0],
            payment_id=row[1],
            amount=Decimal(row[2]),
            currency=Currency(row[3]),
            description=row[4],
            status=PaymentStatus(row[5]) if row[5] else None,
            created_at=datetime.fromisoformat(row[6]) if row[6] else None
        )
