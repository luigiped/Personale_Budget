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
from functools import lru_cache

import bcrypt
import pyotp
from cryptography.fernet import Fernet, InvalidToken

from config_runtime import get_secret

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


# ---------------------------------------------------------------------------
# TOTP helpers
# ---------------------------------------------------------------------------

_TOTP_ISSUER = "Personal Budget"
_ENCRYPTION_PREFIX = "enc:"


@lru_cache(maxsize=1)
def _get_data_cipher() -> Fernet | None:
    """
    Restituisce il cipher applicativo per cifrare dati sensibili nel DB.
    Richiede APP_DATA_ENCRYPTION_KEY in formato Fernet.
    """
    raw_key = get_secret("APP_DATA_ENCRYPTION_KEY")
    if not raw_key:
        logger.warning("APP_DATA_ENCRYPTION_KEY non configurata: cifratura applicativa disattiva.")
        return None
    try:
        return Fernet(str(raw_key).strip().encode("utf-8"))
    except Exception as exc:
        logger.error("APP_DATA_ENCRYPTION_KEY non valida: %s", exc)
        return None


def generate_totp_secret() -> str:
    """Genera un nuovo secret TOTP casuale in formato base32."""
    return pyotp.random_base32()


def encrypt_sensitive_value(value: str) -> str:
    """
    Cifra un valore sensibile per il DB.
    Se la chiave applicativa non è configurata, restituisce il valore in chiaro
    per compatibilità retroattiva.
    """
    raw = str(value or "")
    cipher = _get_data_cipher()
    if not raw or cipher is None:
        return raw
    return f"{_ENCRYPTION_PREFIX}{cipher.encrypt(raw.encode('utf-8')).decode('utf-8')}"


def decrypt_sensitive_value(value: str) -> str | None:
    """
    Decifra un valore sensibile dal DB.
    Supporta sia valori cifrati con prefisso `enc:` sia valori legacy in chiaro.
    """
    raw = str(value or "")
    if not raw:
        return ""
    if not raw.startswith(_ENCRYPTION_PREFIX):
        return raw
    cipher = _get_data_cipher()
    if cipher is None:
        logger.error("Impossibile decifrare un valore sensibile: chiave applicativa assente.")
        return None
    try:
        token = raw[len(_ENCRYPTION_PREFIX):].encode("utf-8")
        return cipher.decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        logger.error("decrypt_sensitive_value: token non valido: %s", exc)
        return None
    except Exception as exc:
        logger.error("decrypt_sensitive_value: errore inatteso: %s", exc)
        return None


def get_totp_uri(secret: str, email: str) -> str:
    """
    Restituisce l'URI otpauth:// da codificare nel QR code.
    Compatibile con Google Authenticator, Authy, ecc.
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=_TOTP_ISSUER)


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verifica un codice TOTP a 6 cifre contro il secret.

    valid_window=1 tollera uno skew di ±30 secondi sull'orologio del client.
    Non solleva mai eccezioni: in caso di errore restituisce False e logga.
    """
    if not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(str(code).strip(), valid_window=1)
    except Exception as exc:
        logger.error("verify_totp_code: errore inatteso: %s", exc)
        return False
