from .user import User


class SessionManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.selected_user = None
            self.users = []
            self._initialized = True

    def create_user(self, manual_url_provider=None, cancel_event=None):
        user = User(manual_url_provider=manual_url_provider, cancel_event=cancel_event)
        self.selected_user = user
        self.users.append(user)
        return user

    def get_users(self):
        return self.users

    def get_selected_user(self):
        return self.selected_user

    def set_session_id(self, session_id):
        filtered_users = [user for user in self.users if user.get_id() == session_id]
        if filtered_users:
            self.selected_user = filtered_users[0]
        else:
            self.selected_user = None
