"""Password hashing, signed session tokens, and ID generation."""
import logging
import secrets
import string
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext

from app.config import SECRET_KEY, SESSION_TTL_SECONDS

logger = logging.getLogger("sms.security")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="sms-session")

MIN_PASSWORD_LENGTH = 8
# bcrypt silently truncates anything past this many UTF-8 bytes — we reject
# instead of truncating, so two different long passwords can never collide.
BCRYPT_MAX_BYTES = 72


class PasswordError(ValueError):
    """Raised for password inputs that are unsafe to hash (too short/long)."""


def hash_password(password: str) -> str:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise PasswordError(f"Password is too long (max {BCRYPT_MAX_BYTES} bytes)")
    return pwd_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or not password:
        return False
    try:
        return pwd_context.verify(password, stored_hash)
    except Exception:
        return False


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def create_session(payload: dict) -> str:
    """Sign a session payload (uid, role, name, ...). Expiry is enforced on verify."""
    return _serializer.dumps(payload)


def verify_session(token: str):
    """Return the decoded payload dict, or None if missing/invalid/expired."""
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return None  # expected: not logged in, tampered, or expired cookie
    except Exception:
        logger.exception("Unexpected error verifying session token")
        return None


def random_password(length: int = 12) -> str:
    """Generates a random password with guaranteed character diversity
    (at least one lowercase, one uppercase, one digit)."""
    if length < 4:
        length = 4
    alphabet = string.ascii_letters + string.digits
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(length))
        if (any(c.islower() for c in pw) and
            any(c.isupper() for c in pw) and
            any(c.isdigit() for c in pw)):
            return pw