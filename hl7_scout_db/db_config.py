# Copyright © 2026 Sebastian Bąk. All rights reserved.
"""Hospital Oracle DB connection configurations — persisted encrypted via Windows DPAPI."""

import ctypes
import ctypes.wintypes
import json
import os
import sys
from dataclasses import dataclass, asdict
from typing import List


# ── Windows DPAPI ─────────────────────────────────────────────────────────────

class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_encrypt(plaintext: bytes) -> bytes:
    buf = ctypes.create_string_buffer(plaintext)
    blob_in = _BLOB(len(plaintext), buf)
    blob_out = _BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


def _dpapi_decrypt(ciphertext: bytes) -> bytes:
    buf = ctypes.create_string_buffer(ciphertext)
    blob_in = _BLOB(len(ciphertext), buf)
    blob_out = _BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise OSError("CryptUnprotectData failed — wrong user or corrupted file")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result


# ── Config path ───────────────────────────────────────────────────────────────

def _config_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


_CONFIG_FILE = os.path.join(_config_dir(), "db_config.bin")
_CONFIG_FILE_LEGACY = os.path.join(_config_dir(), "db_config.json")


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HospitalDB:
    name: str
    host: str
    port: int = 1521
    service: str = ""
    user: str = ""
    password: str = ""
    thick_mode: bool = False
    instant_client_dir: str = ""


# ── Persistence ───────────────────────────────────────────────────────────────

def load_hospitals() -> List[HospitalDB]:
    # Try encrypted file first
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "rb") as f:
                raw = _dpapi_decrypt(f.read())
            data = json.loads(raw.decode("utf-8"))
            return [HospitalDB(**{k: v for k, v in h.items()
                                  if k in HospitalDB.__dataclass_fields__})
                    for h in data]
        except Exception:
            pass

    # Migrate legacy plain-text JSON if present
    if os.path.exists(_CONFIG_FILE_LEGACY):
        hospitals = []
        try:
            with open(_CONFIG_FILE_LEGACY, "r", encoding="utf-8") as f:
                data = json.load(f)
            hospitals = [HospitalDB(**{k: v for k, v in h.items()
                                       if k in HospitalDB.__dataclass_fields__})
                         for h in data]
            save_hospitals(hospitals)
        except Exception:
            pass
        finally:
            # Always remove legacy plaintext file — credentials must not stay on disk
            try:
                os.remove(_CONFIG_FILE_LEGACY)
            except OSError:
                pass
        if hospitals:
            return hospitals

    return []


def save_hospitals(hospitals: List[HospitalDB]):
    plaintext = json.dumps(
        [asdict(h) for h in hospitals], ensure_ascii=False, indent=2
    ).encode("utf-8")
    encrypted = _dpapi_encrypt(plaintext)
    with open(_CONFIG_FILE, "wb") as f:
        f.write(encrypted)
