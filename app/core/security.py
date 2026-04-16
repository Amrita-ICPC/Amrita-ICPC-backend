from fastapi import FastAPI
from fastapi_keycloak_middleware import KeycloakConfiguration, setup_keycloak_middleware

from app.core.config import config
from app.core.logger import logger

# Keycloak Configuration
keycloak_config = KeycloakConfiguration(
    url=config.KEYCLOAK_SERVER_URL,
    realm=config.KEYCLOAK_REALM,
    client_id=config.KEYCLOAK_CLIENT_ID,
    claims=["sub", "name", "email", "resource_access", "groups"],
    reject_on_missing_claim=config.ENVIRONMENT == "production",
    # Disabling SSL verify for local dev/internal CA issues or Keycloak on HTTP. not recommended for production
    verify=config.ENVIRONMENT == "production",
)


# Custom User Mapper
async def map_user(userinfo: dict):
    logger.info(f"Keycloak UserInfo Claims: {userinfo}")
    return {
        "sub": userinfo.get("sub"),
        "name": userinfo.get("name"),
        "email": userinfo.get("email"),
        "roles": userinfo.get("resource_access", {})
        .get(config.KEYCLOAK_CLIENT_ID, {})
        .get("roles", []),
        "groups": list(map(lambda x: x.lstrip("/"), userinfo.get("groups", []) or [])),
    }


def setup_security(app: FastAPI):
    """
    Setup Keycloak authentication middleware.
    """
    setup_keycloak_middleware(
        app=app,
        keycloak_configuration=keycloak_config,
        user_mapper=map_user,
        exclude_patterns=[
            f"{config.API_PREFIX}/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ],
    )
