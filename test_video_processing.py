#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений в обработке видео
"""

import asyncio
import logging
from video_editor import VideoEditor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_video_processing():
    """Тест обработки видео с исправлениями"""
    
    # Создаем экземпляр видеоредактора
    video_editor = VideoEditor()
    
    # Тестовые параметры
    test_video_path = "temp/chunk_0.mp4"  # Путь к тестовому видео
    clip_duration = 30  # 30 секунд на клип
    subtitles = []  # Пустые субтитры для теста
    config = {
        'title': 'ТЕСТ',
        'subtitle': 'Клип'
    }
    
    print("🧪 ТЕСТИРОВАНИЕ ИСПРАВЛЕНИЙ ОБРАБОТКИ ВИДЕО")
    print("=" * 50)
    
    try:
        # Проверяем, существует ли тестовый файл
        import os
        if not os.path.exists(test_video_path):
            print(f"❌ Тестовый файл не найден: {test_video_path}")
            print("Создайте тестовый файл или измените путь в скрипте")
            return
        
        print(f"✅ Тестовый файл найден: {test_video_path}")
        
        # Получаем информацию о видео
        video_info = video_editor.get_video_info(test_video_path)
        print(f"📹 Информация о видео:")
        print(f"   Длительность: {video_info['duration']:.1f} сек")
        print(f"   Разрешение: {video_info['width']}x{video_info['height']}")
        print(f"   FPS: {video_info['fps']}")
        
        # Тестируем создание клипов
        print("\n🚀 Запускаем тест создания клипов...")
        clips = await video_editor.create_clips_parallel(
            test_video_path,
            clip_duration,
            subtitles,
            start_index=0,
            config=config,
            max_parallel=2  # Ограничиваем для теста
        )
        
        print(f"\n✅ ТЕСТ ЗАВЕРШЕН!")
        print(f"   Создано клипов: {len(clips)}")
        for i, clip_path in enumerate(clips):
            print(f"   Клип {i+1}: {clip_path}")
            
    except Exception as e:
        print(f"❌ ОШИБКА ТЕСТА: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_video_processing())