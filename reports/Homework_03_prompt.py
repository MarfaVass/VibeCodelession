import re
from collections import Counter


def analyze_text(text: str) -> dict:
    # Приводим текст к нижнему регистру,
    # чтобы не учитывать различия между заглавными и строчными буквами.
    text = text.lower()

    # Находим слова на русском и английском языках.
    # Буквы и цифры не смешиваем: учитываем только последовательности букв.
    words = re.findall(r"[a-zа-яё]+", text)

    # Считаем количество предложений по знакам . ! ?
    # Несколько знаков подряд считаются одним разделителем предложений.
    sentences = re.findall(r"[.!?]+", text)

    # Если слов нет, возвращаем нулевые значения.
    if not words:
        return {
            "word_count": 0,
            "unique_words": 0,
            "top_3_words": [],
            "avg_word_length": 0,
            "sentence_count": 0,
        }

    # Подсчитываем частоту каждого слова.
    word_frequencies = Counter(words)

    # Выбираем три самых частых слова.
    # При одинаковой частоте сохраняется порядок первого появления.
    top_3_words = word_frequencies.most_common(3)

    # Рассчитываем среднюю длину слова.
    avg_word_length = round(sum(len(word) for word in words) / len(words), 2)

    # Формируем и возвращаем результат.
    return {
        "word_count": len(words),
        "unique_words": len(word_frequencies),
        "top_3_words": top_3_words,
        "avg_word_length": avg_word_length,
        "sentence_count": len(sentences),
    }


# Тест 1. Обычный текст
result = analyze_text("Привет, мир! Привет, Python. Как дела?")
assert result == {
    "word_count": 6,
    "unique_words": 5,
    "top_3_words": [("привет", 2), ("мир", 1), ("python", 1)],
    "avg_word_length": 4.67,
    "sentence_count": 3,
}
print("Тест 1 пройден:", result)


# Тест 2. Пустая строка
result = analyze_text("")
assert result == {
    "word_count": 0,
    "unique_words": 0,
    "top_3_words": [],
    "avg_word_length": 0,
    "sentence_count": 0,
}
print("Тест 2 пройден:", result)


# Тест 3. Строка только из пробелов
result = analyze_text("     ")
assert result == {
    "word_count": 0,
    "unique_words": 0,
    "top_3_words": [],
    "avg_word_length": 0,
    "sentence_count": 0,
}
print("Тест 3 пройден:", result)


# Тест 4. Текст только с пунктуацией
result = analyze_text("... !!! ???")
assert result == {
    "word_count": 0,
    "unique_words": 0,
    "top_3_words": [],
    "avg_word_length": 0,
    "sentence_count": 0,
}
print("Тест 4 пройден:", result)

print("\nВсе тесты успешно пройдены!")

# Ввод произвольного текста пользователем
print("\n=== Анализ собственного текста ===")
user_text = input("Введите текст для анализа: ")

# Вызываем функцию и выводим результат
result = analyze_text(user_text)

print("\nРезультат анализа:")
print("Количество слов:", result["word_count"])
print("Уникальных слов:", result["unique_words"])
print("Топ-3 слов:", result["top_3_words"])
print("Средняя длина слова:", result["avg_word_length"])
print("Количество предложений:", result["sentence_count"])

text = "из-за дождя мы опоздали. hello-world тоже"
print("С точкой:   ", analyze_text(text))
print("Без точки:  ", analyze_text(text.replace(".", "")))

print("Привет!!! ->", analyze_text("Привет!!!")["sentence_count"])
print("Привет... мир ->", analyze_text("Привет... мир")["sentence_count"])

print(analyze_text("Привет")["sentence_count"])  # ожидаем: 1 (по-хорошему)
print(analyze_text("Привет!")["sentence_count"])  # ожидаем: 1
print(analyze_text("Привет! Мир?")["sentence_count"])  # ожидаем: 2

print("=== ЛОВУШКА 6: None и не-строки ===")
for bad in [None, 123, 3.14, ["привет", "мир"], {"a": 1}, True]:
    try:
        result = analyze_text(bad)
        print(f"{bad!r:20} -> OK: {result}")
    except Exception as e:
        print(f"{bad!r:20} -> {type(e).__name__}: {e}")
