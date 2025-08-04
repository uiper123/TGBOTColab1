import os
import asyncio
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

class SubtitleGenerator:
    def __init__(self):
        # Загружаем легкую модель Whisper
        self.model = None
        self.model_name = "base"  # Можно использовать "tiny" для еще большей скорости
        self.whisper_available = False
        self._check_whisper()
    
    def _check_whisper(self):
        """Проверка доступности Whisper"""
        try:
            import whisper
            # Проверяем, есть ли функция load_model
            if hasattr(whisper, 'load_model'):
                self.whisper = whisper
                self.whisper_available = True
                logger.info("✅ OpenAI Whisper доступен")
            else:
                logger.error("❌ OpenAI Whisper установлен, но load_model недоступен")
                self._try_alternative_whisper()
        except ImportError:
            logger.error("❌ OpenAI Whisper не установлен")
            self._try_alternative_whisper()
    
    def _try_alternative_whisper(self):
        """Попытка использовать альтернативные версии Whisper"""
        try:
            # Пробуем faster-whisper
            import faster_whisper
            self.whisper = faster_whisper
            self.whisper_available = True
            self.use_faster_whisper = True
            logger.info("✅ Используем faster-whisper как альтернативу")
        except ImportError:
            try:
                # Пробуем whisper-jax
                import whisper_jax
                self.whisper = whisper_jax
                self.whisper_available = True
                self.use_whisper_jax = True
                logger.info("✅ Используем whisper-jax как альтернативу")
            except ImportError:
                logger.error("❌ Ни одна версия Whisper не доступна")
                self.whisper_available = False
    
    def _load_model(self):
        """Ленивая загрузка модели с проверкой доступности и GPU"""
        if not self.whisper_available:
            logger.error("Whisper недоступен, субтитры не будут созданы")
            return False
            
        if self.model is None:
            try:
                # Проверяем доступность GPU
                gpu_available = self._check_gpu_support()
                
                logger.info(f"Загрузка модели Whisper: {self.model_name}")
                
                if hasattr(self, 'use_faster_whisper'):
                    # Используем faster-whisper с GPU поддержкой
                    from faster_whisper import WhisperModel
                    if gpu_available:
                        self.model = WhisperModel(self.model_name, device="cuda", compute_type="float16")
                        logger.info("🎮 faster-whisper загружен с GPU ускорением")
                    else:
                        self.model = WhisperModel(self.model_name, device="cpu")
                        logger.info("💻 faster-whisper загружен на CPU")
                elif hasattr(self, 'use_whisper_jax'):
                    # Используем whisper-jax (автоматически использует GPU если доступен)
                    self.model = self.whisper.load_model(self.model_name)
                    logger.info("🎮 whisper-jax загружен (автоматическое GPU)")
                else:
                    # Используем обычный OpenAI Whisper
                    import torch
                    if gpu_available and torch.cuda.is_available():
                        self.model = self.whisper.load_model(self.model_name, device="cuda")
                        logger.info("🎮 OpenAI Whisper загружен с GPU ускорением")
                    else:
                        self.model = self.whisper.load_model(self.model_name, device="cpu")
                        logger.info("💻 OpenAI Whisper загружен на CPU")
                    
                logger.info("✅ Модель Whisper загружена успешно")
                return True
                
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки модели Whisper: {e}")
                self.whisper_available = False
                return False
        
        return True
    
    def _check_gpu_support(self) -> bool:
        """Более надежная проверка поддержки GPU для Whisper."""
        try:
            # 1. Проверяем наличие NVIDIA GPU с помощью nvidia-smi
            import subprocess
            try:
                subprocess.check_output(['nvidia-smi'])
                logger.info("✅ Обнаружен NVIDIA GPU.")
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.info("NVIDIA GPU не найден, используется CPU.")
                return False

            # 2. Проверяем, доступен ли PyTorch с CUDA
            import torch
            if torch.cuda.is_available():
                logger.info(f"✅ PyTorch CUDA доступен: {torch.cuda.get_device_name(0)}")
                return True
            else:
                logger.info("❌ PyTorch CUDA недоступен, используется CPU.")
                return False

        except ImportError:
            logger.info("PyTorch не установлен, используется CPU.")
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке GPU: {e}")
            return False
    
    async def generate(self, video_path: str) -> list:
        """Генерация субтитров для видео"""
        try:
            loop = asyncio.get_event_loop()
            subtitles = await loop.run_in_executor(
                None,
                self._generate_sync,
                video_path
            )
            return subtitles
            
        except Exception as e:
            logger.error(f"Ошибка генерации субтитров: {e}")
            return []
    
    def _generate_sync(self, video_path: str) -> list:
        """Синхронная генерация субтитров"""
        try:
            # Проверяем, удалось ли загрузить модель
            if not self._load_model():
                logger.warning("Модель Whisper недоступна, возвращаем пустые субтитры")
                return []
            
            logger.info(f"Генерация субтитров для: {video_path}")
            
            # Разные способы транскрипции в зависимости от типа Whisper
            if hasattr(self, 'use_faster_whisper'):
                # faster-whisper имеет другой API
                segments, info = self.model.transcribe(
                    video_path,
                    language='ru',
                    word_timestamps=True
                )
                # Конвертируем в формат OpenAI Whisper
                result = {'segments': []}
                for segment in segments:
                    result['segments'].append({
                        'start': segment.start,
                        'end': segment.end,
                        'text': segment.text,
                        'words': [{'word': word.word, 'start': word.start, 'end': word.end} 
                                 for word in segment.words] if hasattr(segment, 'words') else []
                    })
            else:
                # Обычный OpenAI Whisper или whisper-jax
                result = self.model.transcribe(
                    video_path,
                    language='ru',  # Русский язык
                    word_timestamps=True,  # Временные метки для слов
                    verbose=False
                )
            
            # Сначала пробуем получить субтитры по словам из сегментов
            word_subtitles = []
            for segment in result['segments']:
                if 'words' in segment and segment['words']:
                    # Если в сегменте есть слова с временными метками
                    for word_info in segment['words']:
                        word = word_info.get('word', '').strip()
                        start = word_info.get('start', segment['start'])
                        end = word_info.get('end', segment['end'])
                        
                        if word:
                            word_subtitles.append({
                                'start': start,
                                'end': end,
                                'text': word
                            })
                else:
                    # Если нет детальных слов, разбиваем текст сегмента на слова
                    words = segment['text'].strip().split()
                    if words:
                        segment_duration = segment['end'] - segment['start']
                        word_duration = segment_duration / len(words)
                        
                        for i, word in enumerate(words):
                            start = segment['start'] + (i * word_duration)
                            end = start + word_duration
                            
                            word_subtitles.append({
                                'start': start,
                                'end': end,
                                'text': word
                            })
            
            if word_subtitles:
                logger.info(f"Создано {len(word_subtitles)} субтитров по словам")
                return word_subtitles
            
            # Если не удалось получить слова, используем сегменты
            subtitles = []
            for segment in result['segments']:
                subtitle = {
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                }
                subtitles.append(subtitle)
            
            logger.info(f"Создано {len(subtitles)} субтитров по сегментам")
            return subtitles
            
        except Exception as e:
            logger.error(f"Ошибка синхронной генерации субтитров: {e}")
            return []
    
    def _create_word_subtitles(self, words: list) -> list:
        """Создание субтитров по одному слову для лучшей анимации"""
        try:
            subtitles = []
            
            for word_info in words:
                word = word_info.get('word', '').strip()
                start = word_info.get('start', 0)
                end = word_info.get('end', 0)
                
                if not word:
                    continue
                
                # Создаем субтитр для каждого слова отдельно
                subtitle = {
                    'start': start,
                    'end': end,
                    'text': word
                }
                subtitles.append(subtitle)
            
            return subtitles
            
        except Exception as e:
            logger.error(f"Ошибка создания субтитров по словам: {e}")
            return []
    
    def save_srt(self, subtitles: list, output_path: str):
        """Сохранение субтитров в формате SRT"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, sub in enumerate(subtitles, 1):
                    start_time = self._seconds_to_srt_time(sub['start'])
                    end_time = self._seconds_to_srt_time(sub['end'])
                    
                    f.write(f"{i}\n")
                    f.write(f"{start_time} --> {end_time}\n")
                    f.write(f"{sub['text']}\n\n")
            
            logger.info(f"Субтитры сохранены: {output_path}")
            
        except Exception as e:
            logger.error(f"Ошибка сохранения SRT: {e}")
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Конвертация секунд в формат времени SRT"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"