#!/usr/bin/env python3
"""
Отладочный скрипт для поиска ошибки split()
"""

import asyncio
import logging
import traceback
from video_editor import VideoEditor

# Настройка детального логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def debug_split_error():
    """Отладка ошибки split()"""
    
    print("🔍 ОТЛАДКА ОШИБКИ split()")
    print("=" * 50)
    
    editor = VideoEditor()
    
    # Тестовые данные
    input_path = "temp/БРАТИШКИН ПРО СВОЮ АУДИТОРИЮ И ВНОВЬ ПРО ХЕСУСА.mp4"
    output_path = "output/debug_clip.mp4"
    start_time = 0.0
    duration = 30.0
    subtitles = []
    clip_number = 1
    config = None
    
    try:
        print(f"🎬 Тестируем создание клипа из: {input_path}")
        
        # Сначала проверим get_video_info
        print("1️⃣ Проверяем get_video_info...")
        video_info = editor.get_video_info(input_path)
        print(f"✅ video_info получен: {video_info}")
        
        # Теперь проверим _check_gpu_support
        print("2️⃣ Проверяем _check_gpu_support...")
        gpu_available = editor._check_gpu_support()
        print(f"✅ GPU доступен: {gpu_available}")
        
        # Теперь попробуем создать клип
        print("3️⃣ Создаем клип...")
        success = await editor.create_styled_clip(
            input_path, output_path, start_time, duration, subtitles, clip_number, config
        )
        
        if success:
            print("✅ Клип создан успешно!")
        else:
            print("❌ Клип не создан")
            
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        print(f"📋 ПОЛНЫЙ TRACEBACK:")
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(debug_split_error())