class User:
    def __init__(self, email, username, password):
        self.email = email
        self.username = username
        self.password = password
    
    def to_dict(self):
        return {
            "email": self.email,
            "username": self.username
        }
