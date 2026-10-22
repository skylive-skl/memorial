import secrets

# Без неоднозначных символов: нет 0/O, 1/l/I, i, o.
ALPHABET = "23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
LENGTH = 8


def generate_short_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
