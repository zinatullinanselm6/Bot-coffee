import asyncio
import sqlite3
import os
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- НАСТРОЙКИ ---
TOKEN = os.environ.get("TOKEN")

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()
dp.include_router(router)

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            join_date DATE,
            order_count INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

init_db()

# --- FSM ---
class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_order_text = State()
    waiting_for_custom_time = State()

# --- КЛАВИАТУРЫ ---
def get_main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="☕️ Оформить заказ", callback_data="menu_order")],
        [InlineKeyboardButton(text="💬 Поддержка", callback_data="menu_support")]
    ])

def get_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад ↩️", callback_data="menu_back")]
    ])

def get_addresses_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ухтомская 1", callback_data="addr_Ухтомская 1")],
        [InlineKeyboardButton(text="Пушкина 2", callback_data="addr_Пушкина 2")],
        [InlineKeyboardButton(text="Правды 3", callback_data="addr_Правды 3")],
        [InlineKeyboardButton(text="Васильковая 4", callback_data="addr_Васильковая 4")],
        [InlineKeyboardButton(text="Назад ↩️", callback_data="menu_back")]
    ])

def get_time_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Через 5 минут", callback_data="time_5 мин")],
        [InlineKeyboardButton(text="Через 15 минут", callback_data="time_15 мин")],
        [InlineKeyboardButton(text="Через 30 минут", callback_data="time_30 мин")],
        [InlineKeyboardButton(text="Через час", callback_data="time_1 час")],
        [InlineKeyboardButton(text="Другое время ⏰", callback_data="time_custom")],
        [InlineKeyboardButton(text="Отмена ❌", callback_data="menu_back")]
    ])

# --- ТЕКСТЫ ---
MAIN_MENU_TEXT = (
    "👋 <b>Добро пожаловать в «Кофеманию»!</b>\n\n"
    "Этот бот создан для того, чтобы ваш кофе ждал вас горячим. ☕️\n\n"
    "<i>Выберите действие:</i>"
)

# --- ИСПРАВЛЕННАЯ ФУНКЦИЯ ЗАВЕРШЕНИЯ ЗАКАЗА ---
async def finish_order(event, state: FSMContext, time_val: str):
    data = await state.get_data()
    address = data.get("address")
    order_text = data.get("order_text")
    
    # БЕРЕМ ЮЗЕРА ПРАВИЛЬНО (из события, а не из сообщения бота)
    user = event.from_user
    username = f"@{user.username}" if user.username else "Скрыт"

    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET order_count = order_count + 1 WHERE user_id = ?', (user.id,))
    cursor.execute('SELECT user_id FROM admins')
    admins = cursor.fetchall()
    conn.commit()
    conn.close()

    admin_text = (
        "🔔 <b>НОВЫЙ ЗАКАЗ</b>\n\n"
        f"1. <b>Юзернейм:</b> {username}\n"
        f"2. <b>Адрес:</b> {address}\n"
        f"3. <b>Заказ:</b> {order_text}\n"
        f"4. <b>Время:</b> {time_val}"
    )

    for admin in admins:
        try:
            await bot.send_message(admin[0], admin_text)
        except:
            pass

    success_text = "✅ <b>Ваш заказ успешно отправлен!</b>\nБариста уже получил информацию."
    
    # ПРАВИЛЬНО РЕДАКТИРУЕМ СООБЩЕНИЕ
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(success_text, reply_markup=get_back_kb())
    else:
        await event.answer(success_text, reply_markup=get_back_kb())
    
    await state.clear()
    await state.update_data(main_msg_id=event.message.message_id if isinstance(event, CallbackQuery) else event.message_id)

# --- ОБРАБОТЧИКИ ---

@router.message(Command("admin170311"))
async def add_admin(message: Message):
    await message.delete()
    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (message.from_user.id,))
    conn.commit()
    conn.close()
    msg = await message.answer("✅ Вы назначены администратором.")
    await asyncio.sleep(3)
    await msg.delete()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await message.delete()
    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM users WHERE user_id = ?', (message.from_user.id,))
    user = cursor.fetchone()
    conn.close()

    if user:
        bot_msg = await message.answer(MAIN_MENU_TEXT, reply_markup=get_main_menu_kb())
        await state.update_data(main_msg_id=bot_msg.message_id)
    else:
        bot_msg = await message.answer("✨ Добро пожаловать! Как к вам обращаться?")
        await state.set_state(OrderState.waiting_for_name)
        await state.update_data(main_msg_id=bot_msg.message_id)

