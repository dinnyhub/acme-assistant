import os
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.logger import get_logger
from app.metrics import log_error

load_dotenv()
logger = get_logger(__name__)

security = HTTPBearer()

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "acme")
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "acme-app")


async def get_keycloak_public_key() -> str:
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        realm_info = response.json()
        public_key = realm_info["public_key"]
        return f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> dict:
    token = credentials.credentials
    try:
        public_key = await get_keycloak_public_key()
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience="account"
        )
        username = payload.get("preferred_username")
        roles = payload.get("realm_access", {}).get("roles", [])
        logger.info(f"User authenticated | username={username} | roles={roles}")
        return {
            "username": username,
            "roles": roles,
            "email": payload.get("email"),
        }
    except JWTError as e:
        log_error("auth", "JWTError", str(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except Exception as e:
        log_error("auth", "AuthError", str(e))
        raise HTTPException(status_code=401, detail="Authentication failed")


def require_role(required_role: str):
    async def role_checker(
        user: dict = Depends(get_current_user)
    ) -> dict:
        if required_role not in user["roles"]:
            log_error(
                "auth",
                "InsufficientPermissions",
                f"User {user['username']} requires role {required_role}",
                user_role=str(user["roles"])
            )
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {required_role}"
            )
        return user
    return role_checker


def get_user_role(user: dict) -> str:
    roles = user.get("roles", [])
    if "admin" in roles:
        return "admin"
    elif "support_user" in roles:
        return "support_user"
    elif "sales_user" in roles:
        return "sales_user"
    return "unknown"