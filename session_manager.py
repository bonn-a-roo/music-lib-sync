from model.user import User


class SessionManager:
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.selected_user = None
        self.users = []

    def create_user(self):
        user = User()
        self.selected_user = user
        self.users.append(user)

    def get_users(self):
        if not self.users:
            self.create_user()
        return self.users

    def get_selected_user(self):
        return self.selected_user

    def set_session_id(self, session_id):
        filtered_users = [user for user in self.users if user.get_id() == session_id]
        if filtered_users:
            self.selected_user = filtered_users[0]
        else:
            self.selected_user = None
