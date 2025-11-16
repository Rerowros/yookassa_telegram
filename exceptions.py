"""
Кастомные исключения для работы с платежами YooKassa
"""


class PaymentError(Exception):
    """Базовое исключение для всех ошибок платежей"""
    
    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)
    
    def __str__(self):
        if self.original_error:
            return f"{self.message}. Original error: {str(self.original_error)}"
        return self.message


class PaymentCreationError(PaymentError):
    """Ошибка при создании платежа"""
    pass


class PaymentNotFoundError(PaymentError):
    """Платеж не найден"""
    pass


class PaymentCaptureError(PaymentError):
    """Ошибка при подтверждении платежа"""
    pass


class PaymentCancelError(PaymentError):
    """Ошибка при отмене платежа"""
    pass


class RefundError(PaymentError):
    """Ошибка при создании возврата"""
    pass


class RefundNotFoundError(RefundError):
    """Возврат не найден"""
    pass


class ReceiptError(PaymentError):
    """Ошибка при работе с чеками"""
    pass


class WebhookError(PaymentError):
    """Ошибка при обработке webhook"""
    pass


class ValidationError(PaymentError):
    """Ошибка валидации данных"""
    pass


class ConfigurationError(PaymentError):
    """Ошибка конфигурации"""
    pass


class NetworkError(PaymentError):
    """Сетевая ошибка при запросе к API"""
    pass


class AuthenticationError(PaymentError):
    """Ошибка аутентификации"""
    pass
