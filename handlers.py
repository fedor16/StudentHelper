from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from database import Session, User, Task, Subject, func
from datetime import datetime
from sqlalchemy.orm import joinedload
import re
import logging

# Настройка логгирования
logger = logging.getLogger(__name__)

# Состояния диалога
REGISTER_STATE, CREATE_TASK_TITLE, CREATE_TASK_DESC, CREATE_TASK_SUBJECT, CREATE_TASK_TEACHER, CREATE_TASK_DEADLINE, CREATE_TASK_ATTACHMENT = range(7)
SEND_SOLUTION, = range(1, 2)

# Глобальная клавиатура с кнопкой "Меню"
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("Меню")]], 
    resize_keyboard=True,
    is_persistent=True
)

async def start(update: Update, context: CallbackContext) -> int:
    # Всегда сбрасываем состояние при старте
    context.user_data.clear()
    
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        
        if user:
            if user.user_type == 'student':
                await student_menu(update, context)
            elif user.user_type == 'helper':
                await helper_menu(update, context)
            elif user.user_type == 'teacher':
                await teacher_menu(update, context)
            return ConversationHandler.END
        else:
            keyboard = [
                [InlineKeyboardButton("Студент", callback_data='student')],
                [InlineKeyboardButton("Помогающий студент", callback_data='helper')],
                [InlineKeyboardButton("Преподаватель", callback_data='teacher')]
            ]
            await update.message.reply_text(
                "Добро пожаловать! Выберите ваш статус:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return REGISTER_STATE

async def register_user(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    user_type = query.data
    context.user_data['user_type'] = user_type
    
    if user_type == 'student':
        await query.edit_message_text("Введите ваше ФИО и группу в формате:\n\nПример: Иванов Иван гр. ИТ-1")
    elif user_type == 'helper':
        await query.edit_message_text("Введите ваше ФИО и группу в формате:\n\nПример: Петров Пётр гр. ИТ-2")
    elif user_type == 'teacher':
        await query.edit_message_text("Введите ваше ФИО в формате:\n\nПример: Сидоров С.А.")
    
    return REGISTER_STATE

async def complete_registration(update: Update, context: CallbackContext) -> int:
    if 'user_type' not in context.user_data:
        await update.message.reply_text("❌ Сначала выберите вашу роль.")
        return REGISTER_STATE
    text = update.message.text
    chat_id = update.effective_chat.id
    user_type = context.user_data['user_type']
    
    if user_type in ['student', 'helper']:
        if not re.search(r'гр\.\s*\w+', text, re.IGNORECASE):
            await update.message.reply_text("❌ Неверный формат. Укажите группу в формате: Иванов Иван гр. ИТ-1")
            return REGISTER_STATE
    
    with Session() as session:
        new_user = User(
            chat_id=chat_id,
            user_type=user_type,
            full_name=text
        )
        
        if user_type in ['student', 'helper']:
            match = re.search(r'гр\.\s*(\w+)', text, re.IGNORECASE)
            if match:
                new_user.group_name = match.group(1).strip()
        
        session.add(new_user)
        session.commit()
    
    # Автоматически открываем соответствующее меню после регистрации
    if user_type == 'student':
        await student_menu(update, context)
    elif user_type == 'helper':
        await helper_menu(update, context)
    elif user_type == 'teacher':
        await teacher_menu(update, context)
    
    return ConversationHandler.END

async def menu_handler(update: Update, context: CallbackContext):
    # Всегда сбрасываем состояние при вызове меню
    context.user_data.clear()
    
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        
        if not user:
            await update.message.reply_text("❌ Сначала зарегистрируйтесь через /start")
            return
        
        if user.user_type == 'student':
            await student_menu(update, context)
        elif user.user_type == 'helper':
            await helper_menu(update, context)
        elif user.user_type == 'teacher':
            await teacher_menu(update, context)

async def student_menu(update: Update, context: CallbackContext):
    # Всегда сбрасываем состояние при входе в меню
    context.user_data.clear()
    
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        if not user or user.user_type != 'student':
            if isinstance(update, Update) and update.message:
                await update.message.reply_text("❌ Доступно только для студентов", reply_markup=MENU_KEYBOARD)
            else:
                query = update.callback_query
                await query.answer()
                await query.edit_message_text("❌ Доступно только для студентов")
            return
    
    keyboard = [
        [InlineKeyboardButton("📝 Создать задание", callback_data='create_task')],
        [InlineKeyboardButton("📋 Мои задания", callback_data='my_tasks')],
        [InlineKeyboardButton("🏆 Рейтинг помощников", callback_data='helper_rating')],
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "👨‍🎓 Меню студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👨‍🎓 Меню студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    return


async def show_student_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    # 2) сразу подгружаем связи subject и helper
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        tasks = session.query(Task)\
                       .options(
                           joinedload(Task.subject),
                           joinedload(Task.helper)
                       )\
                       .filter_by(student_id=user.id)\
                       .order_by(Task.status, Task.created_at)\
                       .all()
        
    if not tasks:
        await query.edit_message_text(
            "❗ У вас нет заданий.\n\n"
            "Используйте /menu, чтобы вернуться в меню."
        )
        return
        
    # 3) формируем сообщение и кнопки вне цикла
    message = ["📋 Ваши задания:"]
    keyboard = []
        
    for task in tasks:
        status_icon = {
            'new': '🆕',
            'in_progress': '🔄',
            'completed': '✅'
        }[task.status]
        
        lines = [
            f"{status_icon} <b>{task.title}</b>",
            f"📝 Описание: {task.description[:50]}…",
            f"🏷 Предмет: {task.subject.name}",        # теперь доступно
            f"👨‍🏫 Преподаватель: {task.teacher_name}",
            f"📅 Создано: {task.created_at.strftime('%d.%m.%Y %H:%M')}",
            f"⏰ Срок: {task.deadline.strftime('%d.%m.%Y')}",
            f"🔄 Статус: {task.status}"
        ]
        if task.helper:
            lines.append(f"👨‍🎓 Помощник: {task.helper.full_name}")
        
        message.append("\n".join(lines))
        
        # кнопки «Удалить» или «Оценить»
        if task.status == 'new':
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ Удалить '{task.title[:15]}…'",
                    callback_data=f"delete_task_{task.id}"
                )
            ])
        elif task.status == 'completed' and not task.rating:
            keyboard.append([
                InlineKeyboardButton(
                    f"⭐ Оценить '{task.title[:15]}…'",
                    callback_data=f"rate_task_{task.id}"
                )
            ])
    
    # 4) единожды добавляем кнопку «В меню»
    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_student_menu')])
    
    # 5) и только один раз шлём итоговое сообщение
    await query.edit_message_text(
        text="\n\n".join(message),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def delete_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    
    with Session() as session:
        task = session.query(Task).get(task_id)
        if not task:
            await query.edit_message_text("❌ Задание не найдено")
            return
            
        if task.status != 'new':
            await query.edit_message_text("❌ Можно удалять только новые задания")
            return
            
        session.delete(task)
        session.commit()
    
    await query.edit_message_text("✅ Задание успешно удалено")
    await show_student_tasks(update, context)

async def rate_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    context.user_data['rating_task_id'] = task_id
    
    keyboard = [
        [InlineKeyboardButton(str(i), callback_data=f'set_rating_{i}') for i in range(1, 6)]
    ]
    await query.edit_message_text(
        "Выберите оценку для задания (1-5):",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def set_rating(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    rating = int(query.data.split('_')[2])
    task_id = context.user_data.get('rating_task_id')
    
    if not task_id:
        await query.edit_message_text("❌ Ошибка: задание не найдено")
        return
    
    with Session() as session:
        task = session.query(Task).get(task_id)
        if not task or task.status != 'completed':
            await query.edit_message_text("❌ Можно оценивать только завершенные задания")
            return
            
        task.rating = rating
        session.commit()
        
        if task.helper:
            helper = session.query(User).get(task.helper.id)
            completed_tasks = session.query(Task)\
                .filter_by(helper_id=helper.id, status='completed')\
                .filter(Task.rating.isnot(None))\
                .count()
                
            if completed_tasks > 0:
                total_rating = session.query(func.sum(Task.rating))\
                    .filter_by(helper_id=helper.id)\
                    .scalar()
                helper.rating = total_rating / completed_tasks
                session.commit()
    
    await query.edit_message_text(f"✅ Вы поставили оценку {rating} за задание")
    await show_student_tasks(update, context)

async def show_helper_rating(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    with Session() as session:
        helpers = session.query(User)\
            .filter_by(user_type='helper')\
            .order_by(User.rating.desc())\
            .all()
        
    if not helpers:
        await query.edit_message_text(
            "Пока нет помощников с рейтингом.\n\n"
            "Используйте /menu для возврата в меню."
        )
        return

        
    message = ["🏆 Рейтинг помощников:\n"]
    for i, helper in enumerate(helpers, 1):
        message.append(
            f"{i}. {helper.full_name} - ⭐ {helper.rating:.1f} "
            f"(выполнено заданий: {helper.completed_tasks})"
        )
        
    keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_student_menu')]]
        
    await query.edit_message_text(
        text="\n".join(message),
        reply_markup=InlineKeyboardMarkup(keyboard))

async def helper_menu(update: Update, context: CallbackContext):
    # Всегда сбрасываем состояние при входе в меню
    context.user_data.clear()
    
    if isinstance(update, Update) and update.message:
        chat_id = update.message.chat_id
    else:
        query = update.callback_query
        await query.answer()
        chat_id = query.message.chat_id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='helper').first()
        if not user:
            if isinstance(update, Update) and update.message:
                await update.message.reply_text("❌ Доступно только для помогающих студентов", reply_markup=MENU_KEYBOARD)
            else:
                await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
    
    keyboard = [
        [InlineKeyboardButton("📋 Мои задания", callback_data='helper_my_tasks')],
        [InlineKeyboardButton("🔍 Доступные задания", callback_data='available_tasks')],
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "👨‍🏫 Меню помогающего студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text(
            "👨‍🏫 Меню помогающего студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    return


async def show_available_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    # Проверяем, что пользователь — помощник и сразу выгружаем новые задания
    with Session() as session:
        helper = session.query(User).filter_by(
            chat_id=chat_id, user_type='helper'
        ).first()
        if not helper:
            await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
        tasks = session.query(Task).filter_by(status='new').all()

    # Если нет ни одного нового задания — сразу даём сообщение и инструкцию /menu
    if not tasks:
        await query.edit_message_text(
            "❗ Нет доступных заданий.\n\n"
            "Используйте /menu, чтобы вернуться в меню."
        )
        return

    # Иначе — показываем меню фильтрации по предметам + «Все задания»
    with Session() as session:
        subjects = session.query(Subject).all()

    total = len(tasks)
    keyboard = [
        [InlineKeyboardButton(f"Все задания ({total})", callback_data="filter_tasks_all")]
    ]
    for subj in subjects:
        cnt = session.query(Task)\
            .filter_by(status='new', subject_id=subj.id)\
            .count()
        keyboard.append([
            InlineKeyboardButton(f"{subj.name} ({cnt})", callback_data=f"filter_tasks_{subj.id}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')])

    await query.edit_message_text(
        "🔍 Выберите предмет или «Все задания»:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def filter_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    data = query.data           # e.g. "filter_tasks_all" или "filter_tasks_3"
    parts = data.split("_")     # ["filter","tasks","all"] или ["filter","tasks","3"]
    key = parts[-1]             # "all" или "3"

    with Session() as session:
        if key == "all":
            tasks = session.query(Task).filter_by(status='new').all()
        else:
            subject_id = int(key)
            tasks = session.query(Task).filter_by(
                status='new',
                subject_id=subject_id
            ).all()

    if not tasks:
        await query.edit_message_text("Нет доступных заданий.")
        return

    lines, kb = [], []
    for i, t in enumerate(tasks, 1):
        lines.append(
            f"{i}. <b>{t.title}</b>\n"
            f"{t.description}\n"
            f"⏰ Дедлайн: {t.deadline.strftime('%d.%m.%Y')}\n"
        )
        kb.append([InlineKeyboardButton(
            f"{i} – {t.title}", 
            callback_data=f"choose_task_{t.id}"
        )])

    kb.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')])
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb)
    )



from sqlalchemy.orm import joinedload

async def choose_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split("_")[2])

    # Загружаем задачу вместе с предметом и автором
    with Session() as session:
        task = (
            session.query(Task)
                   .options(
                        joinedload(Task.subject),
                        joinedload(Task.student)
                   )
                   .get(task_id)
        )
        helper = session.query(User)\
                        .filter_by(chat_id=update.effective_chat.id, user_type='helper')\
                        .first()

        # Переводим задачу в in_progress
        task.status    = 'in_progress'
        task.helper_id = helper.id
        session.commit()

        # Собираем текст сообщения
        text = (
            f"<b>Вы выбрали задание:</b>\n\n"
            f"<b>Тема:</b> {task.title}\n"
            f"<b>Описание:</b>\n{task.description}\n\n"
            f"🏷 <b>Предмет:</b> {task.subject.name}\n"
            f"👨‍🎓 <b>Студент:</b> {task.student.full_name}\n"
            f"⏰ <b>Дедлайн:</b> {task.deadline.strftime('%d.%m.%Y')}\n"
        )

        # Добавляем информацию о вложении, если оно есть
        if task.attachment_id:
            name = task.attachment_name or 'файл'
            text += f"\n📎 Вложение: {name}"

    # Редактируем сообщение помощнику
    await query.edit_message_text(
        text=text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[ 
            InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu') 
        ]])
    )
    if task.attachment_id:
    # мы сохраняли attachment_name='фото' для фото, иначе — real filename
        if task.attachment_name == 'фото':
        # отправляем как фото
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=task.attachment_id
            )
        else:
        # отправляем как документ, с оригинальным именем в подписи
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=task.attachment_id,
                filename=task.attachment_name  # необязательно, но полезно
            )
    # Уведомляем студента, что его задачу взяли в работу
    try:
        await context.bot.send_message(
            chat_id=task.student.chat_id,
            text=(
                f"🎉 Вашу задачу «{task.title}» взял в работу "
                f"помощник: {helper.full_name}"
            )
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления студента: {e}")



async def take_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    helper_chat_id = update.effective_chat.id

    with Session() as session:
        task = session.query(Task).get(task_id)
        helper = session.query(User)\
                        .filter_by(chat_id=helper_chat_id, user_type='helper')\
                        .first()

        if not task or not helper:
            await query.edit_message_text("❌ Ошибка: задание или пользователь не найдены")
            return

        if task.status != 'new':
            await query.edit_message_text("❌ Задание уже взято другим помощником")
            return

        task.status    = 'in_progress'
        task.helper_id = helper.id
        session.commit()

    await query.edit_message_text(f"✅ Вы взяли задание: {task.title}")
    try:
        await context.bot.send_message(
            chat_id=task.student.chat_id,
            text=f"🎉 Ваше задание '{task.title}' взял в работу помощник: {helper.full_name}"
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления студента: {e}")

    await helper_menu(update, context)



async def show_helper_tasks(update, context):
    query = update.callback_query
    await query.answer()
    helper_chat = update.effective_chat.id

    with Session() as session:
        helper = session.query(User).filter_by(
            chat_id=helper_chat, user_type='helper'
        ).first()
        if not helper:
            await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
        tasks = session.query(Task).filter_by(helper_id=helper.id).all()

    if not tasks:
        await query.edit_message_text(
            "❗ У вас нет взятых заданий.\n\n"
            "Используйте /menu, чтобы вернуться в меню."
        )
        return

    lines, kb = [], []
    for i, t in enumerate(tasks, 1):
        title = f"<s>{t.title}</s>" if t.status == 'completed' else t.title
        lines.append(f"{i}. {title} — ⏰ {t.deadline.strftime('%d.%m.%Y')}")

        if t.status == 'in_progress':
            kb.append([
                InlineKeyboardButton(
                    f"📤 Решение {i}",               # <- сокращённая кнопка
                    callback_data=f"submit_solution_{t.id}"
                ),
                InlineKeyboardButton(
                    "ℹ️",
                    callback_data=f"info_task_{t.id}"
                ),
                InlineKeyboardButton(
                    "❌",
                    callback_data=f"abandon_task_{t.id}"
                )
            ])

    kb.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(kb)
    )





async def info_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id  # <-- определили chat_id

    # Получаем задачу вместе со связями
    with Session() as session:
        task = (
            session.query(Task)
                   .options(
                       joinedload(Task.subject),
                       joinedload(Task.student),
                       joinedload(Task.helper)
                   )
                   .get(int(query.data.split("_")[2]))
        )

    # Собираем текст
    text = (
        f"<b>Информация по заданию:</b>\n\n"
        f"<b>Тема:</b> {task.title}\n"
        f"<b>Описание:</b>\n{task.description}\n\n"
        f"🏷 <b>Предмет:</b> {task.subject.name}\n"
        f"👨‍🎓 <b>Студент:</b> {task.student.full_name}\n"
        f"⏰ <b>Дедлайн:</b> {task.deadline.strftime('%d.%m.%Y')}\n"
        f"🔄 <b>Статус:</b> {task.status}"
    )
    if task.helper:
        text += f"\n👨‍🎓 <b>Помощник:</b> {task.helper.full_name}"

    # Кнопка «В меню»
    menu_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')
    ]])

    # Шлём основное описание
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML',
        reply_markup=menu_kb
    )

    # Если есть вложение — отправляем его
    if task.attachment_id:
        if task.attachment_name == 'фото':
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=task.attachment_id
            )
        else:
            await context.bot.send_document(
                chat_id=chat_id,
                document=task.attachment_id,
                filename=task.attachment_name
            )

