from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    username: str
    role: str
    is_active: bool = True


def can_view_admin_report(user: User) -> bool:
    # BUG: this grants every active user access to the admin report.
    return user.is_active
