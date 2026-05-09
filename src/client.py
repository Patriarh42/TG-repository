import os
import requests

class GoldForum:
    def __init__(self, base_url=None):
        self.base = (base_url or os.getenv("GOLDFORUM_URL", "http://23.111.103.231")).rstrip('/')
        self.session = requests.Session()
        self.authenticated = False

    def login(self, username, password):
        r = self.session.post(f"{self.base}/api/v1/auth/login", json={"username": username, "password": password}, timeout=30)
        data = r.json()
        if data.get("success"):
            self.authenticated = True
            print(f"✓ Вошли как {username}")
        return data

    def logout(self):
        self.session.post(f"{self.base}/api/v1/auth/logout", timeout=30)
        self.authenticated = False
        print("✓ Вышли")

    def get_post(self, post_id):
        return self.session.get(f"{self.base}/api/v1/posts/{post_id}/metadata", timeout=30).json()

    def import_post(self, zip_path):
        if not os.path.exists(zip_path):
            return {"success": False, "error": "Файл не найден"}
        with open(zip_path, 'rb') as f:
            files = {'zip_file': (os.path.basename(zip_path), f, 'application/zip')}
            return self.session.post(f"{self.base}/api/v1/posts/import", files=files, timeout=60).json()

    def export_post(self, post_id, output=None):
        r = self.session.get(f"{self.base}/api/v1/posts/{post_id}/export", timeout=60)
        if r.ok:
            out = output or f"data/post_{post_id}.zip"
            os.makedirs("data", exist_ok=True)
            with open(out, 'wb') as f: f.write(r.content)
            print(f"✓ Сохранено: {out}")
            return True
        return False

    def bulk_export(self, post_ids, output="data/posts.zip"):
        r = self.session.post(f"{self.base}/api/v1/posts/export/bulk", json={"post_ids": post_ids}, timeout=120)
        if r.ok:
            os.makedirs("data", exist_ok=True)
            with open(output, 'wb') as f: f.write(r.content)
            print(f"✓ Экспортировано: {output}")
            return True
        return False

    def get_comments(self, post_id):
        return self.session.get(f"{self.base}/api/v1/posts/{post_id}/comments", timeout=30).json()

    def add_comment(self, post_id, text):
        return self.session.post(f"{self.base}/api/v1/posts/{post_id}/comments", json={"content": text}, timeout=30).json()

    def delete_comment(self, comment_id):
        return self.session.delete(f"{self.base}/api/v1/comments/{comment_id}, timeout=30).json()

    def like(self, post_id):
        return self.session.post(f"{self.base}/api/v1/posts/{post_id}/like", timeout=30).json()

    def toggle(self, post_id, action):
        return self.session.post(f"{self.base}/api/interactions/toggle", json={"post_id": post_id, "action": action}, timeout=30).json()

    def status(self, post_id):
        return self.session.get(f"{self.base}/api/interactions/post/{post_id}/status", timeout=30).json()

    def export_favorites(self, username, password, output=None):
        out = output or f"data/{username}_favorites.zip"
        os.makedirs("data", exist_ok=True)
        r = self.session.post(f"{self.base}/api/v1/users/{username}/favorites/export", json={"password": password}, timeout=120)
        if r.ok:
            with open(out, 'wb') as f: f.write(r.content)
            print(f"✓ Избранное: {out}")
            return True
        return False

    def close(self):
        self.session.close()