async def view_my_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    tid = int(query.data.split("_")[3])
    with Session() as session:
        t = session.query(Task).get(tid)

    text = (
        f"<b>{t.title}</b>\n\n"
        f"{t.description}\n\n"
        f"🏷 {t.subject.name}\n"
        f"👨‍🎓 {t.student.full_name}\n"
        f"⏰ Дедлайн: {t.deadline.strftime('%d.%m.%Y')}\n"
        f"🔄 Статус: {t.status}"
    )
    kb = [
        [
          InlineKeyboardButton("📤 Отправить решение", callback_data=f"submit_solution_{tid}"),
          InlineKeyboardButton("❌ Отказаться",          callback_data=f"abandon_task_{tid}")
        ],
        [InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')]
    ]
    await query.edit_message_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(kb))

async def abandon_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    helper_chat_id = update.effective_chat.id
    
    with Session() as session:
        # Получаем задание и помощника
        task = session.query(Task).get(task_id)
        helper = session.query(User).filter_by(chat_id=helper_chat_id, user_type='helper').first()
        
        if not task or not helper or task.helper_id != helper.id:
            await query.edit_message_text("❌ Ошибка: задание не найдено или вы не являетесь исполнителем")
            return
        
        # Возвращаем задание в статус "новое"
        task.status = 'new'
        task.helper_id = None
        session.commit()
        
        # Уведомление помощнику
        await query.edit_message_text(f"❌ Вы отказались от задания: {task.title}")
        
        # Уведомление студенту
        try:
            await context.bot.send_message(
                chat_id=task.student.chat_id,
                text=f"⚠️ Помощник отказался от выполнения вашего задания '{task.title}'. Задание снова доступно для выполнения."
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления студента: {e}")
        
        # Показываем обновленный список заданий помощника
        await show_helper_tasks(update, context)

async def submit_solution(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    
    # Сохраняем ID задания в контексте
    context.user_data['solution_task_id'] = task_id
    
    await query.edit_message_text(
        "📤 Отправьте решение задания (текст, фото, документ или архив):\n\n"
        "Используйте /cancel для отмены")
    return SEND_SOLUTION

async def receive_solution(update: Update, context: CallbackContext) -> int:
    task_id = context.user_data.get('solution_task_id')
    helper_chat_id = update.effective_chat.id
    
    if not task_id:
        await update.message.reply_text("❌ Ошибка: задание не найдено")
        return ConversationHandler.END
    
    with Session() as session:
        # Получаем задание и помощника
        task = session.query(Task).get(task_id)
        helper = session.query(User).filter_by(chat_id=helper_chat_id, user_type='helper').first()
        
        if not task or not helper or task.helper_id != helper.id:
            await update.message.reply_text("❌ Ошибка: задание не найдено или вы не являетесь исполнителем")
            return ConversationHandler.END
        
        # Сохраняем решение в зависимости от типа
        if update.message.text:
            # Текстовое решение
            task.solution_text = update.message.text
        elif update.message.document:
            # Документ (PDF, Word и т.д.)
            task.solution_file_id = update.message.document.file_id
        elif update.message.photo:
            # Фото (берем самое высокое разрешение)
            task.solution_file_id = update.message.photo[-1].file_id
        else:
            await update.message.reply_text("❌ Неподдерживаемый формат решения")
            return SEND_SOLUTION
        
        # Обновляем статус задания
        task.status = 'completed'
        helper.completed_tasks += 1
        session.commit()
        
        # Уведомление помощнику
        await update.message.reply_text("✅ Решение успешно отправлено студенту!")
        
        # Уведомление студенту
        try:
            message = f"🎉 По вашему заданию '{task.title}' готово решение!\nПомощник: {helper.full_name}"
            
            if task.solution_text:
                await context.bot.send_message(
                    chat_id=task.student.chat_id,
                    text=f"{message}\n\nРешение:\n{task.solution_text}"
                )
            elif task.solution_file_id:
                await context.bot.send_message(
                    chat_id=task.student.chat_id,
                    text=message
                )
                # Отправляем файл или фото
                if update.message.document:
                    await context.bot.send_document(
                        chat_id=task.student.chat_id,
                        document=task.solution_file_id
                    )
                else:  # photo
                    await context.bot.send_photo(
                        chat_id=task.student.chat_id,
                        photo=task.solution_file_id
                    )
        except Exception as e:
            logger.error(f"Ошибка отправки решения студенту: {e}")
    
    # Очищаем состояние после отправки решения
    context.user_data.clear()
    
    # Возвращаемся в меню помощника
    await helper_menu(update, context)
    return ConversationHandler.END

async def create_task_start(update: Update, context: CallbackContext) -> int:
    logger.info("Создание задания: пользователь %s начал диалог", update.effective_chat.id)
    query = update.callback_query
    await query.answer()
    
    # Всегда сбрасываем состояние перед началом создания задания
    context.user_data.clear()
    
    await query.edit_message_text("Введите тему задания:")
    return CREATE_TASK_TITLE

async def task_title_received(update: Update, context: CallbackContext) -> int:
    logger.info("Создание задания: пользователь %s ввёл тему: %s", update.effective_chat.id, update.message.text)
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text("Введите описание задания:")
    return CREATE_TASK_DESC

async def task_description_received(update: Update, context: CallbackContext) -> int:
    logger.info("Создание задания: пользователь %s ввёл описание", update.effective_chat.id)
    context.user_data['task_desc'] = update.message.text
    
    with Session() as session:
        subjects = session.query(Subject).all()
    
    keyboard = []
    if subjects:
        for subject in subjects:
            keyboard.append([InlineKeyboardButton(subject.name, callback_data=f"subj_{subject.id}")])
    
    keyboard.append([InlineKeyboardButton("➕ Добавить новый предмет", callback_data="new_subject")])
    
    await update.message.reply_text(
        "Выберите предмет:",
        reply_markup=InlineKeyboardMarkup(keyboard))
    return CREATE_TASK_SUBJECT

async def task_subject_received(update: Update, context: CallbackContext) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        
        if query.data == "new_subject":
            await query.edit_message_text("Введите название нового предмета:")
            return CREATE_TASK_SUBJECT
        else:
            subject_id = int(query.data.split('_')[1])
            context.user_data['subject_id'] = subject_id
            await query.edit_message_text("Введите ФИО преподавателя:")
            return CREATE_TASK_TEACHER
    else:
        subject_name = update.message.text
        
        with Session() as session:
            existing_subject = session.query(Subject).filter_by(name=subject_name).first()
            if existing_subject:
                context.user_data['subject_id'] = existing_subject.id
            else:
                new_subject = Subject(name=subject_name)
                session.add(new_subject)
                session.commit()
                context.user_data['subject_id'] = new_subject.id
        
        await update.message.reply_text("Введите ФИО преподавателя:")
        return CREATE_TASK_TEACHER

async def task_teacher_received(update: Update, context: CallbackContext) -> int:
    context.user_data['teacher_name'] = update.message.text
    await update.message.reply_text(
        "Укажите срок выполнения в формате ДД.MM.ГГГГ\n"
        "(дата должна быть > сегодняшнего дня):")
    return CREATE_TASK_DEADLINE

from datetime import datetime as dt

async def task_deadline_received(update, context) -> int:
    text = update.message.text.strip()
    try:
        deadline = dt.strptime(text, "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используйте ДД.MM.ГГГГ:")
        return CREATE_TASK_DEADLINE

    if deadline.date() <= dt.now().date():
        await update.message.reply_text("❌ Дата должна быть в будущем. Попробуйте снова:")
        return CREATE_TASK_DEADLINE

    context.user_data['deadline'] = deadline
    await update.message.reply_text(
        "Прикрепите файл (изображение, документ, PDF, архив)\n"
        "или нажмите /skip, чтобы пропустить"
    )
    return CREATE_TASK_ATTACHMENT

async def task_attachment_received(update: Update, context: CallbackContext) -> int:
    """Принимает фото или любой документ и создаёт задачу."""
    # 1) Собираем attachment_id/name
    if update.message.photo:
        f = update.message.photo[-1]
        context.user_data['attachment_id']   = f.file_id
        context.user_data['attachment_name'] = 'фото'
    elif update.message.document:
        doc = update.message.document
        context.user_data['attachment_id']   = doc.file_id
        # если у файла есть имя — сохраняем, иначе просто 'документ'
        context.user_data['attachment_name'] = doc.file_name or 'документ'
    else:
        context.user_data['attachment_id']   = None
        context.user_data['attachment_name'] = None

    # 2) Дальше идёт ваш код из старого task_photo_received, 
    #    только вместо photo_id используйте attachment_id и attachment_name.
    #    Пример (упрощённо):
    chat_id     = update.effective_chat.id
    title       = context.user_data['task_title']
    description = context.user_data['task_desc']
    subject_id  = context.user_data['subject_id']
    teacher     = context.user_data['teacher_name']
    deadline    = context.user_data['deadline']
    attach_id   = context.user_data.get('attachment_id')
    attach_name = context.user_data.get('attachment_name')

    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='student').first()
        new_task = Task(
            title=title,
            description=description,
            subject_id=subject_id,
            teacher_name=teacher,
            deadline=deadline,
            student_id=user.id,
            attachment_id=attach_id,
            attachment_name=attach_name,
            status='new'
        )
        session.add(new_task)
        session.commit()

    # 3) Очищаем context и возвращаем меню
    context.user_data.clear()
    await update.message.reply_text("✅ Задание создано!", reply_markup=MENU_KEYBOARD)
    await student_menu(update, context)
    return ConversationHandler.END

async def skip_attachment(update: Update, context: CallbackContext) -> int:
    # если пользователь нажал /skip — просто делаем то же самое,
    # что и task_attachment_received без вложения.
    update.message.text = None
    return await task_attachment_received(update, context)

"""    logger.info("Создание задания: пользователь %s завершает задание", update.effective_chat.id)
    if update.message.photo:
        photo = update.message.photo[-1]
        context.user_data['photo_id'] = photo.file_id
    else:
        context.user_data['photo_id'] = None
    
    # Собираем все данные
    chat_id = update.effective_chat.id
    title = context.user_data['task_title']
    description = context.user_data['task_desc']
    subject_id = context.user_data['subject_id']
    teacher_name = context.user_data['teacher_name']
    photo_id = context.user_data.get('photo_id')
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='student').first()
        if not user:
            await update.message.reply_text("❌ Ошибка: пользователь не найден")
            return ConversationHandler.END
        
        new_task = Task(
            title=title,
            description=description,
            subject_id=subject_id,
            teacher_name=teacher_name,
            deadline=context.user_data['deadline'],
            student_id=user.id,
            photo_id=photo_id,
            status='new'
        )
        session.add(new_task)
        session.commit()
    
    # Очищаем состояние после успешного создания задания
    context.user_data.clear()
    
    await update.message.reply_text("✅ Задание успешно создано!", reply_markup=MENU_KEYBOARD)
    # Автоматически возвращаемся в меню студента после создания задания
    await student_menu(update, context)
    return ConversationHandler.END

async def skip_photo(update: Update, context: CallbackContext) -> int:
    # Устанавливаем отсутствие фото и переходим к созданию задания
    context.user_data['photo_id'] = None
    return await task_photo_received(update, context)"""

async def teacher_menu(update: Update, context: CallbackContext):
    # Всегда сбрасываем состояние при входе в меню
    context.user_data.clear()
    
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='teacher').first()
        if not user:
            if isinstance(update, Update) and update.message:
                await update.message.reply_text("❌ Доступно только для преподавателей", reply_markup=MENU_KEYBOARD)
            else:
                query = update.callback_query
                await query.answer()
                await query.edit_message_text("❌ Доступно только для преподавателей")
            return
    
    keyboard = [
        [InlineKeyboardButton("📋 Задания моих студентов", callback_data='teacher_student_tasks')],
        [InlineKeyboardButton("👨‍🎓 Студенты, загрузившие задания", callback_data='teacher_students')],
        [InlineKeyboardButton("👨‍🏫 Помогающие студенты по моим заданиям", callback_data='teacher_helpers')],
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "👨‍🏫 Меню преподавателя:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👨‍🏫 Меню преподавателя:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    return

from sqlalchemy.orm import joinedload
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import CallbackContext
from database import Session, User, Task

async def show_teacher_student_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    # Забираем задачи преподавателя, сразу подгружая subject, student и helper
    with Session() as session:
        teacher = session.query(User) \
                         .filter_by(chat_id=chat_id, user_type='teacher') \
                         .first()
        if not teacher:
            await query.edit_message_text("❌ Доступно только для преподавателей")
            return

        tasks = (
            session.query(Task)
                   .options(
                       joinedload(Task.subject),
                       joinedload(Task.student),
                       joinedload(Task.helper)
                   )
                   .filter(Task.teacher_name.ilike(f"%{teacher.full_name}%"))
                   .order_by(Task.created_at)
                   .all()
        )

    # Если нет ни одной задачи — отрисуем сообщение
    if not tasks:
        await query.edit_message_text("📭 Пока нет заданий с вашим именем")
        return

    # Собираем текст и кнопки
    message_lines = ["📋 Задания моих студентов:\n"]
    for task in tasks:
        block = [
            f"📌 <b>{task.title}</b>",
            f"📝 {task.description[:50]}…",
            f"🏷 Предмет: {task.subject.name}",
            f"👤 Студент: {task.student.full_name}"
        ]

        # Вложение, если есть
        if task.attachment_id:
            name = task.attachment_name or "файл"
            block.append(f"📎 Вложение: {name}")

        # Помощник, если есть
        if task.helper:
            block.append(f"👨‍🎓 Помощник: {task.helper.full_name}")

        block.append(f"🔄 Статус: {task.status}")
        message_lines.append("\n".join(block) + "\n")

    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_teacher_menu")]
    ]

    # Отправляем единым сообщением
    await query.edit_message_text(
        text="\n".join(message_lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )



async def show_teacher_students(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    with Session() as session:
        teacher = session.query(User).filter_by(chat_id=chat_id, user_type='teacher').first()
        if not teacher:
            await query.edit_message_text("❌ Доступно только для преподавателей")
            return
        
        # Получаем уникальных студентов, которые создали задания с именем преподавателя
        students = session.query(User).join(Task, Task.student_id == User.id).filter(
            Task.teacher_name.ilike(f"%{teacher.full_name}%")
        ).distinct().all()
        
        if not students:
            await query.edit_message_text("Нет студентов, загрузивших задания с вашим именем")
            return
        
        message = ["👨‍🎓 Студенты, загрузившие ваши задания:\n"]
        for student in students:
            message.append(f"- {student.full_name}")
        
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_teacher_menu')]]
        
        await query.edit_message_text(
            text="\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard))



async def show_teacher_helpers(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id

    # Получаем преподавателя и всех helper’ов, завершивших его задачи
    with Session() as session:
        teacher = session.query(User)\
                         .filter_by(chat_id=chat_id, user_type='teacher')\
                         .first()
        if not teacher:
            await query.edit_message_text("❌ Доступно только для преподавателей")
            return

        helpers = (
            session.query(User)
                   .join(Task, Task.helper_id == User.id)
                   .filter(
                        Task.teacher_name.ilike(f"%{teacher.full_name}%"),
                        Task.status == 'completed'
                   )
                   .distinct()
                   .all()
        )

    # 1) Если помощников нет — показываем одно сообщение с кнопкой возврата
    if not helpers:
        await query.edit_message_text(
            text=(
                "Нет помогающих студентов по вашим заданиям.\n\n"
                "Нажмите кнопку ниже, чтобы вернуться в меню."
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 В меню", callback_data="back_to_teacher_menu")
            ]])
        )
        return

    # 2) Иначе — собираем список помощников
    message_lines = ["👨‍🏫 Помогающие студенты по вашим заданиям:\n"]
    for i, helper in enumerate(helpers, start=1):
        message_lines.append(
            f"{i}. {helper.full_name} — ⭐ {helper.rating:.1f} (выполнено: {helper.completed_tasks})"
        )

    # 3) Кнопка возврата
    keyboard = [
        [InlineKeyboardButton("🔙 В меню", callback_data="back_to_teacher_menu")]
    ]

    # 4) Редактируем сообщение одним вызовом
    await query.edit_message_text(
        text="\n".join(message_lines),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def refresh_student_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await student_menu(update, context)

async def back_to_student_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Всегда сбрасываем состояние при возврате в меню
    context.user_data.clear()
    await student_menu(update, context)
    return ConversationHandler.END

async def refresh_helper_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await helper_menu(update, context)

async def back_to_helper_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Всегда сбрасываем состояние при возврате в меню
    context.user_data.clear()
    await helper_menu(update, context)
    return ConversationHandler.END

async def refresh_teacher_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await teacher_menu(update, context)

async def back_to_teacher_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Всегда сбрасываем состояние при возврате в меню
    context.user_data.clear()
    await teacher_menu(update, context)
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    # Очищаем состояние при отмене
    context.user_data.clear()
    await update.message.reply_text("❌ Действие отменено", reply_markup=MENU_KEYBOARD)
    return ConversationHandler.END

async def cancel_solution(update: Update, context: CallbackContext) -> int:
    context.user_data.clear()
    # просто возвращаем меню помощника
    await helper_menu(update, context)
    return ConversationHandler.END
