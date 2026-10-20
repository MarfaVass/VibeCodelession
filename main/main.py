def check_product_card(title, price, description):
    """Проверяет обязательные поля карточки товара."""
    errors = []

    if not title.strip():
        errors.append("Не указано название товара")

    if price <= 0:
        errors.append("Цена должна быть больше нуля")

    if not description.strip():
        errors.append("Не заполнено описание товара")

    return errors


if __name__ == "__main__":
    title = "Разделочная доска ComposeEat"
    price = 2490
    description = "Двусторонняя разделочная доска для кухни"

    errors = check_product_card(title, price, description)

    if errors:
        print("Обнаружены ошибки:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Карточка товара заполнена корректно.")
