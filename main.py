import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from handlers import *
from database import init_db
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    application = ApplicationBuilder().token(TOKEN).build()
    
    # Обработчик регистрации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REGISTER_STATE: [
                CallbackQueryHandler(register_user, pattern='^(student|helper|teacher)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, complete_registration)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)], 
        per_chat=True
    )
    
    # Обработчик создания задания (обратите внимание на allow_reentry=True)
    task_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(create_task_start, pattern='^create_task$')],
        states={
            CREATE_TASK_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_title_received),
                CommandHandler('cancel', cancel)
            ],
            CREATE_TASK_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_description_received),
                CommandHandler('cancel', cancel)
            ],
            CREATE_TASK_SUBJECT: [
                CallbackQueryHandler(task_subject_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_subject_received),
                CommandHandler('cancel', cancel)
            ],
            CREATE_TASK_TEACHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_teacher_received),
                CommandHandler('cancel', cancel)
            ],
            CREATE_TASK_DEADLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_deadline_received),
                CommandHandler('cancel', cancel)
            ],
            CREATE_TASK_ATTACHMENT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, task_attachment_received),
                CommandHandler('skip', skip_attachment),
                CommandHandler('cancel', cancel)
            ]

        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CallbackQueryHandler(back_to_student_menu, pattern='^back_to_student_menu$')
        ],
        per_chat=True,
        allow_reentry=True  # Позволяет повторно запускать диалог создания задания
    )
    
    # Обработчик отправки решения (также добавлен allow_reentry)
    solution_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_solution, pattern='^submit_solution_')],
        states={
            SEND_SOLUTION: [
                MessageHandler(
                    filters.TEXT | filters.PHOTO | filters.Document.ALL,
                    receive_solution
                ),
                CommandHandler('cancel', cancel_solution)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_solution)],
        per_chat=True,
        allow_reentry=True
    )
    
    # Регистрация обработчиков
    application.add_handler(conv_handler)
    application.add_handler(task_conv)
    application.add_handler(solution_conv)
    
    # Обработчики меню
    application.add_handler(CommandHandler('menu', menu_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^Меню$'), menu_handler))
    
    # Обработчики для студента
    application.add_handler(CallbackQueryHandler(show_student_tasks, pattern='^my_tasks$'))
    application.add_handler(CallbackQueryHandler(show_helper_rating, pattern='^helper_rating$'))
    application.add_handler(CallbackQueryHandler(delete_task, pattern='^delete_task_'))
    application.add_handler(CallbackQueryHandler(rate_task, pattern='^rate_task_'))
    application.add_handler(CallbackQueryHandler(set_rating, pattern='^set_rating_'))
    application.add_handler(CallbackQueryHandler(refresh_student_menu, pattern='^refresh_student_menu$'))
    application.add_handler(CallbackQueryHandler(back_to_student_menu, pattern='^back_to_student_menu$'))
    
    # Обработчики для помогающего студента
    application.add_handler(CallbackQueryHandler(take_task, pattern='^take_task_'))
    application.add_handler(CallbackQueryHandler(abandon_task, pattern='^abandon_task_'))
    application.add_handler(CallbackQueryHandler(helper_menu, pattern='^refresh_helper_menu$'))
    application.add_handler(CallbackQueryHandler(helper_menu, pattern='^back_to_helper_menu$'))
    application.add_handler(CallbackQueryHandler(show_helper_tasks, pattern='^helper_my_tasks$'))
    application.add_handler(CallbackQueryHandler(show_available_tasks, pattern='^available_tasks$'))
    
    # Обработчики для преподавателя
    application.add_handler(CallbackQueryHandler(teacher_menu, pattern='^refresh_teacher_menu$'))
    application.add_handler(CallbackQueryHandler(back_to_teacher_menu, pattern='^back_to_teacher_menu$'))
    application.add_handler(CallbackQueryHandler(show_teacher_student_tasks, pattern='^teacher_student_tasks$'))
    application.add_handler(CallbackQueryHandler(show_teacher_students, pattern='^teacher_students$'))
    application.add_handler(CallbackQueryHandler(show_teacher_helpers, pattern='^teacher_helpers$'))
    
    application.add_handler(CallbackQueryHandler(filter_tasks, pattern=r'^filter_tasks_'))
    application.add_handler(CallbackQueryHandler(choose_task,    pattern=r'^choose_task_'))
    application.add_handler(CallbackQueryHandler(view_my_task,  pattern=r'^view_my_task_'))
    application.add_handler(CallbackQueryHandler(info_task, pattern=r'^info_task_'))
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()