import asyncio
import logging
from video_processor import VideoProcessor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_video_processor():
    """Тест для нового метода process_chunk_logic"""
    
    video_processor = VideoProcessor()
    
    test_video_path = "temp/chunk_0.mp4"
    clip_duration = 30
    config = {
        'title': 'ТЕСТ',
        'subtitle': 'Клип'
    }
    
    print("🧪 ТЕСТИРОВАНИЕ VideoProcessor.process_chunk_logic")
    print("=" * 50)
    
    try:
        import os
        if not os.path.exists(test_video_path):
            print(f"❌ Тестовый файл не найден: {test_video_path}")
            return
        
        print(f"✅ Тестовый файл найден: {test_video_path}")
        
        clips = await video_processor.process_chunk_logic(
            test_video_path,
            clip_duration,
            config,
            start_index=0
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
    asyncio.run(test_video_processor())
