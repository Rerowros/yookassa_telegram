"""
Вспомогательные функции
"""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict


def generate_idempotency_key(order_id: str, timestamp: datetime | None = None) -> str:
    """
    Генерация ключа идемпотентности
    
    Ключ идемпотентности используется для защиты от дублирования платежей.
    Если запрос с таким же ключом будет отправлен повторно, YooKassa вернет
    результат первого запроса.
    
    Args:
        order_id: ID заказа
        timestamp: Временная метка (опционально)
        
    Returns:
        str: Ключ идемпотентности
    """
    if timestamp is None:
        timestamp = datetime.now()
    
    # Создаем уникальный ключ на основе order_id и timestamp
    data = f"{order_id}_{timestamp.isoformat()}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


def generate_order_id(prefix: str = "order") -> str:
    """
    Генерация уникального ID заказа
    
    Args:
        prefix: Префикс для ID
        
    Returns:
        str: Уникальный ID заказа
    """
    unique_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{prefix}_{timestamp}_{unique_id}"


def generate_secret_token(length: int = 32) -> str:
    """
    Генерация секретного токена для webhook
    
    Args:
        length: Длина токена
        
    Returns:
        str: Секретный токен
    """
    return secrets.token_urlsafe(length)


def format_amount(amount: float | int | str) -> str:
    """
    Форматирование суммы для API YooKassa
    
    Args:
        amount: Сумма
        
    Returns:
        str: Отформатированная сумма (XX.XX)
    """
    from decimal import Decimal
    return f"{Decimal(str(amount)):.2f}"


def parse_phone(phone: str) -> str:
    """
    Парсинг и нормализация телефона
    
    Args:
        phone: Телефон в любом формате
        
    Returns:
        str: Телефон в формате 79XXXXXXXXX
    """
    # Удаляем все символы кроме цифр
    clean = ''.join(filter(str.isdigit, phone))
    
    # Если начинается с 8, меняем на 7
    if clean.startswith('8'):
        clean = '7' + clean[1:]
    
    # Если не начинается с 7, добавляем 7
    if not clean.startswith('7'):
        clean = '7' + clean
    
    return clean


def mask_sensitive_data(data: Dict[str, Any], fields: list[str] = None) -> Dict[str, Any]:
    """
    Маскирование чувствительных данных для логирования
    
    Args:
        data: Данные
        fields: Список полей для маскирования
        
    Returns:
        Dict: Данные с замаскированными полями
    """
    if fields is None:
        fields = ['secret_key', 'password', 'token', 'card_number', 'cvv']
    
    result = data.copy()
    
    for key, value in result.items():
        if key in fields:
            result[key] = "***MASKED***"
        elif isinstance(value, dict):
            result[key] = mask_sensitive_data(value, fields)
        elif isinstance(value, list):
            result[key] = [
                mask_sensitive_data(item, fields) if isinstance(item, dict) else item
                for item in value
            ]
    
    return result


def validate_webhook_signature(payload: str, signature: str, secret: str) -> bool:
    """
    Проверка подписи webhook
    
    Args:
        payload: Тело запроса
        signature: Подпись из заголовка
        secret: Секретный ключ
        
    Returns:
        bool: Валидна ли подпись
    """
    expected_signature = hashlib.sha256(
        (payload + secret).encode()
    ).hexdigest()
    
    return secrets.compare_digest(signature, expected_signature)


def calculate_timeout_with_jitter(base_timeout: int, attempt: int, max_jitter: float = 0.1) -> float:
    """
    Расчет таймаута с jitter для retry логики
    
    Args:
        base_timeout: Базовый таймаут
        attempt: Номер попытки
        max_jitter: Максимальный jitter (доля от базового таймаута)
        
    Returns:
        float: Таймаут с jitter
    """
    import random
    
    # Экспоненциальная задержка
    timeout = base_timeout * (2 ** attempt)
    
    # Добавляем jitter
    jitter = random.uniform(0, max_jitter * timeout)
    
    return timeout + jitter


def truncate_string(text: str, max_length: int = 128) -> str:
    """
    Обрезка строки до максимальной длины
    
    Args:
        text: Строка
        max_length: Максимальная длина
        
    Returns:
        str: Обрезанная строка
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def safe_get(data: Dict[str, Any], *keys, default=None) -> Any:
    """
    Безопасное получение вложенного значения из словаря
    
    Args:
        data: Словарь
        *keys: Ключи для навигации
        default: Значение по умолчанию
        
    Returns:
        Any: Значение или default
        
    Example:
        safe_get({"a": {"b": {"c": 1}}}, "a", "b", "c")  # 1
        safe_get({"a": {"b": {}}}, "a", "b", "c", default=0)  # 0
    """
    result = data
    for key in keys:
        if isinstance(result, dict):
            result = result.get(key)
        else:
            return default
        
        if result is None:
            return default
    
    return result
