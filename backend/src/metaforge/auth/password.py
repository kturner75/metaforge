"""Password hashing service using bcrypt."""

from passlib.context import CryptContext


class PasswordService:
    """Service for hashing and verifying passwords using bcrypt.

    Uses passlib's CryptContext for secure password hashing with
    automatic salt generation and configurable work factor.
    """

    def __init__(self, rounds: int = 12):
        """Initialize the password service.

        Args:
            rounds: bcrypt work factor (default 12, higher = slower + more secure)
        """
        self._context = CryptContext(
            schemes=["bcrypt"],
            deprecated="auto",
            bcrypt__rounds=rounds,
        )

    def hash(self, password: str) -> str:
        """Hash a password.

        Args:
            password: Plain text password

        Returns:
            Bcrypt hash string (includes algorithm, rounds, salt, and hash)
        """
        return self._context.hash(password)

    def verify(self, password: str, hash: str) -> bool:
        """Verify a password against a hash.

        Args:
            password: Plain text password to verify
            hash: Bcrypt hash to verify against

        Returns:
            True if password matches, False otherwise
        """
        try:
            return self._context.verify(password, hash)
        except Exception:
            return False

    def needs_rehash(self, hash: str) -> bool:
        """Check if a hash needs to be upgraded.

        This can happen when bcrypt rounds are increased or the
        hashing scheme is updated.

        Args:
            hash: Existing password hash

        Returns:
            True if the hash should be regenerated
        """
        return self._context.needs_update(hash)
