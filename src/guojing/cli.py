"""Interactive administrator account commands that keep passwords out of shell history."""

import argparse
from collections.abc import Callable, Sequence
from getpass import getpass

from guojing.application.auth.ports import (
    AdminUserNotFoundError,
    PasswordHasher,
)
from guojing.application.auth.service import AdminAuthService
from guojing.core.config import Settings
from guojing.infrastructure.persistence.admin_auth_repository import (
    SqlAlchemyAdminAuthRepository,
)
from guojing.infrastructure.persistence.database import Database
from guojing.infrastructure.security.passwords import Argon2PasswordHasher

PasswordReader = Callable[[str], str]


def main(
    argv: Sequence[str] | None = None,
    password_reader: PasswordReader = getpass,
    password_hasher: PasswordHasher | None = None,
) -> int:
    parser = _build_parser()
    arguments = parser.parse_args(argv)
    settings = Settings()
    database = Database(settings.database_url)
    service = AdminAuthService(
        SqlAlchemyAdminAuthRepository(database),
        password_hasher or Argon2PasswordHasher(),
    )
    try:
        password = password_reader("Password: ")
        confirmation = password_reader("Confirm password: ")
        if password != confirmation:
            parser.error("passwords do not match")
        if arguments.command == "create-admin":
            admin = service.create_admin(arguments.username, password)
            print(f"Created administrator {admin.username!r}.")
        else:
            admin = service.reset_admin_password(arguments.username, password)
            print(f"Reset password and revoked sessions for {admin.username!r}.")
    except (ValueError, AdminUserNotFoundError) as error:
        parser.error(str(error))
    finally:
        database.dispose()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="guojing-admin")
    commands = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("create-admin", "create an administrator account"),
        ("reset-admin-password", "reset a password and revoke existing sessions"),
    ):
        subcommand = commands.add_parser(command, help=help_text)
        subcommand.add_argument("--username", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
