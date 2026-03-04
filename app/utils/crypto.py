from cryptography.fernet import Fernet


def encrypt_data(plaintext: str, key: str) -> bytes:
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.encrypt(plaintext.encode("utf-8"))


def decrypt_data(ciphertext: bytes, key: str) -> str:
    f = Fernet(key.encode() if isinstance(key, str) else key)
    return f.decrypt(ciphertext).decode("utf-8")
