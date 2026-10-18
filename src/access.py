import math
import secrets
import threading
import time

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 6
SESSION_COOKIE = "rs_session"

FREE_TRIES = 5
FIRST_WAIT = 2
MAX_WAIT = 300


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text) -> str | None:
    """The code in text, ignoring case, spaces and dashes, or None if it isn't code-shaped."""
    if not isinstance(text, str) or not text.isascii():
        return None
    code = text.replace(" ", "").replace("-", "").upper()
    if len(code) != CODE_LENGTH or not set(code) <= set(CODE_ALPHABET):
        return None
    return code


def format_code(code: str) -> str:
    return f"{code[:3]} {code[3:]}"


def wait_after(failures: int) -> int:
    """Seconds an IP must wait after this many wrong codes in a row."""
    if failures < FREE_TRIES:
        return 0
    return min(MAX_WAIT, FIRST_WAIT * 2 ** (failures - FREE_TRIES))


class TooManyTries(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"Too many tries, retry after {retry_after} s")
        self.retry_after = retry_after


class AccessControl:
    """The access code, the sessions it starts and the per-IP count of wrong codes. All in memory."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self.require_code = True
        self.code = None
        self._sessions = set()
        self._failures = {}  # client IP -> (wrong codes in a row, time its wait ends)

    def start(self, require_code: bool) -> str | None:
        with self._lock:
            self.require_code = require_code
            self.code = new_code() if require_code else None
            self._sessions.clear()
            self._failures.clear()
            return self.code

    def stop(self):
        with self._lock:
            self.code = None
            self._sessions.clear()
            self._failures.clear()

    def try_code(self, client_ip: str, text) -> str | None:
        """A new session token if text is the code, else None. Raises TooManyTries while the IP must wait."""
        with self._lock:
            now = self._clock()
            failures, wait_until = self._failures.get(client_ip, (0, now))
            if now < wait_until:
                raise TooManyTries(math.ceil(wait_until - now))
            if self.code is None or normalize_code(text) != self.code:
                failures += 1
                self._failures[client_ip] = (failures, now + wait_after(failures))
                return None
            self._failures.pop(client_ip, None)
            token = secrets.token_urlsafe(32)
            self._sessions.add(token)
            return token

    def is_valid(self, token) -> bool:
        with self._lock:
            return token in self._sessions

    def end_session(self, token):
        with self._lock:
            self._sessions.discard(token)


access = AccessControl()
