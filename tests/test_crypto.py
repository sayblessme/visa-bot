from cryptography.fernet import Fernet

from app.utils.crypto import decrypt_data, encrypt_data


def test_encrypt_decrypt_roundtrip():
    """Data survives encrypt -> decrypt cycle."""
    key = Fernet.generate_key().decode()
    plaintext = '{"cookies": [{"name": "session", "value": "abc123"}]}'

    encrypted = encrypt_data(plaintext, key)
    assert encrypted != plaintext.encode()

    decrypted = decrypt_data(encrypted, key)
    assert decrypted == plaintext
