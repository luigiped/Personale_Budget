"""
security.py
-----------
Gestione sicura delle password.

Usa bcrypt per tutti i nuovi hash. Mantiene retrocompatibilità con i vecchi
hash SHA-256: al primo login con hash legacy, ri-hasha automaticamente in bcrypt.

Import:
    from security import hash_password, verify_password
"""

import hashlib
import logging

import bcrypt

logger = logging.getLogger(__name__)

# Prefisso che distingue gli hash bcrypt da quelli SHA-256 legacy.
# Gli hash bcrypt iniziano sempre con "$2b$" — il prefisso non è necessario
# per identificarli, ma lo usiamo come guardia esplicita.
_BCRYPT_PREFIX = "$2b$"


def hash_password(password: str) -> str:
    """
    Genera un hash bcrypt della password.
    Restituisce una stringa UTF-8 pronta per essere salvata nel DB.
    """
    pwd_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifica una password contro l'hash salvato nel DB.

    Gestisce due formati:
    - bcrypt  (stored_hash inizia con "$2b$") → verifica diretta
    - SHA-256 legacy (hex di 64 caratteri)    → verifica legacy

    Restituisce True se la password è corretta, False altrimenti.
    Non solleva mai eccezioni: in caso di errore restituisce False e logga.
    """
    if not password or not stored_hash:
        return False

    stored = stored_hash.strip()

    try:
        if stored.startswith(_BCRYPT_PREFIX):
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        else:
            # Hash legacy SHA-256 (64 caratteri hex)
            sha_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
            return sha_hash == stored
    except Exception as exc:
        logger.error("verify_password: errore inatteso: %s", exc)
        return False


def needs_rehash(stored_hash: str) -> bool:
    """
    Restituisce True se l'hash è in formato legacy (SHA-256) e va aggiornato.
    Usalo dopo un login riuscito per migrare automaticamente l'utente a bcrypt.
    """
    if not stored_hash:
        return False
    return not stored_hash.strip().startswith(_BCRYPT_PREFIX)
