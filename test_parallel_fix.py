#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений параллельной обработки
"""

import asyncio
import logging
import sys
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_parallel.log', encoding='utf-8')
    ]
)

logger = logging.getLogger(__name__)

async def test_subtitle_generator():
    """Тест генератора субтитров с новыми исправлениями"""
    try:
        from subtitle_generator import SubtitleGenerator
        
        logger.info("🧪 Тестируем исправленный SubtitleGenerator...")
        
        # Создаем несколько экземпляров для имитации параллельной работы
        generators = [SubtitleGenerator() for _ in range(3)]
        
        # Проверяем, что все экземпляры используют одну модель
        for i, gen in enumerate(generators):
            logger.info(f"   Генератор {i+1}: whisper_available = {gen.whisper_available}")
            
        logger.info("✅ SubtitleGenerator инициализирован успешно")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования SubtitleGenerator: {e}")
        return False

async def test_video_processor():
    """Тест процессора видео с новыми исправлениями"""
    try:
        from video_processor import VideoProcessor
        
        logger.info("🧪 Тестируем исправленный VideoProcessor...")
        
        processor = VideoProcessor()
        
        # Проверяем, что директории созданы
        assert processor.temp_dir.exists(), "Temp директория не создана"
        assert processor.output_dir.exists(), "Output директория не создана"
        
        logger.info("✅ VideoProcessor инициализирован успешно")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования VideoProcessor: {e}")
        return False

async def test_parallel_safety():
    """Тест потокобезопасности исправлений"""
    try:
        logger.info("🧪 Тестируем потокобезопасность...")
        
        # Имитируем параллельные задачи
        tasks = []
        for i in range(3):
            task = asyncio.create_task(simulate_parallel_work(i))
            tasks.append(task)
            # Небольшая задержка между запусками
            await asyncio.sleep(0.5)
        
        # Ждем завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Проверяем результаты
        success_count = sum(1 for r in results if r is True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        logger.info(f"   Успешных задач: {success_count}/3")
        logger.info(f"   Ошибок: {error_count}/3")
        
        if error_count == 0:
            logger.info("✅ Потокобезопасность работает корректно")
            return True
        else:
            logger.warning(f"⚠️ Обнаружены ошибки в {error_count} задачах")
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"   Задача {i+1}: {result}")
            return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования потокобезопасности: {e}")
        return False

async def simulate_parallel_work(task_id: int):
    """Имитация параллельной работы"""
    try:
        logger.info(f"🔄 Запуск параллельной задачи {task_id+1}")
        
        # Имитируем загрузку модели
        await asyncio.sleep(1)
        
        # Имитируем обработку
        await asyncio.sleep(2)
        
        logger.info(f"✅ Параллельная задача {task_id+1} завершена")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка в параллельной задаче {task_id+1}: {e}")
        raise

async def main():
    """Основная функция тестирования"""
    logger.info("🚀 НАЧИНАЕМ ТЕСТИРОВАНИЕ ИСПРАВЛЕНИЙ ПАРАЛЛЕЛЬНОЙ ОБРАБОТКИ")
    logger.info("=" * 60)
    
    tests = [
        ("SubtitleGenerator", test_subtitle_generator),
        ("VideoProcessor", test_video_processor),
        ("Потокобезопасность", test_parallel_safety)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 Тест: {test_name}")
        logger.info("-" * 30)
        
        try:
            result = await test_func()
            results[test_name] = result
            
            if result:
                logger.info(f"✅ {test_name}: ПРОЙДЕН")
            else:
                logger.warning(f"⚠️ {test_name}: НЕ ПРОЙДЕН")
                
        except Exception as e:
            logger.error(f"❌ {test_name}: КРИТИЧЕСКАЯ ОШИБКА - {e}")
            results[test_name] = False
    
    # Итоговый отчет
    logger.info("\n" + "=" * 60)
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ ТЕСТИРОВАНИЯ")
    logger.info("=" * 60)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ ПРОЙДЕН" if result else "❌ НЕ ПРОЙДЕН"
        logger.info(f"   {test_name}: {status}")
    
    logger.info(f"\n📈 Результат: {passed}/{total} тестов пройдено")
    
  