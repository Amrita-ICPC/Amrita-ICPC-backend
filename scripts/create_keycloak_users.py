"""
Script to bulk-create student users directly in Keycloak.

Prompts for the number of users to create and creates them as
student1, student2, ... studentN with the default password "1234".
Users that already exist in Keycloak (by username) are skipped.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import config
from app.core.logger import logger
from keycloak import KeycloakAdmin, KeycloakOpenIDConnection

DEFAULT_PASSWORD = "1234"
USERNAME_PREFIX = "student"
GROUP_NAME = "student"


def get_keycloak_admin() -> KeycloakAdmin:
    """Create a KeycloakAdmin client using the users-sync service account."""
    conn = KeycloakOpenIDConnection(
        server_url=config.KEYCLOAK_SERVER_URL,
        realm_name=config.KEYCLOAK_REALM,
        client_id=config.KEYCLOAK_USERS_SYNC_CLIENT_ID,
        client_secret_key=config.KEYCLOAK_USERS_SYNC_CLIENT_SECRET,
        verify=True,
    )
    return KeycloakAdmin(connection=conn)


def get_student_group_id(keycloak_admin: KeycloakAdmin) -> str | None:
    """Look up the 'student' group id, if it exists in the realm."""
    groups = keycloak_admin.get_groups()
    for group in groups:
        if group.get("name") == GROUP_NAME:
            return group["id"]
    return None


def create_students(count: int) -> None:
    """Create `count` student users (student1..studentN), skipping existing ones."""
    keycloak_admin = get_keycloak_admin()
    student_group_id = get_student_group_id(keycloak_admin)
    if not student_group_id:
        logger.warning(
            "Group '%s' not found in realm '%s' - users will be created without a group",
            GROUP_NAME,
            config.KEYCLOAK_REALM,
        )

    created_count = 0
    skipped_count = 0

    for i in range(1, count + 1):
        username = f"{USERNAME_PREFIX}{i}"

        existing = keycloak_admin.get_users(query={"username": username, "exact": True})
        if existing:
            print(f"  Skipped {username} (already exists)")
            skipped_count += 1
            continue

        user_id = keycloak_admin.create_user(
            {
                "username": username,
                "email": f"{username}@example.com",
                "firstName": "Student",
                "lastName": str(i),
                "enabled": True,
                "emailVerified": True,
                "credentials": [
                    {
                        "type": "password",
                        "value": DEFAULT_PASSWORD,
                        "temporary": False,
                    }
                ],
            }
        )

        if student_group_id:
            keycloak_admin.group_user_add(user_id, student_group_id)

        print(f"  Created {username}")
        created_count += 1

    print("\nDone.")
    print(f"  Created: {created_count}")
    print(f"  Skipped (already existed): {skipped_count}")


def main() -> None:
    raw = input("Number of student users to create: ").strip()
    try:
        count = int(raw)
    except ValueError:
        print("Please enter a valid integer.")
        sys.exit(1)

    if count <= 0:
        print("Number of users must be positive.")
        sys.exit(1)

    create_students(count)


if __name__ == "__main__":
    main()
