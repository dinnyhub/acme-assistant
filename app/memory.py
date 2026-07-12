import json
import redis
import os
from dotenv import load_dotenv
from app.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

# Redis connection
redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True
)

SESSION_TTL = 3600  # 1 hour — sessions expire after 1 hour of inactivity


def get_session_history(session_id: str) -> list:
    """
    Retrieves conversation history for a session from Redis.
    Returns empty list if no history exists.
    """
    try:
        data = redis_client.get(f"session:{session_id}")
        if data:
            history = json.loads(data)
            logger.info(
                f"Session history retrieved | "
                f"session={session_id} | messages={len(history)}"
            )
            return history
        return []
    except Exception as e:
        logger.error(f"Redis get error | session={session_id} | error={e}")
        return []


def save_session_history(session_id: str, history: list) -> None:
    """
    Saves conversation history for a session to Redis.
    Sets TTL of 1 hour so stale sessions auto-expire.
    """
    try:
        redis_client.setex(
            f"session:{session_id}",
            SESSION_TTL,
            json.dumps(history)
        )
        logger.info(
            f"Session history saved | "
            f"session={session_id} | messages={len(history)}"
        )
    except Exception as e:
        logger.error(f"Redis set error | session={session_id} | error={e}")


def append_to_session(
    session_id: str,
    role: str,
    content: str
) -> None:
    """
    Appends a single message to session history.
    Keeps last 20 messages to avoid context window overflow.
    """
    history = get_session_history(session_id)
    history.append({"role": role, "content": content})

    # Keep only last 20 messages
    if len(history) > 20:
        history = history[-20:]

    save_session_history(session_id, history)


def clear_session(session_id: str) -> None:
    """Clears session history — called on logout."""
    try:
        redis_client.delete(f"session:{session_id}")
        logger.info(f"Session cleared | session={session_id}")
    except Exception as e:
        logger.error(f"Redis delete error | session={session_id} | error={e}")


def get_redis_health() -> bool:
    """Check if Redis is available."""
    try:
        redis_client.ping()
        return True
    except Exception:
        return False