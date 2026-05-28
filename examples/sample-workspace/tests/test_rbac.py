import unittest

from app import User, can_view_admin_report


class AdminReportAccessTest(unittest.TestCase):
    def test_active_admin_can_view_admin_report(self) -> None:
        user = User(username="ada", role="admin", is_active=True)

        self.assertTrue(can_view_admin_report(user))

    def test_active_non_admin_cannot_view_admin_report(self) -> None:
        user = User(username="grace", role="analyst", is_active=True)

        self.assertFalse(can_view_admin_report(user))

    def test_inactive_admin_cannot_view_admin_report(self) -> None:
        user = User(username="linus", role="admin", is_active=False)

        self.assertFalse(can_view_admin_report(user))


if __name__ == "__main__":
    unittest.main()
