#!/usr/bin/env python3
"""
Скрипт для запуска телеграм бота
"""

import sys
import logging
from bot import TelegramBot

def main():
    """Главная функция"""
    try:
        # Настройка логирования
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('bot.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info("Запуск телеграм бота...")
        
        # Создаем и запускаем бота
        bot = TelegramBot()
        bot.run()
        
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()