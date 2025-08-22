import os
import asyncio
import logging
import ffmpeg
from pathlib import Path
from youtube_downloader import YouTubeDownloader
from video_editor import VideoEditor
from subtitle_generator import SubtitleGenerator
from google_drive_uploader import GoogleDriveUploader


logger = logging.getLogger(__name__)

class VideoProcessor:
    def __init__(self):
        self.youtube_downloader = YouTubeDownloader()
        self.video_editor = VideoEditor()
        self.subtitle_generator = SubtitleGenerator()
        self.drive_uploader = GoogleDriveUploader()
        
        # Создаем рабочие директории
        self.temp_dir = Path("temp")
        self.output_dir = Path("output")
        self.temp_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
    
    async def process_youtube_video(self, url: str, config: dict) -> dict:
        """Обработка YouTube видео"""
        try:
            # 1. Скачиваем видео (автоматически использует cookies если доступны)
            logger.info(f"Скачивание YouTube видео: {url}")
            download_result = await self.youtube_downloader.download_with_cookies(url)
            
            if not download_result['success']:
                return {'success': False, 'error': download_result['error']}
            
            video_path = download_result['video_path']
            
            # 2. Обрабатываем видео
            result = await self.process_video_file(video_path, config)
            
            # 3. Удаляем скачанное видео
            if os.path.exists(video_path):
                os.remove(video_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка обработки YouTube видео: {e}")
            return {'success': False, 'error': str(e)}
    
    async def process_video_file(self, video_path: str, config: dict) -> dict:
        """Обработка видео файла"""
        try:
            duration = config.get('duration', 30)
            
            # 1. Получаем информацию о видео
            video_info = self.video_editor.get_video_info(video_path)
            total_duration = video_info['duration']
            
            logger.info(f"🎮 Обработка видео длительностью {total_duration} секунд")
            
            # 2. Если видео больше 5 минут, нарезаем на чанки
            chunks = []
            if total_duration > 300:  # 5 минут
                logger.info(f"🔪 Видео {total_duration:.1f} сек > 300 сек, нарезаем на чанки")
                chunks = await self.split_into_chunks(video_path, chunk_duration=300)
                logger.info(f"📦 Создано чанков: {len(chunks)}")
            else:
                logger.info(f"📹 Видео {total_duration:.1f} сек <= 300 сек, обрабатываем целиком")
                chunks = [video_path]
        
            # КРИТИЧЕСКАЯ ПРОВЕРКА: убеждаемся что все чанки существуют
            existing_chunks = []
            for i, chunk_path in enumerate(chunks):
                if os.path.exists(chunk_path):
                    chunk_info = self.video_editor.get_video_info(chunk_path)
                    existing_chunks.append(chunk_path)
                    logger.info(f"✅ Чанк {i+1} существует: {chunk_path} ({chunk_info['duration']:.1f} сек)")
                else:
                    logger.error(f"❌ Чанк {i+1} НЕ СУЩЕСТВУЕТ: {chunk_path}")
            
            logger.info(f"📊 ИТОГО готовых чанков: {len(existing_chunks)}/{len(chunks)}")
            chunks = existing_chunks
            
            # 3. Последовательная обработка чанков (параллельная обработка клипов внутри)
            logger.info(f"🚀 НАЧИНАЕМ ПОСЛЕДОВАТЕЛЬНУЮ обработку {len(chunks)} чанков!")
            
            all_clips = []
            total_expected_clips = 0
            
            for i, chunk_path in enumerate(chunks):
                try:
                    # Получаем информацию о чанке для расчета ожидаемых клипов
                    chunk_info = self.video_editor.get_video_info(chunk_path)
                    chunk_duration = chunk_info['duration']
                    expected_clips_in_chunk = int(chunk_duration // duration)
                    total_expected_clips += expected_clips_in_chunk
                    
                    logger.info(f"📋 Обработка чанка {i+1}/{len(chunks)}: {chunk_duration:.1f}сек, ожидается {expected_clips_in_chunk} клипов")
                    
                    # Обрабатываем чанк и ждем результат (внутри этого метода клипы создаются параллельно)
                    clips_from_chunk = await self._process_chunk_parallel(
                        chunk_path, 
                        duration, 
                        config, 
                        i, 
                        len(chunks),
                        video_path
                    )
                    
                    if isinstance(clips_from_chunk, Exception):
                        logger.error(f"❌ Ошибка обработки чанка {i+1}: {clips_from_chunk}")
                    elif clips_from_chunk and isinstance(clips_from_chunk, list):
                        all_clips.extend(clips_from_chunk)
                        logger.info(f"✅ Чанк {i+1} обработан: {len(clips_from_chunk)} клипов")
                    else:
                        logger.warning(f"⚠️ Чанк {i+1} вернул пустой или некорректный результат")

                except Exception as e:
                    logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА обработки чанка {i+1}: {e}")
                    continue
            
            # ФИНАЛЬНАЯ СТАТИСТИКА
            logger.info(f"🏁 ФИНАЛЬНАЯ СТАТИСТИКА ОБРАБОТКИ:")
            logger.info(f"   📹 Исходное видео: {total_duration:.1f} сек")
            logger.info(f"   📦 Обработано чанков: {len(chunks)}")
            logger.info(f"   🎯 Ожидалось клипов: {total_expected_clips}")
            logger.info(f"   ✅ Создано клипов: {len(all_clips)}")
            logger.info(f"   📊 Эффективность: {len(all_clips)/total_expected_clips*100:.1f}%" if total_expected_clips > 0 else "   📊 Эффективность: 0%")
            
            # 4. Ждем завершения записи всех файлов
            import time
            logger.info("Ожидание завершения записи файлов...")
            time.sleep(3)  # Даем время на завершение записи
            
            # 5. Загружаем все клипы на Google Drive
            logger.info(f"Загрузка {len(all_clips)} клипов на Google Drive")
            upload_results = await self.drive_uploader.upload_clips(all_clips)
            
            # 5. Создаем файл со ссылками
            links_file = await self.create_links_file(upload_results)
            
            # 6. Очищаем временные файлы ТОЛЬКО после успешной загрузки
            successful_uploads = sum(1 for r in upload_results if r.get('success', False))
            if successful_uploads > 0:
                logger.info(f"Успешно загружено {successful_uploads}/{len(all_clips)} клипов, очищаем файлы")
                # Удаляем только успешно загруженные файлы
                self.cleanup_successful_files(all_clips, upload_results)
            else:
                logger.warning("Ни один клип не был загружен, файлы сохранены для повторной попытки")
            
            return {
                'success': True,
                'total_clips': len(all_clips),
                'links_file': links_file,
                'upload_results': upload_results
            }
        except Exception as e:
            logger.error(f"Ошибка обработки видео: {e}")
            return {'success': False, 'error': str(e)}
    
    async def split_into_chunks(self, video_path: str, chunk_duration: int = 300) -> list:
        """МАКСИМАЛЬНО БЫСТРАЯ нарезка видео на чанки (как в вашем примере + параллельность)"""
        try:
            video_info = self.video_editor.get_video_info(video_path)
            total_duration = int(video_info['duration'])
            
            # Если видео короткое - не делим на части (как в вашем примере)
            if total_duration <= chunk_duration:
                logger.info(f"Видео {total_duration} сек <= {chunk_duration} сек, не делим на чанки")
                return [video_path]
            
            # Вычисляем количество частей (как в вашем примере)
            import math
            num_chunks = math.ceil(total_duration / chunk_duration)
            logger.info(f"Делим видео {total_duration} сек на {num_chunks} чанков по {chunk_duration} сек")
            
            # Подготавливаем все задачи для параллельной обработки
            chunk_tasks = []
            chunk_paths = []
            
            for i in range(num_chunks):
                start_time = i * chunk_duration
                actual_duration = min(chunk_duration, total_duration - start_time)
                chunk_path = self.temp_dir / f"chunk_{i}.mp4"
                
                chunk_tasks.append({
                    'input_path': video_path,
                    'output_path': str(chunk_path),
                    'start_time': start_time,
                    'duration': actual_duration,
                    'index': i
                })
                chunk_paths.append(str(chunk_path))
            
            logger.info(f"Начинаем СУПЕР БЫСТРУЮ параллельную нарезку {len(chunk_tasks)} чанков...")
            
            # ПАРАЛЛЕЛЬНО создаем все чанки с прямыми командами ffmpeg
            # Увеличиваем количество параллельных процессов для GPU (больше VRAM = больше параллелизма)
            gpu_available = self._check_gpu_support()
            if gpu_available:
                max_concurrent = min(6, len(chunk_tasks))  # Максимум 6 параллельных процессов для GPU
                logger.info(f"🚀 GPU режим: используем {max_concurrent} параллельных процессов")
            else:
                max_concurrent = min(3, len(chunk_tasks))  # Максимум 3 параллельных процесса для CPU
                logger.info(f"💻 CPU режим: используем {max_concurrent} параллельных процессов")
            
            if len(chunk_tasks) <= max_concurrent:
                # Если чанков мало, создаем все параллельно
                tasks = [
                    self._create_chunk_ultra_fast(task) 
                    for task in chunk_tasks
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # Если чанков много, создаем батчами
                logger.info(f"Создаем {len(chunk_tasks)} чанков батчами по {max_concurrent}")
                results = []
                for i in range(0, len(chunk_tasks), max_concurrent):
                    batch = chunk_tasks[i:i + max_concurrent]
                    batch_tasks = [self._create_chunk_ultra_fast(task) for task in batch]
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    results.extend(batch_results)
                    logger.info(f"Завершен батч {i//max_concurrent + 1}/{(len(chunk_tasks)-1)//max_concurrent + 1}")
            

            
            # Проверяем результаты
            successful_chunks = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка создания чанка {i}: {result}")
                elif result:
                    successful_chunks.append(chunk_paths[i])
                    logger.info(f"✅ Чанк {i+1}/{num_chunks} готов: {chunk_tasks[i]['duration']} сек")
                else:
                    logger.warning(f"❌ Не удалось создать чанк {i}")
            
            logger.info(f"🚀 СУПЕР БЫСТРО создано {len(successful_chunks)}/{num_chunks} чанков")
            
            # КРИТИЧЕСКАЯ ДИАГНОСТИКА: проверяем каждый чанк
            logger.info(f"🔍 ДИАГНОСТИКА СОЗДАННЫХ ЧАНКОВ:")
            total_chunks_duration = 0
            for i, chunk_path in enumerate(successful_chunks):
                try:
                    if os.path.exists(chunk_path):
                        chunk_info = self.video_editor.get_video_info(chunk_path)
                        chunk_duration = chunk_info['duration']
                        total_chunks_duration += chunk_duration
                        logger.info(f"   ✅ Чанк {i+1}: {chunk_duration:.1f} сек - {chunk_path}")
                    else:
                        logger.error(f"   ❌ Чанк {i+1}: ФАЙЛ НЕ СУЩЕСТВУЕТ - {chunk_path}")
                except Exception as e:
                    logger.error(f"   ❌ Чанк {i+1}: ОШИБКА ЧТЕНИЯ - {e}")
            
            logger.info(f"📊 ИТОГО длительность чанков: {total_chunks_duration:.1f} сек из {total_duration:.1f} сек")
            coverage = (total_chunks_duration / total_duration) * 100 if total_duration > 0 else 0
            logger.info(f"📈 Покрытие видео чанками: {coverage:.1f}%")
            
            if coverage < 95:
                logger.warning(f"⚠️  ПРОБЛЕМА: Чанки покрывают только {coverage:.1f}% исходного видео!")
            
            return successful_chunks
            
        except Exception as e:
            logger.error(f"Ошибка супер быстрой нарезки на чанки: {e}")
            return [video_path]  # Возвращаем оригинальный файл
    
    async def _create_chunk_ultra_fast(self, task: dict) -> bool:
        """СУПЕР БЫСТРОЕ создание чанка с таймаутом и fallback"""
        try:
            logger.info(f"🚀 Начинаем создание чанка {task['index']}: {task['start_time']}-{task['start_time'] + task['duration']} сек")
            
            loop = asyncio.get_event_loop()
            
            # Уменьшаем таймаут до 30 секунд для первой попытки
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    self._create_chunk_direct_command,
                    task['input_path'],
                    task['output_path'], 
                    task['start_time'],
                    task['duration']
                ),
                timeout=30.0  # 30 секунд таймаут для первой попытки
            )
            
            # Проверяем, что файл действительно создался
            if os.path.exists(task['output_path']):
                file_size = os.path.getsize(task['output_path'])
                logger.info(f"✅ Чанк {task['index']} создан успешно: {file_size} байт")
                return True
            else:
                logger.error(f"❌ Чанк {task['index']} НЕ СОЗДАЛСЯ: файл отсутствует")
                return False
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ Таймаут создания чанка {task['index']}, пробуем CPU fallback")
            # Пробуем CPU fallback
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        self._create_chunk_cpu_fallback,
                        task['input_path'],
                        task['output_path'], 
                        task['start_time'],
                        task['duration']
                    ),
                    timeout=120.0  # 2 минуты для CPU
                )
                logger.info(f"✅ Чанк {task['index']} создан через CPU fallback")
                return True
            except Exception as fallback_error:
                logger.error(f"❌ CPU fallback тоже не сработал для чанка {task['index']}: {fallback_error}")
                return False
                
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА создания чанка {task['index']}: {e}")
            logger.error(f"   Параметры чанка: start={task['start_time']}, duration={task['duration']}, output={task['output_path']}")
            return False
    
    def _create_chunk_direct_command(self, input_path: str, output_path: str, start_time: int, duration: int):
        """Прямая команда ffmpeg с ПОЛНЫМ GPU ускорением для максимальной скорости"""
        import subprocess
        
        # Проверяем доступность GPU и тип видео
        gpu_available = self._check_gpu_support()
        video_codec = self._get_video_codec(input_path)
        
        # Для AV1 видео используем специальную обработку
        if video_codec == 'av1':
            logger.info(f"🎬 Обнаружен AV1 кодек, используем GPU декодирование + кодирование")
            logger.info(f"   📊 Параметры чанка: start={start_time}s, duration={duration}s")
            return self._create_chunk_av1_gpu_optimized(input_path, output_path, start_time, duration)
        
        if gpu_available:
            # ПОЛНОЕ GPU ускорение: декодирование + кодирование + масштабирование
            cmd = [
                'ffmpeg',
                '-hwaccel', 'cuda',           # GPU декодирование
                '-hwaccel_output_format', 'cuda',  # Держим данные на GPU
                '-ss', str(start_time),       # Время начала (ПЕРЕД входным файлом для быстрого поиска)
                '-i', input_path,             # Входной файл
                '-t', str(duration),          # Длительность
                '-c:v', 'h264_nvenc',         # GPU кодировщик NVIDIA
                '-c:a', 'copy',               # Копируем аудио без перекодирования (быстрее)
                '-preset', 'p4',              # NVENC пресет (p1-p7, p4 = medium)
                '-rc', 'vbr',                 # Variable bitrate для NVENC
                '-cq', '23',                  # Качество для NVENC
                '-profile:v', 'main',         # Основной профиль (более совместимый)
                '-level', '4.0',              # Правильный уровень для Full HD
                '-pix_fmt', 'yuv420p',        # Формат пикселей для совместимости
                '-gpu', '0',                  # Используем первый GPU
                '-avoid_negative_ts', 'make_zero',
                '-y',                         # Перезаписывать без вопросов
                output_path
            ]
            logger.info(f"🚀 ПОЛНОЕ GPU ускорение: декодирование + кодирование ({video_codec} -> h264)")
        else:
            # Обычная CPU команда (как раньше)
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),        # Время начала
                '-i', input_path,              # Входной файл
                '-t', str(duration),           # Длительность
                '-c', 'copy',                  # Копирование без перекодирования
                '-avoid_negative_ts', 'make_zero',
                '-y',                          # Перезаписывать без вопросов
                output_path
            ]
            logger.info(f"💻 Используем CPU для нарезки чанка ({video_codec})")
        
        # Запускаем команду с правильной кодировкой для Windows
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True,
            encoding='utf-8',  # Принудительно используем UTF-8
            errors='ignore',   # Игнорируем ошибки кодировки
            check=False        # Не бросаем исключение при ошибке
        )
        
        if result.returncode != 0:
            logger.error(f"Ошибка ffmpeg: {result.stderr}")
            # Если GPU команда не сработала, пробуем CPU
            if gpu_available:
                logger.warning("ПОЛНОЕ GPU ускорение не сработало, пробуем CPU...")
                return self._create_chunk_cpu_fallback(input_path, output_path, start_time, duration)
            else:
                raise Exception(f"ffmpeg завершился с кодом {result.returncode}")
    
    def _get_video_codec(self, input_path: str) -> str:
        """Определение кодека видео"""
        try:
            probe = ffmpeg.probe(input_path)
            video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
            if video_stream:
                codec = video_stream.get('codec_name', 'unknown')
                logger.info(f"🎬 Обнаружен видео кодек: {codec}")
                return codec
            return 'unknown'
        except Exception as e:
            logger.warning(f"Ошибка определения кодека: {e}")
            return 'unknown'
    
    def _create_chunk_av1_optimized(self, input_path: str, output_path: str, start_time: int, duration: int):
        """Оптимизированная обработка AV1 видео - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        import subprocess
        
        logger.info(f"🎬 Специальная обработка AV1 видео (ИСПРАВЛЕННАЯ)")
        
        # Для AV1 видео лучше использовать stream copy без перекодирования
        # Это намного быстрее и избегает проблем с GPU декодированием AV1
        
        # Сначала пробуем простое копирование без перекодирования
        cmd_copy = [
            'ffmpeg',
            '-ss', str(start_time),       # Время начала
            '-i', input_path,             # Входной файл
            '-t', str(duration),          # Длительность
            '-c', 'copy',                 # Копируем все потоки без перекодирования
            '-avoid_negative_ts', 'make_zero',
            '-y',                         # Перезаписывать без вопросов
            output_path
        ]
        
        logger.info(f"🚀 Пробуем быстрое копирование AV1 без перекодирования")
        
        result = subprocess.run(
            cmd_copy, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='ignore',
            timeout=30,  # Короткий таймаут для копирования
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"✅ AV1 видео успешно скопировано без перекодирования")
            return
        
        # Если копирование не сработало, пробуем CPU перекодирование
        logger.warning(f"Копирование не сработало, пробуем CPU перекодирование...")
        logger.warning(f"Ошибка копирования: {result.stderr[:200]}...")
        
        # CPU перекодирование с оптимизированными параметрами для AV1
        cmd_cpu = [
            'ffmpeg',
            '-ss', str(start_time),       # Время начала
            '-i', input_path,             # Входной файл
            '-t', str(duration),          # Длительность
            '-c:v', 'libx264',            # CPU кодировщик
            '-c:a', 'copy',               # Копируем аудио
            '-preset', 'ultrafast',       # Самый быстрый пресет для AV1
            '-crf', '28',                 # Более высокое сжатие для скорости
            '-profile:v', 'baseline',     # Базовый профиль для совместимости
            '-level', '3.1',              # Более низкий уровень для скорости
            '-pix_fmt', 'yuv420p',        # Формат пикселей
            '-threads', '4',              # Ограничиваем потоки для стабильности
            '-avoid_negative_ts', 'make_zero',
            '-y',                         # Перезаписывать без вопросов
            output_path
        ]
        
        logger.info(f"💻 Используем быстрое CPU перекодирование AV1 -> H.264")
        
        result = subprocess.run(
            cmd_cpu, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='ignore',
            timeout=90,  # 90 секунд для CPU перекодирования
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Ошибка CPU обработки AV1: {result.stderr[:300]}...")
            raise Exception(f"AV1 CPU обработка завершилась с кодом {result.returncode}")
        
        logger.info(f"✅ AV1 видео успешно обработано через CPU (AV1 -> H.264)")
    
    def _create_chunk_av1_gpu_optimized(self, input_path: str, output_path: str, start_time: int, duration: int):
        """GPU оптимизированная обработка AV1 видео"""
        import subprocess
        
        logger.info(f"🚀 GPU обработка AV1 видео")
        
        # Пробуем GPU декодирование AV1 + GPU кодирование H.264
        cmd_gpu = [
            'ffmpeg',
            '-hwaccel', 'cuda',           # GPU декодирование
            '-hwaccel_output_format', 'cuda',  # Держим данные на GPU
            '-ss', str(start_time),       # Время начала
            '-i', input_path,             # Входной файл
            '-t', str(duration),          # Длительность
            '-c:v', 'h264_nvenc',         # GPU кодировщик NVIDIA
            '-c:a', 'copy',               # Копируем аудио
            '-preset', 'p2',              # Быстрый NVENC пресет для AV1
            '-rc', 'vbr',                 # Variable bitrate
            '-cq', '25',                  # Немного выше качество для AV1
            '-profile:v', 'main',         # Основной профиль
            '-level', '4.0',              # Уровень
            '-pix_fmt', 'yuv420p',        # Формат пикселей
            '-gpu', '0',                  # Первый GPU
            '-avoid_negative_ts', 'make_zero',
            '-y',                         # Перезаписывать без вопросов
            output_path
        ]
        
        logger.info(f"🎮 Пробуем ПОЛНОЕ GPU ускорение для AV1 (декодирование + кодирование)")
        
        result = subprocess.run(
            cmd_gpu, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='ignore',
            timeout=60,  # 60 секунд для GPU AV1
            check=False
        )
        
        if result.returncode == 0:
            logger.info(f"✅ AV1 видео успешно обработано через ПОЛНОЕ GPU ускорение")
            return
        
        # Если GPU не сработал, fallback на обычную AV1 обработку
        logger.warning(f"GPU AV1 обработка не сработала, используем CPU fallback...")
        logger.warning(f"Ошибка GPU: {result.stderr[:200]}...")
        
        return self._create_chunk_av1_optimized(input_path, output_path, start_time, duration)

    def _check_gpu_support(self) -> bool:
        """Детальная проверка поддержки GPU для ffmpeg"""
        try:
            import subprocess
            
            logger.info("🔍 ДЕТАЛЬНАЯ ПРОВЕРКА GPU ПОДДЕРЖКИ:")
            
            # 1. Проверяем наличие NVIDIA GPU
            logger.info("   1️⃣ Проверяем nvidia-smi...")
            result = subprocess.run(
                ['nvidia-smi'], 
                capture_output=True, 
                text=True, 
                encoding='utf-8',
                errors='ignore',
                check=False
            )
            if result.returncode != 0:
                logger.warning("   ❌ nvidia-smi недоступен")
                return False
            else:
                # Извлекаем информацию о GPU
                gpu_info = result.stdout
                if "Tesla T4" in gpu_info:
                    logger.info("   ✅ Обнаружен Tesla T4 GPU")
                elif "GeForce" in gpu_info:
                    logger.info("   ✅ Обнаружен GeForce GPU")
                else:
                    logger.info("   ✅ Обнаружен NVIDIA GPU")
            
            # 2. Проверяем поддержку NVENC в ffmpeg
            logger.info("   2️⃣ Проверяем поддержку NVENC в ffmpeg...")
            result = subprocess.run(
                ['ffmpeg', '-encoders'], 
                capture_output=True, 
                text=True,
                encoding='utf-8',
                errors='ignore',
                check=False
            )
            if 'h264_nvenc' not in result.stdout:
                logger.warning("   ❌ h264_nvenc кодировщик недоступен в ffmpeg")
                return False
            else:
                logger.info("   ✅ h264_nvenc кодировщик доступен")
            
            # 3. Тестируем реальное кодирование (быстрый тест)
            logger.info("   3️⃣ Тестируем реальное GPU кодирование...")
            test_result = self._test_gpu_encoding()
            if test_result:
                logger.info("   ✅ GPU кодирование работает!")
                logger.info("🎮 ИТОГ: GPU поддержка ПОЛНОСТЬЮ ДОСТУПНА")
                return True
            else:
                logger.warning("   ❌ GPU кодирование не работает")
                logger.warning("💻 ИТОГ: Используем CPU fallback")
                return False
                
        except Exception as e:
            logger.warning(f"Ошибка проверки GPU: {e}")
            return False
    
    def _test_gpu_encoding(self) -> bool:
        """Быстрый тест GPU кодирования"""
        try:
            import subprocess
            import tempfile
            import os
            
            # Создаем тестовое видео 1 секунда
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_output = temp_file.name
            
            try:
                # Тестовая команда GPU кодирования
                cmd = [
                    'ffmpeg',
                    '-f', 'lavfi',
                    '-i', 'testsrc=duration=1:size=320x240:rate=30',
                    '-c:v', 'h264_nvenc',
                    '-preset', 'fast',
                    '-cq', '23',
                    '-profile:v', 'main',
                    '-level', '4.0',
                    '-pix_fmt', 'yuv420p',
                    '-y',
                    temp_output
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=10,  # 10 секунд максимум
                    check=False
                )
                
                success = result.returncode == 0 and os.path.exists(temp_output)
                if not success and result.stderr:
                    logger.warning(f"   GPU тест не прошел: {result.stderr[:200]}...")
                
                return success
                
            finally:
                # Удаляем тестовый файл
                if os.path.exists(temp_output):
                    os.unlink(temp_output)
                    
        except Exception as e:
            logger.warning(f"   Ошибка GPU теста: {e}")
            return False
    
    def _create_chunk_cpu_fallback(self, input_path: str, output_path: str, start_time: int, duration: int):
        """Резервная CPU команда если GPU не работает - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        import subprocess
        
        # CPU команда с разумными параметрами
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),       # Время начала
            '-i', input_path,             # Входной файл
            '-t', str(duration),          # Длительность
            '-c:v', 'libx264',            # CPU кодировщик x264
            '-c:a', 'copy',               # Копируем аудио без перекодирования
            '-preset', 'fast',            # Быстрый пресет для нарезки
            '-crf', '23',                 # Разумное качество для нарезки
            '-profile:v', 'main',         # Основной профиль (более совместимый)
            '-level', '4.0',              # Правильный уровень для Full HD
            '-pix_fmt', 'yuv420p',        # Формат пикселей для совместимости
            '-avoid_negative_ts', 'make_zero',
            '-y',                         # Перезаписывать без вопросов
            output_path
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='ignore',
            check=False
        )
        
        if result.returncode != 0:
            logger.error(f"Ошибка CPU fallback: {result.stderr}")
            raise Exception(f"CPU fallback завершился с кодом {result.returncode}")
    
    async def _create_chunk_fast(self, task: dict) -> bool:
        """Быстрое создание одного чанка (старый метод через python-ffmpeg)"""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self._create_chunk_sync_fast,
                task['input_path'],
                task['output_path'], 
                task['start_time'],
                task['duration']
            )
            return True
        except Exception as e:
            logger.error(f"Ошибка создания чанка {task['index']}: {e}")
            return False

    async def process_chunk_logic(self, chunk_path: str, duration: int, config: dict, start_index: int) -> list:
        """Основная логика обработки одного чанка: генерация субтитров и создание клипов."""
        try:
            # 1. Генерируем субтитры для чанка
            logger.info(f"   🎤 Генерируем субтитры для {chunk_path}...")
            subtitles = await self.subtitle_generator.generate(chunk_path)
            logger.info(f"   ✅ Субтитры для {chunk_path} готовы: {len(subtitles)} фраз")

            # 2. Нарезаем чанк на клипы
            logger.info(f"   ✂️  Нарезаем на клипы из {chunk_path}...")
            clips = await self.video_editor.create_clips_parallel(
                chunk_path,
                duration,
                subtitles,
                start_index=start_index,
                config=config,
                max_parallel=10  # Увеличиваем нагрузку на GPU
            )
            logger.info(f"   🎉 Из {chunk_path} создано {len(clips)} клипов")
            return clips
        except Exception as e:
            logger.error(f"❌ Ошибка в process_chunk_logic для {chunk_path}: {e}")
            return []

    async def _process_chunk_parallel(self, chunk_path: str, duration: int, config: dict,
                                     chunk_index: int, total_chunks: int, original_video_path: str) -> list:
        """Параллельная обработка одного чанка с использованием новой логики."""
        try:
            logger.info(f"🎬 ПАРАЛЛЕЛЬНО обрабатываем чанк {chunk_index+1}/{total_chunks}: {chunk_path}")

            # Вычисляем стартовый индекс для этого чанка
            start_index = chunk_index * int(300 // duration)

            # Вызываем основную логику обработки
            clips = await self.process_chunk_logic(chunk_path, duration, config, start_index)

            # Удаляем временный чанк (если это не оригинальный файл)
            if chunk_path != original_video_path and os.path.exists(chunk_path):
                os.remove(chunk_path)
                logger.info(f"   🗑️  Удален временный чанк: {chunk_path}")

            return clips

        except Exception as e:
            logger.error(f"❌ ОШИБКА параллельной обработки чанка {chunk_index+1}: {e}")
            return []

    
    def _create_chunk_sync_fast(self, input_path: str, output_path: str, start_time: float, duration: float):
        """Синхронное быстрое создание чанка с максимальной оптимизацией"""
        # МАКСИМАЛЬНО БЫСТРАЯ нарезка с stream copy
        (
            ffmpeg
            .input(input_path, 
                   ss=start_time,           # Точное время начала
                   t=duration,              # Длительность
                   copyts=True)             # Сохраняем временные метки
            .output(output_path, 
                   vcodec='copy',           # Копируем видео (без перекодирования)
                   acodec='copy',           # Копируем аудио (без перекодирования)
                   avoid_negative_ts='make_zero',  # Избегаем проблем с таймингом
                   map_metadata=0,          # Копируем метаданные
                   movflags='faststart')    # Оптимизация для быстрого старта
            .overwrite_output()
            .run(quiet=True, capture_stdout=True, capture_stderr=True)
        )
    
    async def create_links_file(self, upload_results: list) -> str:
        """Создание файла со ссылками на скачивание"""
        try:
            links_file = self.output_dir / "video_links.txt"
            
            with open(links_file, 'w', encoding='utf-8') as f:
                f.write("🎬 ССЫЛКИ НА СКАЧИВАНИЕ ШОТСОВ\n")
                f.write("=" * 50 + "\n\n")
                
                for i, result in enumerate(upload_results, 1):
                    if result['success']:
                        f.write(f"Фрагмент {i:03d}: {result['download_url']}\n")
                
                f.write(f"\n📊 Всего создано: {len(upload_results)} шотсов\n")
                f.write(f"✅ Успешно загружено: {sum(1 for r in upload_results if r['success'])}\n")
            
            return str(links_file)
            
        except Exception as e:
            logger.error(f"Ошибка создания файла ссылок: {e}")
            return None
    
    def cleanup_successful_files(self, clip_paths: list, upload_results: list):
        """Очистка только успешно загруженных файлов"""
        try:
            import time
            import gc
            
            # Принудительная сборка мусора для освобождения файловых дескрипторов
            gc.collect()
            
            # Небольшая задержка для завершения всех операций с файлами
            time.sleep(2)  # Увеличиваем задержку
            
            # Удаляем только файлы, которые успешно загрузились
            for i, clip_path in enumerate(clip_paths):
                try:
                    # Проверяем, был ли этот клип успешно загружен
                    if i < len(upload_results) and upload_results[i].get('success', False):
                        if os.path.exists(clip_path):
                            # Пытаемся удалить файл несколько раз
                            for attempt in range(5):  # Больше попыток
                                try:
                                    os.remove(clip_path)
                                    logger.info(f"Удален успешно загруженный файл: {clip_path}")
                                    break
                                except PermissionError:
                                    if attempt < 4:
                                        time.sleep(1)  # Больше времени между попытками
                                        continue
                                    else:
                                        logger.warning(f"Не удалось удалить файл {clip_path} - файл занят, оставляем для ручного удаления")
                    else:
                        logger.info(f"Файл {clip_path} не был загружен, сохраняем для повторной попытки")
                        
                except Exception as e:
                    logger.warning(f"Ошибка удаления файла {clip_path}: {e}")
            
            # Очищаем временную директорию от вспомогательных файлов
            for file in self.temp_dir.glob("*"):
                try:
                    if file.is_file() and not file.name.startswith('clip_'):
                        file.unlink()
                except Exception as e:
                    logger.warning(f"Ошибка удаления временного файла {file}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка очистки успешно загруженных файлов: {e}")

    def cleanup_temp_files(self, clip_paths: list):
        """Очистка всех временных файлов (используется при ошибках)"""
        try:
            import time
            import gc
            
            # Принудительная сборка мусора для освобождения файловых дескрипторов
            gc.collect()
            
            # Небольшая задержка для завершения всех операций с файлами
            time.sleep(1)
            
            for clip_path in clip_paths:
                try:
                    if os.path.exists(clip_path):
                        # Пытаемся удалить файл несколько раз
                        for attempt in range(3):
                            try:
                                os.remove(clip_path)
                                break
                            except PermissionError:
                                if attempt < 2:
                                    time.sleep(0.5)
                                    continue
                                else:
                                    logger.warning(f"Не удалось удалить файл {clip_path} - файл занят")
                except Exception as e:
                    logger.warning(f"Ошибка удаления файла {clip_path}: {e}")
            
            # Очищаем временную директорию
            for file in self.temp_dir.glob("*"):
                try:
                    if file.is_file():
                        file.unlink()
                except Exception as e:
                    logger.warning(f"Ошибка удаления временного файла {file}: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка очистки временных файлов: {e}")