"""
Конфигурация для работы с YooKassa API
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from .exceptions import ConfigurationError


@dataclass
class YooKassaConfig:
    """
    Конфигурация YooKassa
    
    Attributes:
        shop_id: ID магазина (из личного кабинета YooKassa)
        secret_key: Секретный ключ (из личного кабинета YooKassa)
        return_url: URL для возврата пользователя после оплаты
        webhook_url: URL для получения webhook уведомлений
        is_test: Режим тестирования (True для тестовых платежей)
        timeout: Таймаут для API запросов (секунды)
        max_retries: Максимальное количество повторных попыток при ошибке
        
    Для ИП с 54-ФЗ:
        enable_receipts: Включить создание чеков (для 54-ФЗ)
        default_tax_system: Система налогообложения по умолчанию
        inn: ИНН организации/ИП
    """
    
    shop_id: str
    secret_key: str
    return_url: str
    webhook_url: Optional[str] = None
    is_test: bool = False
    timeout: int = 30
    max_retries: int = 3
    
    # Настройки для 54-ФЗ (чеки)
    enable_receipts: bool = True
    default_tax_system: int = 1  # 1 - УСН доход
    inn: Optional[str] = None
    
    # Дополнительные настройки
    auto_capture: bool = True  # Автоматическое подтверждение платежей
    idempotency_key_ttl: int = 3600  # TTL для idempotency keys (секунды)
    
    # Логирование
    enable_logging: bool = True
    log_level: str = "INFO"
    log_requests: bool = True  # Логировать запросы к API
    log_responses: bool = True  # Логировать ответы от API
    
    def __post_init__(self):
        """Валидация конфигурации после инициализации"""
        self.validate()
    
    def validate(self):
        """Валидация конфигурации"""
        if not self.shop_id:
            raise ConfigurationError("shop_id is required")
        
        if not self.secret_key:
            raise ConfigurationError("secret_key is required")
        
        if not self.return_url:
            raise ConfigurationError("return_url is required")
        
        # ИНН обязателен только если включены чеки
        if self.enable_receipts and not self.inn:
            raise ConfigurationError(
                "inn is required when enable_receipts=True. "
                "For testing without INN, set YOOKASSA_ENABLE_RECEIPTS=false in .env"
            )
        
        if self.timeout < 1:
            raise ConfigurationError("timeout must be >= 1")
        
        if self.max_retries < 0:
            raise ConfigurationError("max_retries must be >= 0")
    
    @classmethod
    def from_env(cls, prefix: str = "YOOKASSA_") -> "YooKassaConfig":
        """
        Создать конфигурацию из переменных окружения
        
        Args:
            prefix: Префикс для переменных окружения
            
        Returns:
            YooKassaConfig: Объект конфигурации
            
        Example:
            # В .env файле:
            YOOKASSA_SHOP_ID=123456
            YOOKASSA_SECRET_KEY=test_xxxxx
            YOOKASSA_RETURN_URL=https://example.com/payment/return
            
            # В коде:
            config = YooKassaConfig.from_env()
        """
        shop_id = os.getenv(f"{prefix}SHOP_ID", "")
        secret_key = os.getenv(f"{prefix}SECRET_KEY", "")
        return_url = os.getenv(f"{prefix}RETURN_URL", "")
        webhook_url = os.getenv(f"{prefix}WEBHOOK_URL")
        is_test = os.getenv(f"{prefix}IS_TEST", "false").lower() == "true"
        enable_receipts = os.getenv(f"{prefix}ENABLE_RECEIPTS", "true").lower() == "true"
        inn = os.getenv(f"{prefix}INN")
        auto_capture = os.getenv(f"{prefix}AUTO_CAPTURE", "true").lower() == "true"
        
        return cls(
            shop_id=shop_id,
            secret_key=secret_key,
            return_url=return_url,
            webhook_url=webhook_url,
            is_test=is_test,
            enable_receipts=enable_receipts,
            inn=inn,
            auto_capture=auto_capture
        )
    
    def to_dict(self) -> dict:
        """Конвертировать в словарь (для логирования, без секретных данных)"""
        return {
            "shop_id": self.shop_id,
            "return_url": self.return_url,
            "webhook_url": self.webhook_url,
            "is_test": self.is_test,
            "enable_receipts": self.enable_receipts,
            "auto_capture": self.auto_capture,
        }
