import requests

url = "https://dummyjson.com/products/1"

response = requests.get(url, timeout=15)

print("Статус ответа:", response.status_code)

if response.status_code == 200:
    product = response.json()

    print("Название товара:", product["title"])
    print("Цена:", product["price"])
    print("Описание:", product["description"])
else:
    print("Не удалось получить данные о товаре.")


