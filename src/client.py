import aiohttp
import logging
import zipfile
import io
import json

logger = logging.getLogger(__name__)


class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self._session = None
        self._auth_data = None      # данные авторизованного пользователя
        self._credentials = None     # {'username': ..., 'password': ...}

    async def _get_session(self):
        if self._session is None or self._session.closed:
            # Используем cookie-сессию для поддержки Flask-авторизации
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(),
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # Телефон (не описан в API-документации, оставлен для обратной совместимости)
    # ------------------------------------------------------------------
    async def check_phone_registered(self, phone):
        try:
            session = await self._get_session()
            url = f"{self.base_url}/users/check_phone"
            async with session.get(url, params={"phone": phone}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('is_registered', False)
                return False
        except Exception as e:
            logger.error("check_phone error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Авторизация  POST /api/v1/auth/login
    # ------------------------------------------------------------------
    async def auth_user(self, username, password):
        """Возвращает (успех, данные_пользователя). Сохраняет учётные данные."""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/auth/login"
            async with session.post(url, json={
                "username": username,
                "password": password,
            }) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success'):
                        self._auth_data = {
                            'user_id': data.get('user_id'),
                            'username': data.get('username'),
                        }
                        self._credentials = {'username': username, 'password': password}
                        return True, self._auth_data
                return False, None
        except Exception as e:
            logger.error("auth_user error: %s", e)
            return False, None

    async def _ensure_auth(self):
        """Гарантирует наличие аутентифицированной сессии перед запросами,
        требующими @login_required. Возвращает True если сессия активна."""
        if self._credentials is None:
            return False
        if self._auth_data is not None:
            return True  # сессия уже активна
        ok, _ = await self.auth_user(
            self._credentials['username'],
            self._credentials['password']
        )
        return ok

    @property
    def is_authenticated(self):
        return self._auth_data is not None

    # ------------------------------------------------------------------
    # Посты  GET /api/v1/posts/<id>/metadata + GET /api/v1/posts/<id>/export
    # ------------------------------------------------------------------
    async def get_post(self, post_id):
        """Возвращает метаданные поста + его содержимое (из zip-архива)."""
        try:
            session = await self._get_session()

            # 1. Метаданные (документированный эндпоинт)
            meta_url = f"{self.base_url}/api/v1/posts/{post_id}/metadata"
            async with session.get(meta_url) as meta_resp:
                if meta_resp.status != 200:
                    return {"id": post_id, "error": f"HTTP {meta_resp.status}"}
                meta = await meta_resp.json()

            # 2. Контент через экспорт (zip-архив)
            export_url = f"{self.base_url}/api/v1/posts/{post_id}/export"
            async with session.get(export_url) as export_resp:
                if export_resp.status != 200:
                    meta['content'] = f'(контент недоступен: HTTP {export_resp.status})'
                    return meta
                zip_data = await export_resp.read()

            # 3. Извлекаем post.md из архива
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                for name in zf.namelist():
                    if name.endswith('post.md'):
                        meta['content'] = zf.read(name).decode('utf-8')
                        return meta
                meta['content'] = '(post.md не найден в архиве)'
                return meta

        except Exception as e:
            logger.error("get_post error: %s", e)
            return {"id": post_id, "error": str(e)}

    # ------------------------------------------------------------------
    # Комментарии  GET /api/v1/posts/<id>/comments
    # ------------------------------------------------------------------
    async def get_comments(self, post_id):
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/posts/{post_id}/comments"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('comments', [])
                return []
        except Exception as e:
            logger.error("get_comments error: %s", e)
            return []

    # ------------------------------------------------------------------
    # Добавить комментарий  POST /api/v1/posts/<id>/comments
    #   тело: {"content": "текст"}
    #   автор определяется сервером по сессии
    # ------------------------------------------------------------------
    async def add_comment(self, post_id, text):
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/posts/{post_id}/comments"
            async with session.post(url, json={"content": text}) as resp:
                data = await resp.json()
                return data.get('success', False)
        except Exception as e:
            logger.error("add_comment error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Избранное  POST /api/v1/users/<username>/favorites/export
    # ------------------------------------------------------------------
    async def get_favorites(self, username, password):
        """Возвращает список избранных постов через экспорт zip-архива.
        При ошибке авторизации возвращает None, при отсутствии избранного — []."""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/v1/users/{username}/favorites/export"
            async with session.post(url, json={"password": password}) as resp:
                if resp.status == 401:
                    logger.warning("get_favorites: wrong password for %s", username)
                    return None
                if resp.status == 403:
                    return []  # нет избранного
                if resp.status != 200:
                    logger.warning("get_favorites: HTTP %s for %s", resp.status, username)
                    return None
                zip_data = await resp.read()

            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                # Ищем metadata.json в архиве
                for name in zf.namelist():
                    if name.endswith('metadata.json'):
                        metadata = json.loads(zf.read(name).decode('utf-8'))
                        # Сервер возвращает {"username": ..., "posts": [...]}
                        return metadata.get('posts', []) if isinstance(metadata, dict) else []

                # Запасной вариант: извлекаем директории постов из структуры zip
                posts = []
                seen = set()
                for name in zf.namelist():
                    parts = name.split('/')
                    if len(parts) >= 2 and parts[0] == 'posts':
                        post_dir = parts[1]
                        if post_dir not in seen:
                            seen.add(post_dir)
                            posts.append({'id': post_dir, 'title': ''})
                return posts

        except Exception as e:
            logger.error("get_favorites error: %s", e)
            return None
