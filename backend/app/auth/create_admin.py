"""Create an admin account from the server console:   python -m app.auth.create_admin"""
import getpass
import sys

from app.auth import service
from app.core import db


def main() -> int:
    db.init_db()
    email = input("Admin email: ").strip()
    name = input("Full name [Administrator]: ").strip() or "Administrator"
    pw = getpass.getpass("Password (12+ chars): ")
    if pw != getpass.getpass("Repeat password: "):
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        with db.session_scope() as s:
            u = service.create_admin(s, email, pw, name)
            print(f"Created admin {u.email}. Sign in at the admin login page (a code will be emailed to you).")
    except Exception as e:
        print(f"Could not create admin: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
