import os
import asyncio
import logging
import pickle
import base64
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class GoogleDriveUploader:
    def __init__(self):
        self.service = None
        self.folder_id = None
        
    def _get_credentials(self):
        """Получение учетных данных Google"""
        try:
            # Получаем токен из переменной окружения
            token_base64 = os.getenv('GOOGLE_OAUTH_TOKEN_BASE64')
            if not token_base64:
                raise ValueError("GOOGLE_OAUTH_TOKEN_BASE64 не найден в переменных окружения")
            
            # Декодируем токен
            token_data = base64.b64decode(token_base64)
            credentials = pickle.loads(token_data)
            
            # Обновляем токен если нужно
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            
            return credentials
            
        except Exception as e:
            logger.error(f"Ошибка получения учетных данных: {e}")
            raise
    
    def _init_service(self):
        """Инициализация сервиса Google Drive"""
        if self.service is None:
            credentials = self._get_credentials()
            
            # Обновляем токен если нужно
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            
            # Создаем сервис напрямую с credentials (новый API)
            self.service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    
    async def upload_clips(self, clip_paths: list) -> list:
        """Загрузка всех клипов на Google Drive"""
        try:
            self._init_service()
            
            # Создаем папку для клипов
            folder_name = f"Video_Clips_{len(clip_paths)}_clips"
            self.folder_id = await self._create_folder(folder_name)
            
            # Загружаем клипы последовательно для избежания SSL проблем
            semaphore = asyncio.Semaphore(1)  # Только 1 одновременная загрузка
            
            tasks = []
            for i, clip_path in enumerate(clip_paths):
                task = self._upload_single_clip(semaphore, clip_path, i + 1)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            upload_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Ошибка загрузки клипа {i+1}: {result}")
                    upload_results.append({
                        'success': False,
                        'error': str(result),
                        'clip_number': i + 1
                    })
                else:
                    upload_results.append(result)
            
            logger.info(f"Загружено {sum(1 for r in upload_results if r['success'])}/{len(clip_paths)} клипов")
            return upload_results
            
        except Exception as e:
            logger.error(f"Ошибка загрузки клипов: {e}")
            return [{'success': False, 'error': str(e)} for _ in clip_paths]
    
    async def _upload_single_clip(self, semaphore: asyncio.Semaphore, clip_path: str, clip_number: int) -> dict:
        """Загрузка одного клипа"""
        async with semaphore:
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self._upload_clip_sync,
                    clip_path, clip_number
                )
                return result
                
            except Exception as e:
                logger.error(f"Ошибка загрузки клипа {clip_number}: {e}")
                return {
                    'success': False,
                    'error': str(e),
                    'clip_number': clip_number
                }
    
    def _upload_clip_sync(self, clip_path: str, clip_number: int) -> dict:
        """Синхронная загрузка клипа с повторными попытками"""
        import time
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                file_name = f"clip_{clip_number:03d}.mp4"
                
                # Метаданные файла
                file_metadata = {
                    'name': file_name,
                    'parents': [self.folder_id] if self.folder_id else []
                }
                
                # Загружаем файл
                media = MediaFileUpload(clip_path, mimetype='video/mp4', resumable=True)
                
                file = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,name,webViewLink'
                ).execute()
                
                file_id = file.get('id')
                
                # Делаем файл общедоступным
                self.service.permissions().create(
                    fileId=file_id,
                    body={'role': 'reader', 'type': 'anyone'}
                ).execute()
                
                # Получаем прямую ссылку на скачивание
                download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                view_url = file.get('webViewLink')
                
                logger.info(f"Загружен клип {clip_number}: {file_name}")
                
                return {
                    'success': True,
                    'file_id': file_id,
                    'file_name': file_name,
                    'download_url': download_url,
                    'view_url': view_url,
                    'clip_number': clip_number
                }
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2, 4, 6 секунд
                    logger.warning(f"Попытка {attempt + 1} загрузки клипа {clip_number} неудачна: {e}. Повтор через {wait_time} сек...")
                    time.sleep(wait_time)
                    
                    # Переинициализируем сервис при SSL ошибках
                    if "SSL" in str(e) or "WRONG_VERSION_NUMBER" in str(e):
                        logger.info(f"SSL ошибка, переинициализируем сервис для клипа {clip_number}")
                        self.service = None
                        self._init_service()
                else:
                    logger.error(f"Все попытки загрузки клипа {clip_number} исчерпаны: {e}")
                    raise
    
    async def _create_folder(self, folder_name: str) -> str:
        """Создание папки на Google Drive"""
        try:
            loop = asyncio.get_event_loop()
            folder_id = await loop.run_in_executor(
                None,
                self._create_folder_sync,
                folder_name
            )
            return folder_id
            
        except Exception as e:
            logger.error(f"Ошибка создания папки: {e}")
            return None
    
    def _create_folder_sync(self, folder_name: str) -> str:
        """Синхронное создание папки"""
        try:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            
            folder = self.service.files().create(
                body=folder_metadata,
                fields='id'
            ).execute()
            
            folder_id = folder.get('id')
            logger.info(f"Создана папка: {folder_name} (ID: {folder_id})")
            
            return folder_id
            
        except Exception as e:
            logger.error(f"Ошибка синхронного создания папки: {e}")
            raise
    
    def get_folder_link(self) -> str:
        """Получение ссылки на папку"""
        if self.folder_id:
            return f"https://drive.google.com/drive/folders/{self.folder_id}"
        return None