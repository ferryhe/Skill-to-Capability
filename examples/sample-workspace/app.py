class User:
    def __init__(self, role: str) -> None:
        self.role = role


def can_view_admin_report(user: User) -> bool:
    return user.role == "admin"
