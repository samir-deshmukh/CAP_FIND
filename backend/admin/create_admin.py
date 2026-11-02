import argparse
import getpass

from .db import connect, init_admin_schema
from .security import ROLES, hash_password


def main():
    """Create one administrator account through the protected role/password setup path.

    Connections: Uses backend.admin.db for schema/database access and backend.admin.security to validate the role and hash the password before storage.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=sorted(ROLES), default="SUPER_ADMIN")
    args = parser.parse_args()
    password = getpass.getpass("Password: ")

    init_admin_schema()
    with connect() as connection:
        connection.execute(
            "INSERT INTO admin_users(username,password_hash,role) VALUES (?,?,?)",
            (args.username, hash_password(password), args.role),
        )

    print("Admin created:", args.username)


if __name__ == "__main__":
    main()
