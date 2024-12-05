from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
import logging
from datetime import datetime, time, timezone, timedelta
from aiogram import F
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ContentType, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# Настройка
API_TOKEN = '8079401890:AAEViDARVCq3TpDi1RWAYB6KwfJsuKf_mAg'  # Замените на токен вашего бота
ADMIN_CHAT_ID = -1002486131912  
ADMIN_IDS = [605530472, 296187600]

EKAT_TZ = timezone(timedelta(hours=5))  # Екатеринбургское время (UTC+5)
WORKING_HOURS = (time(8, 0), time(20, 0))  # С 8:00 до 20:00

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Состояния
class UserStates(StatesGroup):
    waiting_for_problem = State()
    waiting_for_confirm = State()
    contacting_admin = State()

class AdminStates(StatesGroup):
    waiting_for_reply = State()
    contacting_user = State()

# Хранилище заявок
user_requests = {}
admin_responses = {}
request_counter = 0

# Проверка рабочего времени
def is_within_working_hours():
    current_time = datetime.now(EKAT_TZ).time()
    return WORKING_HOURS[0] <= current_time <= WORKING_HOURS[1]

# Генерация уникального номера заявки
def generate_request_id():
    global request_counter
    request_counter += 1
    date_part = datetime.now(EKAT_TZ).strftime("%Y%m%d")
    return f"{date_part}-{request_counter:05d}"

# Главное меню (клавиатура пользователя)
def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Заявка 📝"), KeyboardButton(text="Мои заявки 📌")],
            [KeyboardButton(text="Связь с админом 📤"), KeyboardButton(text="Функционал ⚙️")]
        ],
        resize_keyboard=True
    )
    return keyboard


# Команда /start
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    logging.info(f"Пользователь {message.from_user.id} начал диалог.")
    await state.clear()
    await message.answer(
        'Привет! ИТ-отдел работает с 8:00 до 20:00 по Екатеринбургскому времени.\n'
        'Для взаимодействия с ботом используйте кнопки ниже, для начала прошу ознакомится с кнопкой "Функционал".',
        reply_markup=main_menu()
    )

# Команда /task
@dp.message(Command("task"))
async def admin_task_list(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("У вас нет доступа к этой команде.")
        return

    active_tasks = []
    completed_tasks = []

    for req_id, req_data in user_requests.items():
        admin_info = req_data.get("admin", {})
        admin_name = admin_info.get("name", "Не назначен")
        task_info = (
            f"Заявка {req_id}\n"
            f"Проблема: {req_data['problem']}\n"
            f"Дата: {req_data['time']}\n"
            f"Администратор: {admin_name}\n"
        )

        if req_data["status"] == "Выполнено":
            completed_tasks.append(task_info)
        else:
            active_tasks.append(task_info)

    response = "Список задач:\n\n"
    if active_tasks:
        response += "🔹 **Активные задачи:**\n\n" + "\n".join(active_tasks) + "\n\n"
    else:
        response += "🔹 **Активные задачи:**\nНет активных задач.\n\n"

    if completed_tasks:
        response += "✅ **Выполненные задачи:**\n\n" + "\n".join(completed_tasks) + "\n\n"
    else:
        response += "✅ **Выполненные задачи:**\nНет выполненных задач.\n\n"

    await message.answer(response, parse_mode="Markdown")


# Кнопка "Заявка"
@dp.message(lambda message: message.text == "Заявка 📝")
async def create_request(message: types.Message, state: FSMContext):
    if not is_within_working_hours():
        await message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return
    await state.set_state(UserStates.waiting_for_problem)
    await message.answer(
        'Для более быстрой и корректной работы ИТ-специалистов просим составлять заявку примерно так:\n'
        'Иван, Пермь, 8912-345-67-89 - телефон для связи или 151 - внутренний. Столкнулся с проблемой на компьютере PERM-MGR-1, не хочет печатать документ.'
    )

# Обработка описания проблемы
@dp.message(UserStates.waiting_for_problem)
async def handle_problem_description(message: types.Message, state: FSMContext):
    if not is_within_working_hours():
        await message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return
    problem_text = message.text
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    request_id = generate_request_id()
    current_time = datetime.now(EKAT_TZ).strftime("%Y-%m-%d %H:%M:%S")

    # Сохраняем заявку
    user_requests[request_id] = {
        "user_id": user_id,
        "user_name": user_name,
        "problem": problem_text,
        "status": "Ожидание подтверждения",
        "time": current_time
    }

    # Логируем заявку
    logging.info(
        f"Создана заявка: {request_id}\n"
        f"Пользователь: {user_name} (ID: {user_id})\n"
        f"Дата: {current_time}\n"
        f"Проблема: {problem_text}"
    )

    # Подтверждение заявки
    confirm_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, все верно", callback_data=f"confirm_request_{request_id}")],
            [InlineKeyboardButton(text="Нет", callback_data=f"cancel_request_{request_id}")]
        ]
    )

    await state.set_state(UserStates.waiting_for_confirm)
    await message.answer(
        f"Заявка сформирована:\n\n"
        f"Имя: {user_name}\n"
        f"ID: {user_id}\n"
        f"Дата: {current_time}\n"
        f"Проблема: {problem_text}\n"
        f"Номер заявки: {request_id}",
        reply_markup=confirm_keyboard
    )

