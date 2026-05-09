import os
from src import GoldForum

def main():
    app = GoldForum()
    
    user = os.getenv("GOLDFORUM_USER", "sari")
    pwd = os.getenv("GOLDFORUM_PASS", "12345678")
    
    if app.login(user, pwd):
        post = app.get_post(1)
        print(f"Пост: {post.get('title')}")
        
        app.add_comment(1, "Круто! 👍")
        app.like(1)
        app.toggle(1, "favorite")
        app.export_post(1)
        app.bulk_export([1, 2, 3])
        
        print(app.status(1))
        app.logout()
        app.close()

if __name__ == "__main__":
    main()
