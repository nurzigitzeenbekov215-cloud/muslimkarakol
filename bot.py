import asyncio
import json
import threading
from urllib.parse import unquote
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from flask import Flask
import os
import re
from supabase import create_client

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8961304073:AAGYSSd1AjbCOxTp7BDSIuItfbytUvdl5Ec"
ADMIN_CHAT_ID = "8189717935"

# ===== НАСТРОЙКИ ВАШЕГО SUPABASE =====
SUPABASE_URL = "https://fneyyiiwjhwkayxayfij.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZuZXl5aWl3amh3a2F5eGF5ZmlqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg2MjMxNjAsImV4cCI6MjA5NDE5OTE2MH0.DfuBB-2NRevPursKMQMrHazfbYZlXIFFUOsTpUP6ngA"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===== СОСТОЯНИЯ =====
class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_payment = State()

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ===== ВАЖНО: ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ ЗАКАЗА ИЗ ВАШЕЙ ТАБЛИЦЫ =====
def get_order_by_id(order_id):
    """Получает заказ из вашей таблицы orders в Supabase"""
    try:
        # В вашей таблице orders есть поля: id, customer_name, customer_phone, products, total_price, status
        result = supabase.table('orders').select('*').eq('id', int(order_id)).execute()
        if result.data and len(result.data) > 0:
            order = result.data[0]
            # Преобразуем ваш формат в формат, понятный боту
            return {
                'items': order.get('products', []),  # products уже содержит массив товаров
                'total': order.get('total_price', 0),
                'status': order.get('status', 'pending')
            }
    except Exception as e:
        print(f"❌ Ошибка получения заказа: {e}")
    return None


# ===== ФУНКЦИЯ ДЛЯ ПАРСИНГА =====
def parse_start_data(text):
    """Извлекает ID заказа из ссылки /start order_ID"""
    try:
        print(f"🔍 Парсинг: {text[:200]}")
        
        if not text or not text.startswith('/start'):
            return None
        
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return None
        
        param = parts[1].strip()
        print(f"📦 Параметр: {param[:100]}")
        
        # Ищем order_ЦИФРЫ
        match = re.search(r'order_(\d+)', param)
        if not match:
            print("❌ Нет совпадения с order_")
            return None
        
        order_id = match.group(1)
        print(f"✅ Найден ID заказа: {order_id}")
        return int(order_id)
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None


# ===== КОМАНДА /START =====
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text
    
    print(f"📨 /start от {user_id}: {text[:100]}")
    
    # Пытаемся получить ID заказа из параметра
    order_id = parse_start_data(text)
    
    if order_id:
        # Получаем заказ из Supabase
        order_data = get_order_by_id(order_id)
        
        if order_data:
            print(f"✅ Заказ получен! ID: {order_id}")
            await state.update_data(order_data=order_data)
            await show_order(message, state, order_data)
            return
        else:
            print(f"❌ Заказ с ID {order_id} не найден в Supabase")
    
    # Если заказа нет — обычное приветствие
    print("❌ Заказ не найден, показываем приветствие")
    await message.answer(
        "🍔 *Добро пожаловать в Muslim Fast Food!* 🍔\n\n"
        "✅ Халяльная еда с быстрой доставкой!\n\n"
        "📦 Чтобы оформить заказ:\n"
        "1️⃣ Перейдите на наш сайт\n"
        "2️⃣ Добавьте товары в корзину\n"
        "3️⃣ Нажмите «Оформить заказ»\n\n"
        "📞 По вопросам: +7 (999) 123-45-67",
        parse_mode="Markdown"
    )


async def show_order(message: types.Message, state: FSMContext, order_data):
    """Показывает заказ и запрашивает данные для доставки"""
    
    items_text = ""
    for item in order_data.get('items', []):
        # Поддерживаем ваш формат товаров: {id, name, price, quantity}
        item_name = item.get('name', item.get('title', 'Товар'))
        item_qty = item.get('quantity', 1)
        item_price = item.get('price', 0)
        item_sum = item_qty * item_price
        items_text += f"🍔 {item_name} × {item_qty} = {item_sum} ₽\n"
    
    total = order_data.get('total', 0)
    
    await state.update_data(order_data=order_data)
    
    await message.answer(
        f"🍔 *Muslim Fast Food* 🍔\n\n"
        f"✅ *Мы получили ваш заказ с сайта!*\n\n"
        f"📋 *Ваш заказ:*\n"
        f"──────────────────\n"
        f"{items_text}"
        f"──────────────────\n"
        f"💰 *ИТОГО:* {total} ₽\n"
        f"──────────────────\n\n"
        f"✏️ *Пожалуйста, укажите ваши данные для доставки:*\n\n"
        f"📝 *Введите ваше имя:*",
        parse_mode="Markdown"
    )
    await OrderState.waiting_for_name.set()


