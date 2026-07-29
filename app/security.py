"""Password hashing, signed session tokens, and ID generation."""
import secrets
import string
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext

from app.config import SECRET_KEY, SESSION_TTL_SECONDS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="sms-session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
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
    except (BadSignature, SignatureExpired, Exception):
        return None


def random_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))