# Подтверждение заявки
@dp.callback_query(lambda callback: callback.data.startswith("confirm_request_"))
async def confirm_request(callback: types.CallbackQuery, state: FSMContext):
    if not is_within_working_hours():
        await callback.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return
    request_id = callback.data.split("_")[2]
    if request_id not in user_requests:
        await callback.answer("Заявка уже удалена.", show_alert=True)
        return

    user_requests[request_id]["status"] = "В работе"

    # Отправка в чат администраторов
    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Взять в работу", callback_data=f"take_request_{request_id}")]
        ]
    )

    await bot.send_message(
        ADMIN_CHAT_ID,
        f"Новая заявка:\n\n"
        f"Имя: {user_requests[request_id]['user_name']}\n"
        f"ID: {user_requests[request_id]['user_id']}\n"
        f"Проблема: {user_requests[request_id]['problem']}\n"
        f"Номер заявки: {request_id}",
        reply_markup=admin_keyboard
    )

    await callback.message.answer("Заявка отправлена в ИТ-отдел.", reply_markup=main_menu())
    await state.clear()

# Отмена заявки
@dp.callback_query(lambda callback: callback.data.startswith("cancel_request_"))
async def cancel_request(callback: types.CallbackQuery, state: FSMContext):
    if not is_within_working_hours():
        await callback.message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return    
    request_id = callback.data.split("_")[2]
    if request_id in user_requests:
        del user_requests[request_id]
    await callback.message.answer("Заявка отменена.", reply_markup=main_menu())
    await state.clear()

# Обработка кнопки "Взять в работу"
@dp.callback_query(lambda callback: callback.data.startswith("take_request_"))
async def take_request(callback: types.CallbackQuery):
    request_id = callback.data.split("_")[2]
    admin_id = callback.from_user.id
    admin_name = callback.from_user.username or callback.from_user.full_name

    if request_id in user_requests:
        user_requests[request_id]["status"] = "В работе"
        user_requests[request_id]["admin"] = {"id": admin_id, "name": admin_name}

        admin_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Выполнено", callback_data=f"complete_request_{request_id}")],
                [InlineKeyboardButton(text="Связь с пользователем", callback_data=f"contact_user_{request_id}")]
            ]
        )

        await callback.message.answer(
            f"Заявка {request_id} взята в работу администратором {admin_name}.",
            reply_markup=admin_keyboard
        )

        # Уведомление пользователя
        await bot.send_message(
            user_requests[request_id]["user_id"],
            f"Ваша заявка {request_id} взята в работу администратором."
        )
    else:
        await callback.answer("Заявка уже удалена.", show_alert=True)


# Обработка кнопки "Выполнено"
@dp.callback_query(lambda callback: callback.data.startswith("complete_request_"))
async def complete_request(callback: types.CallbackQuery):
    request_id = callback.data.split("_")[2]
    if request_id in user_requests:
        user_requests[request_id]["status"] = "Выполнено"
        await callback.message.answer(f"Заявка {request_id} выполнена.")
        await bot.send_message(user_requests[request_id]["user_id"], f"Ваша заявка {request_id} выполнена.")
    else:
        await callback.answer("Заявка уже удалена.", show_alert=True)

# Обработка кнопки "Связь с пользователем"
@dp.callback_query(lambda callback: callback.data.startswith("contact_user_"))
async def contact_user(callback: types.CallbackQuery, state: FSMContext):
    request_id = callback.data.split("_")[2]
    if request_id in user_requests:
        user_id = user_requests[request_id]["user_id"]
        await state.set_state(AdminStates.contacting_user)
        await state.update_data(request_id=request_id, user_id=user_id)
        await callback.message.answer("Напишите сообщение пользователю.")
    else:
        await callback.answer("Заявка уже удалена.", show_alert=True)

# Отправка сообщения пользователю от администратора
@dp.message(StateFilter(AdminStates.contacting_user))
async def send_message_to_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    text = message.text

    await bot.send_message(user_id, f"Сообщение от администратора:\n{text}")
    await message.answer("Ваше сообщение отправлено пользователю.")
    await state.clear()

# Кнопка "Мои заявки"
@dp.message(lambda message: message.text == "Мои заявки 📌")
async def my_requests(message: types.Message):
    if not is_within_working_hours():
        await message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return
    user_id = message.from_user.id
    requests = [
        f"Заявка {req_id} - {req_data['status']}\nПроблема: {req_data['problem']}"
        for req_id, req_data in user_requests.items()
        if req_data["user_id"] == user_id
    ]
    if requests:
        await message.answer("\n\n".join(requests), reply_markup=main_menu())
    else:
        await message.answer("У вас нет активных заявок.", reply_markup=main_menu())

