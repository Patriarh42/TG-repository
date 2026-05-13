import aiohttp
import logging

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.session = None
    
    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def check_phone_registered(self, phone):
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/users/check_phone", params={"phone": phone}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('is_registered', False)
                return False
        except Exception as e:
            logger.error(e)
            return False
    
    async def auth_user(self, username, password):
        try:
            session = await self._get_session()
            async with session.post(f"{self.base_url}/auth/login", json={"username": username, "password": password}) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.error(e)
            return False
    
    async def get_favorites(self, username):
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/users/{username}/favorites") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('posts', [])
                return []
        except Exception as e:
            logger.error(e)
            return []
    
    async def get_post(self, post_id):
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/posts/{post_id}") as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"id": post_id, "error": "Not found"}
        except Exception as e:
            logger.error(e)
            return {"id": post_id, "error": str(e)}
    
    async def get_comments(self, post_id):
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/posts/{post_id}/comments") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('comments', [])
                return []
        except Exception as e:
            logger.error(e)
            return []
    
    async def add_comment(self, post_id, text, username):
        try:
            session = await self._get_session()
            async with session.post(f"{self.base_url}/posts/{post_id}/comments", json={"text": text, "author": username}) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.error(e)
            return False
