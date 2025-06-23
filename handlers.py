from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from database import Session, User, Task, Subject, func
from datetime import datetime
import re

# Состояния диалога
REGISTER_STATE, CREATE_TASK_TITLE, CREATE_TASK_DESC, CREATE_TASK_SUBJECT, CREATE_TASK_TEACHER, CREATE_TASK_PHOTO = range(6)
SEND_SOLUTION, = range(1, 2)

# Глобальная клавиатура с кнопкой "Меню"
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("Меню")]], 
    resize_keyboard=True,
    is_persistent=True
)

async def start(update: Update, context: CallbackContext) -> int:
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
            await update.message.reply_text(  # Исправлено здесь
                "Добро пожаловать! Выберите ваш статус:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )  # Закрывающая скобка добавлена
            return REGISTER_STATE  # Отступ исправлен

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
    
    # Добавляем кнопку "Меню"
    await update.message.reply_text(
        "Используйте кнопку 'Меню' для навигации:",
        reply_markup=MENU_KEYBOARD
    )
    
    return ConversationHandler.END

async def menu_handler(update: Update, context: CallbackContext):
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
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        if not user or user.user_type != 'student':
            if isinstance(update, Update) and update.message:
                await update.message.reply_text("❌ Доступно только для студентов")
            else:
                query = update.callback_query
                await query.answer()
                await query.edit_message_text("❌ Доступно только для студентов")
            return
    
    keyboard = [
        [InlineKeyboardButton("📝 Создать задание", callback_data='create_task')],
        [InlineKeyboardButton("📋 Мои задания", callback_data='my_tasks')],
        [InlineKeyboardButton("🏆 Рейтинг помощников", callback_data='helper_rating')],
        [InlineKeyboardButton("🔄 Обновить", callback_data='refresh_student_menu')]
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
    
    # Добавляем кнопку "Меню"
    await context.bot.send_message(
        chat_id=chat_id,
        text="Используйте кнопку 'Меню' для навигации:",
        reply_markup=MENU_KEYBOARD
    )

async def show_student_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id).first()
        if not user or user.user_type != 'student':
            await query.edit_message_text("❌ Ошибка доступа")
            return
        
        tasks = session.query(Task).filter_by(student_id=user.id).order_by(Task.status, Task.created_at).all()
        
        if not tasks:
            await query.edit_message_text("У вас нет созданных заданий")
            return
        
        message = ["📋 Ваши задания:"]
        keyboard = []
        
        for task in tasks:
            status_icon = "🆕" if task.status == 'new' else "🔄" if task.status == 'in_progress' else "✅"
            task_info = [
                f"{status_icon} <b>{task.title}</b>",
                f"📝 Описание: {task.description[:50]}...",
                f"🏷 Предмет: {task.subject.name}",
                f"👨‍🏫 Преподаватель: {task.teacher_name}",
                f"📅 Создано: {task.created_at.strftime('%d.%m.%Y %H:%M')}",
                f"🔄 Статус: {task.status}"
            ]
            
            if task.helper:
                task_info.append(f"👨‍🎓 Помощник: {task.helper.full_name}")
            
            message.append("\n".join(task_info))
            
            if task.status == 'new':
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ Удалить '{task.title[:15]}...'", 
                        callback_data=f"delete_task_{task.id}")
                ])
            elif task.status == 'completed' and not task.rating:
                keyboard.append([
                    InlineKeyboardButton(
                        f"⭐ Оценить '{task.title[:15]}...'", 
                        callback_data=f"rate_task_{task.id}")
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_student_menu')])
        
        await query.edit_message_text(
            text="\n\n".join(message),
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard))

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
            await query.edit_message_text("Пока нет помощников с рейтингом")
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
                await update.message.reply_text("❌ Доступно только для помогающих студентов")
            else:
                await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
    
    keyboard = [
        [InlineKeyboardButton("📋 Мои задания", callback_data='helper_my_tasks')],
        [InlineKeyboardButton("🔍 Доступные задания", callback_data='available_tasks')],
        [InlineKeyboardButton("🔄 Обновить", callback_data='refresh_helper_menu')]
    ]
    
    if isinstance(update, Update) and update.message:
        await update.message.reply_text(
            "👨‍🏫 Меню помогающего студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text(
            "👨‍🏫 Меню помогающего студента:",
            reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Добавляем кнопку "Меню"
    await context.bot.send_message(
        chat_id=chat_id,
        text="Используйте кнопку 'Меню' для навигации:",
        reply_markup=MENU_KEYBOARD
    )

async def show_available_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    with Session() as session:
        # Проверяем, что пользователь - помогающий студент
        user = session.query(User).filter_by(chat_id=chat_id, user_type='helper').first()
        if not user:
            await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
        
        # Получаем новые задания (status='new')
        tasks = session.query(Task).filter_by(status='new').all()
        
        if not tasks:
            await query.edit_message_text("Нет доступных заданий")
            return
        
        message = ["🔍 Доступные задания:\n"]
        keyboard = []
        
        for task in tasks:
            message.append(
                f"📌 {task.title}\n"
                f"📝 {task.description[:50]}...\n"
                f"🏷 Предмет: {task.subject.name}\n"
            )
            keyboard.append([InlineKeyboardButton(
                f"Взять задание: {task.title[:20]}...", 
                callback_data=f"take_task_{task.id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')])
        
        await query.edit_message_text(
            text="\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard))

async def take_task(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[2])
    helper_chat_id = update.effective_chat.id
    
    with Session() as session:
        # Получаем задание и помощника
        task = session.query(Task).get(task_id)
        helper = session.query(User).filter_by(chat_id=helper_chat_id, user_type='helper').first()
        
        if not task or not helper:
            await query.edit_message_text("❌ Ошибка: задание или пользователь не найдены")
            return
        
        # Проверяем, что задание еще доступно
        if task.status != 'new':
            await query.edit_message_text("❌ Задание уже взято другим помощником")
            return
        
        # Обновляем задание
        task.status = 'in_progress'
        task.helper_id = helper.id
        session.commit()
        
        # Уведомление помощнику
        await query.edit_message_text(f"✅ Вы взяли задание: {task.title}")
        
        # Уведомление студенту
        try:
            await context.bot.send_message(
                chat_id=task.student.chat_id,
                text=f"🎉 Ваше задание '{task.title}' взял в работу помощник: {helper.full_name}"
            )
        except Exception as e:
            print(f"Ошибка уведомления студента: {e}")
        
        # Показываем меню помощника
        await helper_menu(update, context)

async def show_helper_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='helper').first()
        if not user:
            await query.edit_message_text("❌ Доступно только для помогающих студентов")
            return
        
        # Получаем задания, которые взял этот помощник
        tasks = session.query(Task).filter_by(helper_id=user.id).all()
        
        if not tasks:
            await query.edit_message_text("У вас нет взятых заданий")
            return
        
        message = ["📋 Ваши задания:\n"]
        keyboard = []
        
        for task in tasks:
            message.append(
                f"📌 {task.title}\n"
                f"📝 {task.description[:50]}...\n"
                f"🏷 Предмет: {task.subject.name}\n"
                f"👤 Студент: {task.student.full_name}\n"
                f"🔄 Статус: {task.status}\n"
            )
            
            # Для заданий в работе добавляем кнопки действий
            if task.status == 'in_progress':
                keyboard.append([
                    InlineKeyboardButton(
                        f"📤 Отправить решение '{task.title[:10]}...'", 
                        callback_data=f"submit_solution_{task.id}"),
                    InlineKeyboardButton(
                        f"❌ Отказаться '{task.title[:10]}...'", 
                        callback_data=f"abandon_task_{task.id}")
                ])
        
        keyboard.append([InlineKeyboardButton("🔙 В меню", callback_data='back_to_helper_menu')])
        
        await query.edit_message_text(
            text="\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard))

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
            print(f"Ошибка уведомления студента: {e}")
        
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
            print(f"Ошибка отправки решения студенту: {e}")
    
    # Возвращаемся в меню помощника
    await helper_menu(update, context)
    return ConversationHandler.END

async def create_task_start(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите тему задания:")
    return CREATE_TASK_TITLE

async def task_title_received(update: Update, context: CallbackContext) -> int:
    context.user_data['task_title'] = update.message.text
    await update.message.reply_text("Введите описание задания:")
    return CREATE_TASK_DESC

async def task_description_received(update: Update, context: CallbackContext) -> int:
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
        "Хотите добавить фото к заданию?\n\n"
        "Отправьте фото или нажмите /skip чтобы пропустить")
    return CREATE_TASK_PHOTO

async def task_photo_received(update: Update, context: CallbackContext) -> int:
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
            student_id=user.id,
            photo_id=photo_id,
            status='new'
        )
        session.add(new_task)
        session.commit()
    
    await update.message.reply_text("✅ Задание успешно создано!")
    # Автоматически возвращаемся в меню студента после создания задания
    await student_menu(update, context)
    return ConversationHandler.END

async def skip_photo(update: Update, context: CallbackContext) -> int:
    context.user_data['photo_id'] = None
    return await task_photo_received(update, context)

async def teacher_menu(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    
    with Session() as session:
        user = session.query(User).filter_by(chat_id=chat_id, user_type='teacher').first()
        if not user:
            if isinstance(update, Update) and update.message:
                await update.message.reply_text("❌ Доступно только для преподавателей")
            else:
                query = update.callback_query
                await query.answer()
                await query.edit_message_text("❌ Доступно только для преподавателей")
            return
    
    keyboard = [
        [InlineKeyboardButton("📋 Задания моих студентов", callback_data='teacher_student_tasks')],
        [InlineKeyboardButton("👨‍🎓 Студенты, загрузившие задания", callback_data='teacher_students')],
        [InlineKeyboardButton("👨‍🏫 Помогающие студенты по моим заданиям", callback_data='teacher_helpers')],
        [InlineKeyboardButton("🔄 Обновить", callback_data='refresh_teacher_menu')]
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
    
    # Добавляем кнопку "Меню"
    await context.bot.send_message(
        chat_id=chat_id,
        text="Используйте кнопку 'Меню' для навигации:",
        reply_markup=MENU_KEYBOARD
    )

async def show_teacher_student_tasks(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    chat_id = update.effective_chat.id
    
    with Session() as session:
        teacher = session.query(User).filter_by(chat_id=chat_id, user_type='teacher').first()
        if not teacher:
            await query.edit_message_text("❌ Доступно только для преподавателей")
            return
        
        # Получаем задания, где указано имя преподавателя
        tasks = session.query(Task).filter(
            Task.teacher_name.ilike(f"%{teacher.full_name}%")
        ).all()
        
        if not tasks:
            await query.edit_message_text("Нет заданий с вашим именем")
            return
        
        message = ["📋 Задания моих студентов:\n"]
        for task in tasks:
            message.append(
                f"📌 {task.title}\n"
                f"📝 {task.description[:50]}...\n"
                f"🏷 Предмет: {task.subject.name}\n"
                f"👤 Студент: {task.student.full_name}\n"
                f"🔄 Статус: {task.status}\n"
            )
        
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_teacher_menu')]]
        
        await query.edit_message_text(
            text="\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard))

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
    
    with Session() as session:
        teacher = session.query(User).filter_by(chat_id=chat_id, user_type='teacher').first()
        if not teacher:
            await query.edit_message_text("❌ Доступно только для преподавателей")
            return
        
        # Получаем помощников, которые выполняли задания этого преподавателя
        helpers = session.query(User).join(Task, Task.helper_id == User.id).filter(
            Task.teacher_name.ilike(f"%{teacher.full_name}%"),
            Task.status == 'completed'
        ).distinct().all()
        
        if not helpers:
            await query.edit_message_text("Нет помогающих студентов по вашим заданиям")
            return
        
        message = ["👨‍🏫 Помогающие студенты по вашим заданиям:\n"]
        for helper in helpers:
            message.append(f"- {helper.full_name} ⭐ {helper.rating:.1f} (выполнено: {helper.completed_tasks})")
        
        keyboard = [[InlineKeyboardButton("🔙 В меню", callback_data='back_to_teacher_menu')]]
        
        await query.edit_message_text(
            text="\n".join(message),
            reply_markup=InlineKeyboardMarkup(keyboard))

async def refresh_student_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await student_menu(update, context)

async def back_to_student_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await student_menu(update, context)

async def refresh_helper_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await helper_menu(update, context)

async def back_to_helper_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await helper_menu(update, context)

async def refresh_teacher_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await teacher_menu(update, context)

async def back_to_teacher_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    await teacher_menu(update, context)

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("❌ Действие отменено")
    return ConversationHandler.END

async def cancel_solution(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("❌ Отправка решения отменена")
    return ConversationHandler.END