@router.message(OrderState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await message.delete()
    data = await state.get_data()
    msg_id = data.get("main_msg_id")
    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO users (user_id, username, name, join_date) VALUES (?, ?, ?, ?)',
                   (message.from_user.id, message.from_user.username or "none", message.text, datetime.now().date().isoformat()))
    conn.commit()
    conn.close()
    await state.clear()
    await bot.edit_message_text(MAIN_MENU_TEXT, chat_id=message.chat.id, message_id=msg_id, reply_markup=get_main_menu_kb())

@router.callback_query(F.data == "menu_back")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(MAIN_MENU_TEXT, reply_markup=get_main_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def show_profile(callback: CallbackQuery):
    conn = sqlite3.connect('coffeemania.db')
    cursor = conn.cursor()
    cursor.execute('SELECT username, name, join_date, order_count FROM users WHERE user_id = ?', (callback.from_user.id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        join_date = datetime.fromisoformat(user[2]).date()
        days = (datetime.now().date() - join_date).days
        days = 1 if days == 0 else days
        if user[3] <= 3: rank = "Новичок 🌱"
        elif user[3] <= 10: rank = "Умеющий ☕️"
        elif user[3] <= 25: rank = "Кофеман 🤎"
        else: rank = "Легенда кофемании 👑"
        text = f"👤 <b>Профиль:</b> {user[1]}\n🔗 Юзернейм: @{user[0]}\n🗓 Вы с нами: {days} дней\n📦 Заказов: {user[3]}\n🏆 Ранг: {rank}"
        await callback.message.edit_text(text, reply_markup=get_back_kb())
    await callback.answer()

@router.callback_query(F.data == "menu_order")
async def start_order(callback: CallbackQuery):
    await callback.message.edit_text("📍 Выберите адрес:", reply_markup=get_addresses_kb())
    await callback.answer()

@router.callback_query(F.data.startswith("addr_"))
async def process_address(callback: CallbackQuery, state: FSMContext):
    addr = callback.data.split("_")[1]
    await state.update_data(address=addr)
    await callback.message.edit_text(f"✅ Вы выбрали: {addr}\n✍️ Напишите, что заказать:", reply_markup=get_back_kb())
    await state.set_state(OrderState.waiting_for_order_text)
    await callback.answer()

@router.message(OrderState.waiting_for_order_text)
async def process_order_text(message: Message, state: FSMContext):
    await message.delete()
    await state.update_data(order_text=message.text)
    data = await state.get_data()
    main_msg_id = data.get("main_msg_id")
    try:
        await bot.edit_message_text("⏳ Когда забрать заказ?", chat_id=message.chat.id, message_id=main_msg_id, reply_markup=get_time_kb())
    except:
        new_msg = await message.answer("⏳ Когда забрать заказ?", reply_markup=get_time_kb())
        await state.update_data(main_msg_id=new_msg.message_id)
    await state.set_state(None)

@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    time_val = callback.data.split("_")[1]
    if time_val == "custom":
        await callback.message.edit_text("✍️ Напишите время в формате 12:34", reply_markup=get_back_kb())
        await state.set_state(OrderState.waiting_for_custom_time)
    else:
        # ПЕРЕДАЕМ САМ CALLBACK
        await finish_order(callback, state, time_val)
    await callback.answer()

@router.message(OrderState.waiting_for_custom_time)
async def process_custom_time(message: Message, state: FSMContext):
    await message.delete()
    # ПЕРЕДАЕМ САМО СООБЩЕНИЕ
    await finish_order(message, state, message.text)

@router.callback_query(F.data == "menu_support")
async def show_support(callback: CallbackQuery):
    await callback.message.edit_text("💬 Поддержка: @mirayy_code", reply_markup=get_back_kb())
    await callback.answer()

# --- ВЕБ-СЕРВЕР ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
