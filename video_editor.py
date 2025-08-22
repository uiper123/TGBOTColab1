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
            
            # Правильно парсим FPS (может быть в формате "30/1" или "29.97")
            fps_str = video_stream['r_frame_rate']
            if '/' in fps_str:
                numerator, denominator = fps_str.split('/')
                fps = float(numerator) / float(denominator)
            else:
                fps = float(fps_str)
            
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
    
    def _clear_cache(self):
        """Очистка кеша для нового файла"""
        if hasattr(self, '_cached_video_info'):
            delattr(self, '_cached_video_info')
        if hasattr(self, '_cached_video_path'):
            delattr(self, '_cached_video_path')
        if hasattr(self, '_cached_scaling_info'):
            delattr(self, '_cached_scaling_info')

    async def create_clips_parallel(self, video_path: str, clip_duration: int, subtitles: list, start_index: int = 0, config: dict = None, max_parallel: int = None) -> list:
        """ПРОСТОЕ и НАДЕЖНОЕ создание клипов с ограниченной параллельностью"""
        try:
            # Очищаем кеш для нового файла
            self._clear_cache()
            
            logger.info(f"🎬 НАЧИНАЕМ обработку файла: {video_path}")
            
            video_info = self.get_video_info(video_path)
            total_duration = video_info['duration']
            
            # Планируем клипы
            clips_to_create = []
            current_time = 0
            clip_index = start_index
            
            while current_time < total_duration:
                remaining_time = total_duration - current_time
                
                if remaining_time < clip_duration:
                    logger.info(f"Пропущен последний кусок: {remaining_time:.1f} сек < {clip_duration} сек")
                    break
                
                clip_path = self.output_dir / f"clip_{clip_index:03d}.mp4"
                clips_to_create.append({
                    'input_path': video_path,
                    'output_path': str(clip_path),
                    'start_time': current_time,
                    'duration': clip_duration,
                    'subtitles': subtitles,
                    'clip_number': clip_index + 1,
                    'config': config
                })
                
                current_time += clip_duration
                clip_index += 1
            
            # Автоматически определяем оптимальное количество параллельных процессов
            if max_parallel is None:
                gpu_available = self._check_gpu_support()
                if gpu_available:
                    max_parallel = min(8, len(clips_to_create))  # Максимум 8 для GPU (больше VRAM)
                    logger.info(f"🚀 GPU режим: автоматически выбрано {max_parallel} параллельных процессов")
                else:
                    max_parallel = min(4, len(clips_to_create))  # Максимум 4 для CPU
                    logger.info(f"💻 CPU режим: автоматически выбрано {max_parallel} параллельных процессов")
            
            logger.info(f"🚀 Планируется создать {len(clips_to_create)} клипов, макс. параллельно: {max_parallel}")
            
            # ПРОСТАЯ ПОСЛЕДОВАТЕЛЬНАЯ ОБРАБОТКА ПАКЕТАМИ
            created_clips = []
            
            # Разбиваем на пакеты по max_parallel
            for i in range(0, len(clips_to_create), max_parallel):
                batch = clips_to_create[i:i + max_parallel]
                logger.info(f"📦 Обрабатываем пакет {i//max_parallel + 1}: клипы {i+1}-{min(i+max_parallel, len(clips_to_create))}")
                
                # Создаем задачи для текущего пакета
                batch_tasks = []
                for task in batch:
                    batch_tasks.append(self._create_single_clip(task))
                
                # Ждем завершения всех задач в пакете
                try:
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    
                    # Обрабатываем результаты
                    for j, result in enumerate(batch_results):
                        if isinstance(result, Exception):
                            logger.error(f"❌ Ошибка создания клипа {batch[j]['clip_number']}: {result}")
                        elif result:
                            created_clips.append(result)
                            logger.info(f"✅ Клип {batch[j]['clip_number']} готов: {result}")
                        else:
                            logger.warning(f"⚠️ Клип {batch[j]['clip_number']} не создан")
                            
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки пакета: {e}")
                    continue
                
                # Небольшая пауза между пакетами для стабильности
                if i + max_parallel < len(clips_to_create):
                    await asyncio.sleep(1)
            
            logger.info(f"✅ ЗАВЕРШЕНА обработка файла {video_path}: создано {len(created_clips)}/{len(clips_to_create)} клипов")
            return created_clips
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка создания клипов из {video_path}: {e}")
            return []
    
    async def _create_single_clip(self, task: dict) -> str:
        """Создание одного клипа с обработкой ошибок"""
        try:
            import time
            start_time = time.time()
            
            logger.info(f"📝 Создаем клип {task['clip_number']} ({task['start_time']:.1f}-{task['start_time'] + task['duration']:.1f}с)")
            
            success = await self.create_styled_clip(
                task['input_path'],
                task['output_path'],
                task['start_time'],
                task['duration'],
                task['subtitles'],
                task['clip_number'],
                task['config']
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            if success and os.path.exists(task['output_path']):
                logger.info(f"⏱️ Клип {task['clip_number']} создан за {processing_time:.1f} сек")
                return task['output_path']
            else:
                logger.error(f"❌ Клип {task['clip_number']} не создан или файл не существует (время: {processing_time:.1f} сек)")
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания клипа {task['clip_number']}: {e}")
            return None

    async def create_clips(self, video_path: str, clip_duration: int, subtitles: list, start_index: int = 0, config: dict = None) -> list:
        """Создание клипов из видео со строгим таймлайном"""
        try:
            video_info = self.get_video_info(video_path)
            total_duration = video_info['duration']
            
            clips = []
            current_time = 0
            clip_index = start_index
            skipped_clips = 0
            
            while current_time < total_duration:
                end_time = current_time + clip_duration
                
                # СТРОГИЙ ТАЙМЛАЙН: только клипы точной длительности
                remaining_time = total_duration - current_time
                
                # Если оставшееся время меньше заданной длительности - пропускаем
                if remaining_time < clip_duration:
                    logger.info(f"Пропущен последний кусок: {remaining_time:.1f} сек < {clip_duration} сек (строгий таймлайн)")
                    skipped_clips += 1
                    break
                
                clip_path = self.output_dir / f"clip_{clip_index:03d}.mp4"
                
                # Создаем клип с точной длительностью
                success = await self.create_styled_clip(
                    video_path,
                    str(clip_path),
                    current_time,
                    clip_duration,  # Всегда используем точную длительность
                    subtitles,
                    clip_index + 1,
                    config
                )
                
                if success:
                    clips.append(str(clip_path))
                    logger.info(f"Создан клип {clip_index + 1}: {current_time:.1f}-{current_time + clip_duration:.1f} сек ({clip_duration} сек)")
                    clip_index += 1
                else:
                    logger.warning(f"Не удалось создать клип {clip_index + 1}")
                
                current_time += clip_duration
            
            # Детальная статистика
            expected_clips = int(total_duration // clip_duration)
            logger.info(f"📊 СТАТИСТИКА СОЗДАНИЯ КЛИПОВ:")
            logger.info(f"   Длительность видео: {total_duration:.1f} сек")
            logger.info(f"   Ожидалось клипов: {expected_clips}")
            logger.info(f"   Создано клипов: {len(clips)}")
            logger.info(f"   Пропущено клипов: {skipped_clips}")
            logger.info(f"   Эффективность: {len(clips)/expected_clips*100:.1f}%")
            
            return clips
            
        except Exception as e:
            logger.error(f"Ошибка создания клипов: {e}")
            return []
    
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
            import traceback
            logger.error(f"Ошибка создания стилизованного клипа: {e}")
            logger.error(f"Полный traceback: {traceback.format_exc()}")
            return False
    
    def _create_styled_clip_sync(self, input_path: str, output_path: str, start_time: float,
                               duration: float, subtitles: list, clip_number: int, config: dict = None):
        """Синхронное создание стилизованного клипа с GPU ускорением """
        
        try:
            logger.info(f"🔧 Начинаем создание клипа {clip_number}: {input_path}")
            
            # Проверяем доступность GPU
            gpu_available = self._check_gpu_support()
            logger.info(f"🔧 GPU доступен: {gpu_available}")
        except Exception as e:
            logger.error(f"🔧 Ошибка в начале _create_styled_clip_sync: {e}")
            import traceback
            logger.error(f"🔧 Traceback: {traceback.format_exc()}")
            raise
        
        if gpu_available:
            # ПОЛНОЕ GPU ускорение: декодирование на GPU
            main_video = ffmpeg.input(input_path, ss=start_time, t=duration, 
                                    hwaccel='cuda', hwaccel_output_format='cuda')
            logger.info(f"🚀 Клип {clip_number}: ПОЛНОЕ GPU ускорение (декодирование + обработка + кодирование)")
        else:
            # CPU ввод для fallback
            main_video = ffmpeg.input(input_path, ss=start_time, t=duration)
            logger.info(f"💻 Клип {clip_number}: используется CPU обработка")
        
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
        
        # Финальный вывод с МАКСИМАЛЬНЫМ GPU ускорением
        if gpu_available:
            # МАКСИМАЛЬНОЕ GPU ускорение (NVIDIA NVENC) - используем больше GPU памяти
            try:
                (
                    ffmpeg
                    .output(final_video_scaled, audio, output_path, 
                           vcodec='h264_nvenc',    # GPU кодировщик NVIDIA
                           acodec='aac',
                           preset='p2',            # БЫСТРЫЙ NVENC пресет (p1=fastest, p2=faster)
                           rc='vbr',               # Variable bitrate для NVENC
                           cq=20,                  # Более высокое качество (меньше число = лучше качество)
                           pix_fmt='yuv420p',      # Совместимость
                           gpu=0,                  # Принудительно используем первый GPU
                           **{'b:v': '10M',        # Увеличенный битрейт для лучшего качества
                              'b:a': '128k',       # Стандартный битрейт аудио
                              'maxrate': '15M',    # Увеличенный максимальный битрейт
                              'bufsize': '20M',    # Увеличенный размер буфера (больше GPU памяти)
                              'surfaces': '32',    # Больше поверхностей для GPU (использует больше VRAM)
                              'delay': '0',        # Минимальная задержка
                              'rc-lookahead': '32'}) # Увеличенный lookahead (больше GPU вычислений)
                    .overwrite_output()
                    .run(quiet=True)
                )
                logger.info(f"🚀 Клип {clip_number}: создан с МАКСИМАЛЬНЫМ GPU ускорением (10-12 ГБ VRAM)")
            except Exception as nvenc_error:
                logger.warning(f"⚠️ Клип {clip_number}: GPU не сработал, fallback на CPU: {nvenc_error}")
                # Fallback на CPU
                (
                    ffmpeg
                    .output(final_video_scaled, audio, output_path, 
                           vcodec='libx264',
                           acodec='aac',
                           preset='fast',
                           crf=23,
                           pix_fmt='yuv420p',
                           **{'b:a': '128k',
                              'maxrate': '8M',
                              'bufsize': '12M',
                              'profile:v': 'main',
                              'level': '4.0'})
                    .overwrite_output()
                    .run(quiet=True)
                )
                logger.info(f"💻 Клип {clip_number}: создан с CPU fallback")
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