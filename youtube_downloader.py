import os
import asyncio
import logging
import yt_dlp
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    """
    Универсальный загрузчик видео с поддержкой множества платформ через yt-dlp.
    """
    def __init__(self):
        self.temp_dir = Path("temp")
        self.temp_dir.mkdir(exist_ok=True)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.google.com/',
            'DNT': '1',
            'Upgrade-Insecure-Requests': '1',
        }

    async def download_with_cookies(self, url: str, cookies_file: str = 'cookies.txt') -> dict:
        """Скачивание с использованием cookies для различных платформ."""
        use_cookies = False
        if os.path.exists(cookies_file):
            try:
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content and content != '# No cookies':
                        logger.info(f"Найден файл cookies: {cookies_file}")
                        use_cookies = True
            except Exception as e:
                logger.error(f"Ошибка чтения файла cookies: {e}")

        return await self.download(url, use_cookies=use_cookies)

    async def download(self, url: str, use_cookies: bool = False) -> dict:
        """
        Основной метод скачивания видео.
        """
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._download_video, 
                url, 
                use_cookies
            )
            return result
        except Exception as e:
            logger.error(f"Критическая ошибка в процессе скачивания: {e}")
            return {'success': False, 'error': str(e)}

    def _download_video(self, url: str, use_cookies: bool) -> dict:
        """Синхронный метод, выполняемый в отдельном потоке."""
        base_opts = {
            'noplaylist': True,
            'http_headers': self.headers,
            'retries': 5,
            'fragment_retries': 5,
            'skip_unavailable_fragments': True,
        }

        if use_cookies:
            base_opts['cookiefile'] = 'cookies.txt'

        try:
            with yt_dlp.YoutubeDL(base_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'video')
                safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()[:50]
                duration = info.get('duration', 0)

                logger.info(f"Начинаем скачивание: {title} ({duration} сек)")

                # Логика выбора форматов
                video_format = 'bestvideo[ext=mp4]/bestvideo'
                audio_format = 'bestaudio[ext=m4a]/bestaudio'

                video_opts = base_opts.copy()
                video_temp_path = self.temp_dir / f"{safe_title}_video.mp4"
                video_opts.update({
                    'format': video_format,
                    'outtmpl': str(video_temp_path),
                })

                audio_opts = base_opts.copy()
                audio_temp_path = self.temp_dir / f"{safe_title}_audio.m4a"
                audio_opts.update({
                    'format': audio_format,
                    'outtmpl': str(audio_temp_path),
                })

                # Скачиваем видео и аудио
                logger.info("Скачивание видео дорожки...")
                with yt_dlp.YoutubeDL(video_opts) as ydl_video:
                    ydl_video.download([url])

                logger.info("Скачивание аудио дорожки...")
                with yt_dlp.YoutubeDL(audio_opts) as ydl_audio:
                    ydl_audio.download([url])

                # Объединение
                final_output_path = self.temp_dir / f"{safe_title}.mp4"
                self._merge_files(str(video_temp_path), str(audio_temp_path), str(final_output_path))

                # Очистка
                if os.path.exists(video_temp_path): os.remove(video_temp_path)
                if os.path.exists(audio_temp_path): os.remove(audio_temp_path)

                return {
                    'success': True,
                    'video_path': str(final_output_path),
                    'title': title,
                    'duration': duration
                }

        except Exception as e:
            logger.error(f"Ошибка при скачивании и обработке: {e}")
            return {'success': False, 'error': str(e)}

    def _merge_files(self, video_path: str, audio_path: str, output_path: str):
        """Объединяет видео и аудио с помощью FFmpeg."""
        logger.info(f"Объединение {video_path} и {audio_path} в {output_path}")
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-shortest',
            output_path
        ]
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Ошибка FFmpeg при объединении: {result.stderr}")
            raise Exception(f"FFmpeg error: {result.stderr}")
        logger.info("Файлы успешно объединены.")