# Кнопка "Связь с админом"
@dp.message(lambda message: message.text == "Связь с админом 📤")
async def contact_admin(message: types.Message, state: FSMContext):
    if not is_within_working_hours():
        await message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно с вами свяжемся в рабочее время.")
        return
    await state.set_state(UserStates.contacting_admin)
    await message.answer("Напишите сообщение администратору, также вы можете добавить фото или видео.")

# Функция отправки сообщения администратору
@dp.message(StateFilter(UserStates.contacting_admin))
async def send_to_admin(message: types.Message, state: FSMContext):
    # Проверка рабочего времени
    if not is_within_working_hours():
        await message.answer("К сожалению, в данный момент мы не можем вам ответить. Мы обязательно свяжемся с вами в рабочее время.")
        return

    # Данные пользователя
    user_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    user_id = message.from_user.id
    user_text = message.text

    # Создание клавиатуры для ответа администратором
    reply_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Ответить", callback_data=f"reply_to_{user_id}")]]
    )

    # Сохранение сообщения в хранилище (если требуется)
    admin_responses[user_id] = admin_responses.get(user_id, {
        "user_name": user_name,
        "user_id": user_id,
        "messages": []
    })
    admin_responses[user_id]["messages"].append(message)

    # Отправка сообщений или медиа администратору
    try:
        if message.text:
            await bot.send_message(ADMIN_CHAT_ID, f"Сообщение от {user_name}:\n{message.text}", reply_markup=reply_keyboard)
        elif message.photo:
            await bot.send_photo(
                ADMIN_CHAT_ID,
                photo=message.photo[-1].file_id,
                caption=f"Фото от {user_name}",
                reply_markup=reply_keyboard
            )
        elif message.video:
            await bot.send_video(
                ADMIN_CHAT_ID,
                video=message.video.file_id,
                caption=f"Видео от {user_name}",
                reply_markup=reply_keyboard
            )
        elif message.document:
            await bot.send_document(
                ADMIN_CHAT_ID,
                document=message.document.file_id,
                caption=f"Документ от {user_name}",
                reply_markup=reply_keyboard
            )
        elif message.audio:
            await bot.send_audio(
                ADMIN_CHAT_ID,
                audio=message.audio.file_id,
                caption=f"Аудио от {user_name}",
                reply_markup=reply_keyboard
            )
        elif message.voice:
            await bot.send_voice(
                ADMIN_CHAT_ID,
                voice=message.voice.file_id,
                caption=f"Голосовое сообщение от {user_name}",
                reply_markup=reply_keyboard
            )
        elif message.video_note:
            await bot.send_video_note(
                ADMIN_CHAT_ID,
                video_note=message.video_note.file_id,
                reply_markup=reply_keyboard
            )
        else:
            await message.answer("Неизвестный тип сообщения. Попробуйте отправить текст, фото или другой поддерживаемый формат.")
            return

        # Ответ пользователю
        await message.answer("Ваше сообщение успешно отправлено администраторам.", reply_markup=main_menu())
    except TelegramBadRequest as e:
        await message.reply("Ошибка при отправке сообщения администратору. Попробуйте позже.")
        logging.error(f"Ошибка отправки сообщения администратору: {e}")

    # Очистка состояния
    await state.clear()


# Обработка кнопки "Ответить"
@dp.callback_query(lambda callback: callback.data.startswith("reply_to_"))
async def reply_to_user(callback: types.CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    await state.set_state(AdminStates.waiting_for_reply)
    await state.update_data(user_id=user_id)
    await callback.message.answer("Напишите ответ пользователю.")

# Отправка ответа пользователю
@dp.message(StateFilter(AdminStates.waiting_for_reply))
async def send_reply_to_user(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    text = message.text

    await bot.send_message(user_id, f"Ответ от администратора:\n{text}")
    await message.answer("Ваш ответ отправлен пользователю.")
    await state.clear()

# Кнопка "Функционал"
@dp.message(lambda message: message.text == "Функционал ⚙️")
async def bot_functionality(message: types.Message):
    await message.answer(
        'Функционал бота:\n\n'
        '"Заявка 📝" - при нажатии на эту кнопку, бот попросит описать проблему с которой вы столкнулись, спросит все ли верно он записал и отправит вашу проблему администраторам.\n\n'
        '"Мои заявки 📌" - при нажатии на эту кнопку, вы можете увидеть ваши активные заявки и их статус.\n\n'
        '"Связь с админом 📤" - при нажатии на эту кнопку, вы можете напрямую связаться с администраторами и получить ответ либо помощь, без составления заявки.\n\n',
        reply_markup=main_menu()
    )

# Запуск бота
async def main():
    logging.info("Бот запущен и готов к работе.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