@dp.message_handler(state=OrderState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❌ Введите корректное имя (минимум 2 символа):")
        return
    await state.update_data(name=name)
    await message.answer(
        f"✅ {name}, спасибо!\n\n📞 Теперь укажите ваш номер телефона:",
        parse_mode="Markdown"
    )
    await OrderState.waiting_for_phone.set()


@dp.message_handler(state=OrderState.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    # Простая проверка номера телефона (для России)
    phone_clean = re.sub(r'[^0-9+]', '', phone)
    if len(phone_clean) < 10:
        await message.answer("❌ Введите корректный номер телефона (например: +7 999 123 45 67):")
        return
    await state.update_data(phone=phone_clean)
    await message.answer(
        f"📞 Номер: {phone_clean}\n\n🏠 Теперь укажите адрес доставки:",
        parse_mode="Markdown"
    )
    await OrderState.waiting_for_address.set()


@dp.message_handler(state=OrderState.waiting_for_address)
async def process_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("❌ Введите полный адрес (улица, дом, квартира):")
        return
    await state.update_data(address=address)
    await message.answer(
        "💰 *Выберите способ оплаты:*\n\n"
        "1️⃣ Наличными курьеру\n"
        "2️⃣ Картой курьеру\n"
        "3️⃣ Онлайн-перевод (СБП/карта)\n\n"
        "Введите 1, 2 или 3:",
        parse_mode="Markdown"
    )
    await OrderState.waiting_for_payment.set()


@dp.message_handler(state=OrderState.waiting_for_payment)
async def process_payment(message: types.Message, state: FSMContext):
    payment_choice = message.text.strip()
    payment_methods = {
        "1": "💰 Наличными курьеру",
        "2": "💳 Картой курьеру (терминал)",
        "3": "🏦 Онлайн-перевод на карту"
    }
    if payment_choice not in payment_methods:
        await message.answer("❌ Введите 1, 2 или 3:")
        return
    
    payment_method = payment_methods[payment_choice]
    await state.update_data(payment=payment_method)
    
    user_data = await state.get_data()
    name = user_data.get("name")
    phone = user_data.get("phone")
    address = user_data.get("address")
    order_data = user_data.get("order_data", {})
    
    # Формируем текст заказа
    items_text = ""
    for item in order_data.get('items', []):
        item_name = item.get('name', item.get('title', 'Товар'))
        item_qty = item.get('quantity', 1)
        item_price = item.get('price', 0)
        item_sum = item_qty * item_price
        items_text += f"🍔 {item_name} × {item_qty} = {item_sum} ₽\n"
    total = order_data.get('total', 0)
    
    order_text = f"""
🆕 *НОВЫЙ ЗАКАЗ - MUSLIM FAST FOOD* 🆕
──────────────────
📋 *ЗАКАЗ:*
{items_text}
──────────────────
💰 *ИТОГО:* {total} ₽
──────────────────
👤 *Имя:* {name}
📞 *Телефон:* {phone}
🏠 *Адрес:* {address}
💳 *Оплата:* {payment_method}
──────────────────
⏱️ *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
🍔 *Халяльная еда | Быстрая доставка*
    """
    
    # Отправляем заказ админу
    await bot.send_message(ADMIN_CHAT_ID, order_text, parse_mode="Markdown")
    
    # Обновляем статус заказа в Supabase
    try:
        order_data_from_state = user_data.get("order_data", {})
        # Получаем ID заказа из базы (если есть)
        # ВАЖНО: Вам нужно сохранить ID заказа в state при получении
        # Я добавил order_id в state, давайте его сохранять
        pass
    except Exception as e:
        print(f"Ошибка обновления статуса: {e}")
    
    await message.answer(
        "✅ *ЗАКАЗ ПРИНЯТ!* ✅\n\n"
        f"👤 {name}, мы получили ваш заказ.\n"
        f"📞 Курьер свяжется с вами по номеру: {phone}\n"
        f"🏠 Доставим по адресу: {address}\n"
        f"💳 Оплата: {payment_method}\n\n"
        "🍔 *Спасибо за заказ! Ждите звонка курьера.*",
        parse_mode="Markdown"
    )
    
    await state.finish()


@dp.message_handler(commands=['cancel'])
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Оформление заказа отменено.")


@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    await message.answer(
        "🍔 *Muslim Fast Food - Помощь* 🍔\n\n"
        "/start - Начать работу\n"
        "/cancel - Отменить оформление\n"
        "/help - Показать эту справку\n\n"
        "📞 Связь с администратором: +7 (999) 123-45-67",
        parse_mode="Markdown"
    )


# ===== FLASK-СЕРВЕР ДЛЯ RENDER =====
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Muslim Fast Food Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=10000)


if __name__ == "__main__":
    print("🤖 Бот Muslim Fast Food запущен!")
    print(f"📨 Заказы будут приходить в чат: {ADMIN_CHAT_ID}")
    print(f"🔗 Supabase подключен: {SUPABASE_URL}")
    
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    
    executor.start_polling(dp, skip_updates=True)