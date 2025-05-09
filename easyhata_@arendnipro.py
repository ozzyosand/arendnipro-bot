import requests
from bs4 import BeautifulSoup
import telebot
import os
from flask import Flask
from threading import Thread
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Настройка Flask для предотвращения засыпания
app = Flask('')

@app.route('/')
def home():
    logging.info("Received request to / endpoint")
    return "I'm alive"

def run():
    port = int(os.getenv("PORT", 8080))  # Динамический порт
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# Настройка Telegram-бота
bot = telebot.TeleBot(os.getenv("BOT_TOKEN"))

# Удаляем вебхук перед запуском polling
bot.delete_webhook()

# Функция для очистки и форматирования текста с сохранением структуры абзацев
def clean_and_format_description(text):
    if not text or not text.strip():
        return "Описание отсутствует"
    soup = BeautifulSoup(text, "html.parser")
    content = soup.get_text().strip()
    if not content:
        return "Описание отсутствует"
    if not soup.find('p'):
        sentences = content.split('. ')
        paragraphs = [s.strip() + '.' for s in sentences if s.strip()]
        return '\n\n'.join(paragraphs).replace('  ', ' ').replace(' ', ' ')
    paragraphs = []
    for p in soup.find_all('p'):
        content = p.get_text().strip()
        if content:
            paragraphs.append(content)
    return '\n\n'.join(paragraphs).replace('  ', ' ').replace(' ', ' ')

# Функция для обрезки текста с логическим завершением
def trim_description(description, max_length):
    if len(description) <= max_length:
        return description
    last_period = description.rfind('.', 0, max_length)
    if last_period != -1:
        return description[:last_period + 1]
    else:
        return description[:max_length].strip() + '.'

# Функция для извлечения данных из API с отладочным выводом
def get_data_from_api(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    }
    try:
        logging.info(f"Requesting URL: {url}")
        response = requests.get(url, headers=headers)
        logging.info(f"Response status: {response.status_code}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error: {str(e)}")
        return {"error": str(e)}

# Обработка входящих сообщений
@bot.message_handler(content_types=['text'])
def handle_message(message):
    if message.text.startswith("https://easyhata.site/flats/") or message.text.startswith("https://easyhata.site/houses/"):
        parts = message.text.split('/')
        logging.info(f"URL parts: {parts}")
        realty_type = parts[3]
        realty_id = parts[4]
        rieltor_index = parts.index("rieltor") if "rieltor" in parts else -1
        rieltor_id = parts[rieltor_index + 1].split('?')[0] if rieltor_index != -1 and rieltor_index + 1 < len(parts) else "11249"
        api_url = f"https://api.easybase.com.ua/v1/rieltors/{rieltor_id}/{realty_type}/{realty_id}/"
        logging.info(f"Extracted rieltor_id: {rieltor_id}, realty_type: {realty_type}, realty_id: {realty_id}, API URL: {api_url}")

        data = get_data_from_api(api_url)
        if "error" in data:
            bot.reply_to(message, f"Ошибка при запросе к API: {data['error']}")
            return

        description = clean_and_format_description(data.get("text", "Описание отсутствует"))
        logging.info(f"Formatted description: {description}")
        logging.info(f"Description length: {len(description)}")
        city = data.get("city", {}).get("name", "Город не найден")
        street = data.get("street", {}).get("name", "Улица не найдена")
        house_number = data.get("house_number", "") or ""
        address = f"{city}, вул. {street} {house_number}".strip()
        area = str(data.get("square_common", "Площадь не найдена"))
        current_floor = str(data.get("floor", "Этаж не найден"))
        total_floors = str(data.get("floors", "Этаж не найден"))
        price = str(data.get("price", "Цена не найдена"))
        currency = data.get("currency", "USD")
        contact_name = data.get("author_fname", "Имя не найден")
        contact_phone = data.get("phone", ["Телефон не найден"])[0]
        obj_id = str(data.get("id", "ID не найден"))
        images = [img["img_obj"] for img in data.get("images", [])[:10]]

        max_description_length = 780
        description = trim_description(description, max_description_length)

        if realty_type == "houses":
            floor_text = f"Этаж {total_floors}/{total_floors}\n"
        else:
            floor_text = f"Этаж {current_floor}/{total_floors}\n"

        post_text = (
            f"{description}\n\n"
            f"📍 {address}\n\n"
            f"ОП {area} м²\n"
            f"{floor_text}"
            f"Цена {price} {currency}\n\n"
            f"📱 {contact_name} {contact_phone}\n\n"
            f"📸 <a href='https://www.instagram.com/elenamelnik_rieltor'>Мой Instagram</a> | "
            f"💬 <a href='https://t.me/NYK_ELENA'>Написать мне в ЛС</a>\n\n"
            f"{obj_id}"
        )
        logging.info(f"Post text: {post_text}")
        logging.info(f"Post text length: {len(post_text)}")

        if images:
            try:
                media = [telebot.types.InputMediaPhoto(requests.get(img).content) for img in images]
                media[0].caption = post_text[:1024] if len(post_text) > 1024 else post_text
                media[0].parse_mode = 'HTML'
                bot.send_media_group(chat_id="@arendnipro", media=media)
            except Exception as e:
                logging.error(f"Error sending media group: {str(e)}")
                bot.send_message(chat_id="@arendnipro", text="Ошибка при отправке фото. " + post_text[:1024], parse_mode='HTML')
        else:
            bot.send_message(chat_id="@arendnipro", text=post_text[:1024], parse_mode='HTML')

        bot.reply_to(message, "Объявление опубликовано в канале!")
    else:
        bot.reply_to(message, "Пожалуйста, отправьте ссылку на объявление с easyhata.site (flats или houses)")

# Запускаем Flask-сервер и бота
keep_alive()
bot.infinity_polling(none_stop=True)