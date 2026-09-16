"""Cifrado/descifrado de la contraseña usando DPAPI (Windows Data Protection API).

La contraseña queda ligada al usuario de Windows que la cifró: solo esa
cuenta, en ese equipo, puede descifrarla de nuevo. No se guarda ninguna
clave por separado.
"""
import ctypes
import ctypes.wintypes as wintypes


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    data = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return data


def _bytes_to_blob(data: bytes) -> DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    blob = DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))
    blob._buffer_keepalive = buf  # evita que el GC libere el buffer
    return blob


def protect(plaintext: str) -> bytes:
    """Cifra una cadena de texto con DPAPI (ámbito: usuario actual)."""
    if not plaintext:
        raise ValueError("No se puede cifrar una cadena vacía")
    data = plaintext.encode("utf-8")
    in_blob = _bytes_to_blob(data)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,   # descripción
        None,   # entropía adicional
        None,
        None,   # prompt struct
        0,      # flags
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    return _blob_to_bytes(out_blob)


def unprotect(ciphertext: bytes) -> str:
    """Descifra datos previamente cifrados con protect()."""
    in_blob = _bytes_to_blob(ciphertext)
    out_blob = DATA_BLOB()
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    return _blob_to_bytes(out_blob).decode("utf-8")
