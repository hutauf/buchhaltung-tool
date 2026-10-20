"""Offline dashboard verifier, derived only after authenticating the archive."""
from __future__ import annotations
import hashlib

ITERATIONS = 2_100_000
DOMAIN = b'autobookkeeping/dashboard-password/v1\x00'


def descriptor(password: str, authenticated_key_wrapper: bytes) -> dict:
    """Derive an archive-specific salt without modifying the random key wrapper.

    Callers must first verify the exact working-tree or staged archive. The key
    wrapper already contains random salt and nonce; domain separation makes
    this independent of the archive KDF while keeping HTML builds deterministic.
    """
    if not isinstance(password,str) or not password:
        raise ValueError('Archivpasswort für Dashboard-Prüfung fehlt')
    salt=hashlib.sha256(DOMAIN+authenticated_key_wrapper).digest()
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf8'),salt,ITERATIONS,dklen=32)
    return {'version':1,'algorithm':'PBKDF2-SHA256','iterations':ITERATIONS,
            'salt':salt.hex(),'digest':digest.hex()}
