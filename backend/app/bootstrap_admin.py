from __future__ import annotations

import argparse
from getpass import getpass

from app.config import settings
from app.db.migrations import initialize_database
from app.db.session import SessionLocal
from app.services.users import BootstrapAdminError, BootstrapAdminInput, bootstrap_initial_admin


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the first admin user for Private Ledger.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--password")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password or getpass("Password: ")
    initialize_database(settings.database_url)

    with SessionLocal() as session:
        try:
            user = bootstrap_initial_admin(
                session=session,
                admin=BootstrapAdminInput(
                    email=args.email,
                    display_name=args.display_name,
                    password=password,
                ),
                pepper=settings.password_pepper,
            )
        except BootstrapAdminError as exc:
            print(str(exc))
            return 1

    print(f"Created admin user {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
