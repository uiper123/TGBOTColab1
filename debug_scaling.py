#!/usr/bin/env python3
"""
Диагностика проблем с масштабированием YouTube vs локальные файлы
"""

import asyncio
import logging
import ffmpeg
from dotenv import load_dotenv
from pathlib import Path
from video_editor import VideoEditor

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def analyze_video_detailed(video_path: str):
    """Детальный анализ видео файла"""
    try:
        print(f"\n🔍 АНАЛИЗ ВИДЕО: {video_path}")
        print("=" * 60)
        
        probe = ffmpeg.probe(video_path)
        
        # Общая информация
        format_info = probe['format']
        print(f"📁 Формат: {format_info.get('format_name', 'неизвестно')}")
        print(f"⏱️  Длительность: {float(format_info.get('duration', 0)):.2f} сек")
        print(f"📊 Размер файла: {int(format_info.get('size', 0)) / 1024 / 1024:.2f} МБ")
        
        # Анализ всех потоков
        for i, stream in enumerate(probe['streams']):
            print(f"\n📺 ПОТОК {i}: {stream['codec_type']}")
            
            if stream['codec_type'] == 'video':
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                fps = stream.get('r_frame_rate', '0/1')
                codec = stream.get('codec_name', 'неизвестно')
                pixel_format = stream.get('pix_fmt', 'неизвестно')
                
                # Вычисляем FPS
                try:
                    fps_num, fps_den = map(int, fps.split('/'))
                    fps_value = fps_num / fps_den if fps_den != 0 else 0
                except:
                    fps_value = 0
                
                print(f"   📐 Разрешение: {width}x{height}")
                print(f"   🎬 FPS: {fps_value:.2f}")
                print(f"   🎥 Кодек: {codec}")
                print(f"   🎨 Пиксельный формат: {pixel_format}")
                
                # Соотношение сторон
                if width > 0 and height > 0:
                    aspect_ratio = width / height
                    print(f"   📏 Соотношение сторон: {aspect_ratio:.3f}")
                    
                    if aspect_ratio > 1.7:
                        print("   📱 Тип: Широкоэкранное (16:9 или шире)")
                    elif aspect_ratio < 0.6:
                        print("   📱 Тип: Вертикальное (9:16 или уже)")
                    else:
                        print("   📱 Тип: Квадратное или близко к нему")
                
                # Дополнительные метаданные
                if 'tags' in stream:
                    tags = stream['tags']
                    if 'rotate' in tags:
                        print(f"   🔄 Поворот: {tags['rotate']}°")
                
                # SAR и DAR (Sample/Display Aspect Ratio)
                sar = stream.get('sample_aspect_ratio', '1:1')
                dar = stream.get('display_aspect_ratio', 'неизвестно')
                print(f"   📊 SAR: {sar}, DAR: {dar}")
                
            elif stream['codec_type'] == 'audio':
                codec = stream.get('codec_name', 'неизвестно')
                sample_rate = stream.get('sample_rate', 0)
                channels = stream.get('channels', 0)
                print(f"   🎵 Аудио кодек: {codec}")
                print(f"   🎵 Частота: {sample_rate} Гц")
                print(f"   🎵 Каналы: {channels}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка анализа: {e}")
        return False

def compare_scaling_logic(original_width: int, original_height: int):
    """Сравнение логики масштабирования"""
    print(f"\n🧮 ЛОГИКА МАСШТАБИРОВАНИЯ для {original_width}x{original_height}")
    print("=" * 60)
    
    # Целевые размеры
    target_screen_width = 1080
    target_screen_height = 1920
    text_area_height = 520
    available_width = target_screen_width
    available_height = target_screen_height - text_area_height
    
    print(f"🎯 Целевой экран: {target_screen_width}x{target_screen_height}")
    print(f"📝 Место для текста: {text_area_height}px")
    print(f"📺 Доступная область: {available_width}x{available_height}")
    
    # Соотношения сторон
    original_aspect = original_width / original_height
    available_aspect = available_width / available_height
    
    print(f"📏 Исходное соотношение: {original_aspect:.3f}")
    print(f"📏 Доступное соотношение: {available_aspect:.3f}")
    
    # Логика масштабирования
    if original_aspect > available_aspect:
        target_width = available_width
        target_height = int(available_width / original_aspect)
        scale_by = "ширине"
    else:
        target_height = available_height
        target_width = int(available_height * original_aspect)
        scale_by = "высоте"
    
    # Коррекция размеров
    target_width = min(target_width, available_width)
    target_height = min(target_height, available_height)
    target_width = target_width - (target_width % 2)
    target_height = target_height - (target_height % 2)
    
    print(f"⚖️  Масштабирование по: {scale_by}")
    print(f"📐 Результат: {target_width}x{target_height}")
    
    # Проверка на проблемы
    final_aspect = target_width / target_height
    print(f"📏 Итоговое соотношение: {final_aspect:.3f}")
    
    if abs(final_aspect - original_aspect) > 0.01:
        print("⚠️  ВНИМАНИЕ: Соотношение сторон изменилось!")
        print(f"   Изменение: {abs(final_aspect - original_aspect):.3f}")
    
    # Проверка размещения
    y_position = (target_screen_height - target_height) / 2
    print(f"📍 Позиция по Y: {y_position:.0f}px")
    
    if y_position < text_area_height / 2:
        print("⚠️  ВНИМАНИЕ: Видео может перекрывать текст сверху!")
    
    return target_width, target_height

async def main():
    """Основная функция диагностики"""
    print("🔍 ДИАГНОСТИКА ПРОБЛЕМ МАСШТАБИРОВАНИЯ")
    print("=" * 60)
    
    # Ищем видео файлы
    temp_dir = Path("temp")
    output_dir = Path("output")
    
    video_files = []
    for directory in [temp_dir, output_dir]:
        if directory.exists():
            video_files.extend(list(directory.glob("*.mp4")))
    
    if not video_files:
        print("❌ Нет видео файлов для анализа")
        return
    
    print(f"📁 Найдено видео файлов: {len(video_files)}")
    
    # Анализируем каждый файл
    for i, video_file in enumerate(video_files[:3]):  # Максимум 3 файла
        print(f"\n{'='*60}")
        print(f"ФАЙЛ {i+1}: {video_file.name}")
        
        # Детальный анализ
        if analyze_video_detailed(str(video_file)):
            # Получаем базовую информацию
            editor = VideoEditor()
            try:
                info = editor.get_video_info(str(video_file))
                compare_scaling_logic(info['width'], info['height'])
            except Exception as e:
                print(f"❌ Ошибка получения информации: {e}")
    
    print(f"\n{'='*60}")
    print("💡 РЕКОМЕНДАЦИИ:")
    print("1. Проверьте, есть ли поворот в метаданных YouTube видео")
    print("2. Убедитесь, что SAR (Sample Aspect Ratio) = 1:1")
    print("3. YouTube может добавлять черные полосы или обрезать видео")
    print("4. Проверьте, не меняется ли разрешение при скачивании")

if __name__ == "__main__":
    asyncio.run(main())