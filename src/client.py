import os
import requests

API_BASE = os.getenv("GOLDFORUM_URL", "http://23.111.103.231")


class GoldForumClient:
    def __init__(self, username=None, password=None):
        self.base = API_BASE.rstrip('/')
        self.session = requests.Session()
        if username and password:
            self.login(username, password)
    
    def login(self, username, password):
        response = self.session.post(
            f"{self.base}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=10
        )
        data = response.json()
        return data.get("success")
    
    def export_post(self, post_id):
        response = self.session.get(
            f"{self.base}/api/v1/posts/{post_id}/export",
            timeout=60
        )
        if response.status_code == 200:
            return response.content
        return None
    
    def export_favorites(self, username, password):
        response = self.session.post(
            f"{self.base}/api/v1/users/{username}/favorites/export",
            json={"password": password},
            timeout=120
        )
        if response.status_code == 200:
            return response.content
        return None
    
    def get_comments(self, post_id):
        response = self.session.get(
            f"{self.base}/api/v1/posts/{post_id}/comments",
            timeout=30
        )
        return response.json()
    
    def add_comment(self, post_id, content):
        response = self.session.post(
            f"{self.base}/api/v1/posts/{post_id}/comments",
            json={"content": content},
            timeout=30
        )
        return response.json()
    
    def close(self):
        self.session.close()
