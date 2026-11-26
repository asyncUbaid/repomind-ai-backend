from dataclasses import dataclass


@dataclass
class User:
    email: str


def validate_user(token: str) -> User:
    if not token:
        raise ValueError("Token is required")
    return User(email="user@example.com")
