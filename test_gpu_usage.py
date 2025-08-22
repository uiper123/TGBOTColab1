#!/usr/bin/env python3
"""
Тест максимального использования GPU памяти
Запустите этот скрипт и одновременно мониторьте nvidia-smi
"""

import asyncio
import logging
import os
from video_processor import VideoProcessor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_gpu_usage():
    """Тест максимального использования GPU"""
    
    print("🚀 ТЕСТ МАКСИМАЛЬНОГО ИСПОЛЬЗОВАНИЯ GPU")
    print("=" * 50)
    
    # Создаем процессор
    processor = VideoProcessor()
    
    # Проверяем GPU
    gpu_available = processor.video_editor._check_gpu_support()
    if not gpu_available:
        print("❌ GPU недоступен! Тест будет работать на CPU")
        return
    
    print("✅ GPU доступен! Начинаем тест...")
    print("\n📊 МОНИТОРИНГ GPU:")
    print("Откройте новый терминал и запустите: watch -n 1 nvidia-smi")
    print("Вы должны увидеть использование 10-12 ГБ из 15 ГБ Tesla T4")
    print("\n⏳ Начинаем обработку через 5 секунд...")
    
    await asyncio.sleep(5)
    
    # Тестовая конфигурация
    config = {
        'duration': 30,  # 30-секундные клипы
        'title': 'ТЕСТ GPU',
        'subtitle': 'Максимальная нагрузка'
    }
    
    # Найдем тестовое видео
    test_files = []
    for ext in ['.mp4', '.mkv', '.avi', '.mov']:
        for file in os.listdir('.'):
            if file.lower().endswith(ext):
                test_files.append(file)
    
    if not test_files:
        print("❌ Не найдено видео файлов для тестирования!")
        print("Поместите любой видео файл в текущую папку")
        return
    
    test_file = test_files[0]
    print(f"🎬 Используем тестовое видео: {test_file}")
    
    # Запускаем обработку
    print("\n🚀 НАЧИНАЕМ МАКСИМАЛЬНУЮ GPU НАГРУЗКУ!")
    print("Следите за nvidia-smi - должно использоваться 10-12 ГБ VRAM")
    
    result = await processor.process_video_file(test_file, config)
    
    if result['success']:
        print(f"\n✅ ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
        print(f"📊 Создано клипов: {result['total_clips']}")
        print(f"📁 Файл со ссылками: {result['links_file']}")
    else:
        print(f"\n❌ ТЕСТ ЗАВЕРШЕН С ОШИБКОЙ: {result['error']}")

if __name__ == "__main__":
    asyncio.run(test_gpu_usage())