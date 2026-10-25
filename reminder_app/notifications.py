from plyer import notification


def send_notification(title, message, timeout=10):
    """Показывает системное уведомление."""
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Напоминалка",
            timeout=timeout,
        )
        return True
    except Exception as error:
        print(f"Не удалось показать уведомление: {error}")
        return False


def test_notification():
    """Отправляет тестовое уведомление."""
    return send_notification(
        title="Проверка напоминалки",
        message="Системные уведомления работают!",
    )
