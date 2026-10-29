"""Password hashing with scrypt from Python's standard library.

A hash is a one-way function: a password can be checked against it, but the
password cannot be calculated back. A random salt makes the same password look
different for every user, and scrypt is deliberately slow and memory-hungry,
so trying millions of guesses becomes expensive.
"""

import base64
import hashlib
import hmac
import secrets

# Cost parameters: about 16 MB of memory and a few dozen milliseconds per hash
N, R, P = 2**14, 8, 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=32)
    # The parameters are stored with the hash, so they can be raised later
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = stored_hash.split("$")
    except ValueError:
        return False
    if algorithm != "scrypt":
        return False
    expected = base64.b64decode(digest)
    actual = hashlib.scrypt(
        password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p), dklen=len(expected)
    )
    # compare_digest takes the same time for every input, so timing reveals nothing
    return hmac.compare_digest(actual, expected)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
