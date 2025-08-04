import os
import asyncio
import logging
import ffmpeg
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoEditor:
    def __init__(self):
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Настройки для оформления
        self.font_path = "Obelix Pro.ttf"  # Путь к шрифту
        self.title_color = "red"
        self.subtitle_color = "red"
    
    def get_video_info(self, video_path: str) -> dict:
        """Получение информации о видео"""
        try:
            probe = ffmpeg.probe(video_path)
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            
            if not video_stream:
                raise ValueError("Видео поток не найден")
            
            duration = float(probe['format']['duration'])
            width = int(video_stream['width'])
            height = int(video_stream['height'])
            fps = eval(video_stream['r_frame_rate'])
            
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'fps': fps
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о видео: {e}")
            raise
    
    async def extract_segment(self, input_path: str, output_path: str, start_time: float, duration: float) -> bool:
        """Извлечение сегмента видео"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._extract_segment_sync,
                input_path, output_path, start_time, duration
            )
            return True
            
        except Exception as e:
            logger.error(f"Ошибка извлечения сегмента: {e}")
            return False
    
    def _extract_segment_sync(self, input_path: str, output_path: str, start_time: float, duration: float):
        """Синхронное извлечение сегмента"""
        (
            ffmpeg
            .input(input_path, ss=start_time, t=duration)
            .output(output_path, vcodec='libx264', acodec='aac')
            .overwrite_output()
            .run(quiet=True)
        )
    
    
    
    async def create_styled_clip(self, input_path: str, output_path: str, start_time: float, 
                               duration: float, subtitles: list, clip_number: int, config: dict = None) -> bool:
        """Создание стилизованного клипа"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._create_styled_clip_sync,
                input_path, output_path, start_time, duration, subtitles, clip_number, config
            )
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания стилизованного клипа: {e}")
            return False
    
    def _create_styled_clip_sync(self, input_path: str, output_path: str, start_time: float,
                               duration: float, subtitles: list, clip_number: int, config: dict = None):
        """Синхронное создание стилизованного клипа с GPU ускорением"""
        
        # Проверяем доступность GPU
        gpu_available = self._check_gpu_support()
        
        # Всегда используем CPU ввод для стабильности в Colab
        main_video = ffmpeg.input(input_path, ss=start_time, t=duration)
        logger.info(f"💻 Используем CPU для создания клипа {clip_number}")
        
        # Создаем размытый фон (растягиваем на весь экран) - ВЕРТИКАЛЬНЫЙ ФОРМАТ
        blurred_bg = (
            main_video
            .video
            .filter('scale', 1080, 1920, force_original_aspect_ratio='increase')  # Принудительно вертикальный
            .filter('crop', 1080, 1920)  # Обрезаем до точного размера
            .filter('gblur', sigma=20)
        )
        
        # Основное видео по центру - МАКСИМАЛЬНОЕ масштабирование с обрезкой
        # Получаем информацию об исходном видео
        video_info = self.get_video_info(input_path)
        original_width = video_info['width']
        original_height = video_info['height']
        original_fps = video_info['fps']
        
        logger.info(f"🎬 ОБРАБОТКА ВИДЕО МАКСИМАЛЬНОГО КАЧЕСТВА:")
        logger.info(f"   📐 Исходное разрешение: {original_width}x{original_height} ({original_height}p)")
        logger.info(f"   🎞️  FPS: {original_fps}")
        logger.info(f"   🎯 Целевое разрешение: 1080x1920 (вертикальный формат)")
        
        # Определяем тип качества исходного видео
        quality_type = "SD"
        if original_height >= 2160:
            quality_type = "4K Ultra HD"
        elif original_height >= 1440:
            quality_type = "2K/1440p"
        elif original_height >= 1080:
            quality_type = "Full HD 1080p"
        elif original_height >= 720:
            quality_type = "HD 720p"
        
        logger.info(f"   🏆 Качество исходного видео: {quality_type}")
        
        # Целевые размеры для вертикального формата (9:16)
        target_screen_width = 1080
        target_screen_height = 1920
        
        # КРУПНОЕ ЦЕНТРАЛЬНОЕ ВИДЕО: заполняем большую часть экрана с обрезкой
        
        # Вычисляем соотношения сторон
        original_aspect = original_width / original_height
        target_aspect = target_screen_width / target_screen_height  # 9:16 = 0.5625
        
        # Для больших видео (4K+) используем более агрессивное масштабирование
        is_large_video = original_width >= 2160 or original_height >= 2160
        
        # АГРЕССИВНОЕ МАСШТАБИРОВАНИЕ: основное видео занимает 80% высоты экрана
        # Это сделает его очень крупным, с обрезкой по бокам если нужно
        center_video_height = int(target_screen_height * 0.8)  # 80% высоты экрана (1536px)
        
        if original_aspect > target_aspect:
            # Широкое видео - масштабируем по ВЫСОТЕ для максимального размера
            target_height = center_video_height
            target_width = int(target_height * original_aspect)
            
            # Если ширина больше экрана - пусть обрезается, как вы просили
            crop_needed = target_width > target_screen_width
            if crop_needed:
                crop_width = target_screen_width
                crop_height = target_height
                logger.info(f"Широкое видео: {target_width}x{target_height} -> обрезка до {crop_width}x{crop_height}")
            else:
                logger.info(f"Широкое видео: {target_width}x{target_height} (помещается)")
                
        else:
            # Высокое или квадратное видео - тоже масштабируем по высоте
            target_height = center_video_height
            target_width = int(target_height * original_aspect)
            crop_needed = False
            logger.info(f"Высокое видео: {target_width}x{target_height}")
        
        # Убеждаемся, что размеры четные
        target_width = target_width - (target_width % 2)
        target_height = target_height - (target_height % 2)
        
        logger.info(f"Исходное видео: {original_width}x{original_height} (соотношение: {original_aspect:.2f})")
        logger.info(f"Целевой экран: {target_screen_width}x{target_screen_height}")
        logger.info(f"КРУПНОЕ видео: {target_width}x{target_height} (займет 80% высоты экрана)")
        
        # Используем улучшенное масштабирование для больших видео
        if is_large_video:
            # Для больших видео используем высококачественный алгоритм масштабирования
            main_scaled = (
                main_video
                .video
                .filter('scale', target_width, target_height, 
                       flags='lanczos')  # Высококачественный алгоритм
            )
            logger.info(f"Используется Lanczos масштабирование для большого видео")
        else:
            # Для обычных видео используем стандартное масштабирование
            main_scaled = (
                main_video
                .video
                .filter('scale', target_width, target_height)
            )
        
        # Если нужна обрезка по бокам - применяем crop фильтр
        if crop_needed:
            main_scaled = main_scaled.filter('crop', crop_width, crop_height, 
                                           x='(iw-ow)/2', y='(ih-oh)/2')  # Обрезаем по центру
        
        # Накладываем основное видео на размытый фон
        video_with_bg = ffmpeg.filter([blurred_bg, main_scaled], 'overlay', 
                                    x='(W-w)/2', y='(H-h)/2')
        
        # Получаем пользовательские заголовки из config
        if config:
            title_template = config.get('title', 'ФРАГМЕНТ')
            subtitle_template = config.get('subtitle', 'Часть')
            custom_title = config.get('custom_title', False)
            custom_subtitle = config.get('custom_subtitle', False)
        else:
            title_template = 'ФРАГМЕНТ'
            subtitle_template = 'Часть'
            custom_title = False
            custom_subtitle = False
        
        # Формируем заголовки
        if custom_title:
            # Если заголовок пользовательский - не добавляем цифру
            title_text = title_template
        else:
            # Если стандартный - добавляем номер клипа
            title_text = f"{title_template} {clip_number}"
            
        if custom_subtitle:
            # Если подзаголовок пользовательский - не добавляем цифру
            subtitle_text = subtitle_template
        else:
            # Если стандартный - добавляем номер клипа
            subtitle_text = f"{subtitle_template} {clip_number}"
        
        # Заголовок (сверху) - появляется с 8 секунды БЕЗ анимации для стабильности
        title_start_time = 8.0  # Заголовки появляются с 8 секунды
        
        video_with_title = video_with_bg.drawtext(
            text=title_text,
            fontfile=self.font_path if os.path.exists(self.font_path) else None,
            fontsize=60,
            fontcolor=self.title_color,
            x='(w-text_w)/2',
            y='100',
            enable=f'between(t,{title_start_time},{duration})'
        )
        
        # Подзаголовок (под заголовком) - появляется с 8 секунды
        video_with_subtitle = video_with_title.drawtext(
            text=subtitle_text,
            fontfile=self.font_path if os.path.exists(self.font_path) else None,
            fontsize=80,  # Больше заголовка
            fontcolor=self.subtitle_color,
            x='(w-text_w)/2',
            y='200',
            enable=f'between(t,{title_start_time},{duration})'
        )
        
        # Добавляем субтитры с анимацией
        final_video = self._add_animated_subtitles(
            video_with_subtitle, 
            subtitles, 
            start_time, 
            duration
        )
        
        # Аудио
        audio = main_video.audio
        
        # ПРИНУДИТЕЛЬНО добавляем финальное масштабирование до 9:16
        final_video_scaled = final_video.filter('scale', 1080, 1920, force_original_aspect_ratio='decrease').filter('pad', 1080, 1920, '(ow-iw)/2', '(oh-ih)/2')
        
        # Финальный вывод с GPU/CPU кодировщиком
        if gpu_available:
            # GPU ускоренный вывод (NVIDIA NVENC) - ИСПРАВЛЕННАЯ ВЕРСИЯ
            (
                ffmpeg
                .output(final_video_scaled, audio, output_path, 
                       vcodec='h264_nvenc',    # GPU кодировщик NVIDIA
                       acodec='aac',
                       preset='fast',          # Быстрый пресет для стабильности
                       cq=23,                  # Разумное качество (23 хорошо для GPU)
                       pix_fmt='yuv420p',      # Совместимость
                       **{'b:v': '8M',         # Разумный битрейт
                          'b:a': '128k',       # Стандартный битрейт аудио
                          'maxrate': '10M',    # Максимальный битрейт
                          'bufsize': '16M',    # Размер буфера
                          'profile:v': 'main', # Основной профиль (более совместимый)
                          'level': '4.0'})     # Правильный уровень для Full HD
                .overwrite_output()
                .run()
            )
            logger.info(f"🎮 Клип {clip_number} создан с GPU ускорением МАКСИМАЛЬНОГО КАЧЕСТВА (1080x1920)")
        else:
            # CPU вывод с улучшенным качеством для больших видео
            if is_large_video:
                # Для больших видео используем ИСПРАВЛЕННЫЕ настройки качества
                (
                    ffmpeg
                    .output(final_video_scaled, audio, output_path, 
                           vcodec='libx264',
                           acodec='aac',
                           preset='fast',          # Быстрый пресет для стабильности
                           crf=23,                 # Разумное качество
                           pix_fmt='yuv420p',
                           **{'b:a': '128k',       # Стандартный битрейт аудио
                              'maxrate': '8M',     # Разумный максимальный битрейт
                              'bufsize': '12M',    # Размер буфера
                              'profile:v': 'main', # Основной профиль (более совместимый)
                              'level': '4.0'})     # Правильный уровень для Full HD
                    .overwrite_output()
                    .run()
                )
                logger.info(f"💻 Большое видео - клип {clip_number} создан с высоким качеством (1080x1920)")
            else:
                # Для обычных видео используем ИСПРАВЛЕННЫЕ настройки качества
                (
                    ffmpeg
                    .output(final_video_scaled, audio, output_path, 
                           vcodec='libx264',
                           acodec='aac',
                           preset='fast',          # Быстрый пресет для стабильности
                           crf=23,                 # Разумное качество
                           pix_fmt='yuv420p',
                           **{'b:a': '128k',       # Стандартный битрейт аудио
                              'maxrate': '8M',     # Разумный максимальный битрейт
                              'bufsize': '12M',    # Размер буфера
                              'profile:v': 'main', # Основной профиль (более совместимый)
                              'level': '4.0'})     # Правильный уровень для Full HD
                    .overwrite_output()
                    .run()
                )
                logger.info(f"💻 Клип {clip_number} создан с CPU ВЫСОКОГО КАЧЕСТВА (1080x1920)")
    
    def _add_animated_subtitles(self, video, subtitles: list, start_time: float, duration: float):
        """Добавление анимированных субтитров"""
        if not subtitles:
            return video
        
        # Фильтруем субтитры для текущего сегмента
        segment_subtitles = []
        for sub in subtitles:
            sub_start = sub['start'] - start_time
            sub_end = sub['end'] - start_time
            
            # Проверяем, попадает ли субтитр в текущий сегмент
            if sub_end > 0 and sub_start < duration:
                # Корректируем время для сегмента
                adjusted_start = max(0, sub_start)
                adjusted_end = min(duration, sub_end)
                
                segment_subtitles.append({
                    'text': sub['text'],
                    'start': adjusted_start,
                    'end': adjusted_end
                })
        
        # Добавляем каждый субтитр с анимацией подпрыгивания
        result_video = video
        for i, sub in enumerate(segment_subtitles):
            # Упрощенная анимация для стабильности
            y_pos = f"h-200-20*abs(sin(2*PI*(t-{sub['start']})*2))"
            
            result_video = result_video.drawtext(
                text=sub['text'],
                fontfile=self.font_path if os.path.exists(self.font_path) else None,
                fontsize=70,  # Увеличил размер субтитров
                fontcolor='white',
                bordercolor='black',
                borderw=3,  # Увеличил толщину обводки
                x='(w-text_w)/2',
                y=y_pos,
                enable=f"between(t,{sub['start']},{sub['end']})"
            )
        
        return result_video
    
    def _check_gpu_support(self) -> bool:
        """Проверка поддержки GPU для ffmpeg"""
        try:
            import subprocess
            
            # Проверяем доступность NVENC (NVIDIA GPU кодировщик)
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            
            if 'h264_nvenc' in result.stdout:
                logger.info("✅ GPU поддержка (NVENC) доступна для ffmpeg")
                return True
            else:
                logger.info("❌ GPU поддержка недоступна, используем CPU")
                return False
                
        except Exception as e:
            logger.warning(f"Ошибка проверки GPU: {e}, используем CPU")
            return False