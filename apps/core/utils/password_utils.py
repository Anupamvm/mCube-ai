"""
Secure password generation and management utilities.

This module provides utilities for generating secure random passwords
and handling password-related security concerns.
"""

import secrets
import string
from typing import Optional


def generate_secure_password(length: int = 16, include_symbols: bool = True) -> str:
    """
    Generate a cryptographically secure random password.

    Uses Python's secrets module to generate passwords suitable for
    managing user accounts and security credentials.

    Args:
        length: Password length (default: 16 characters)
        include_symbols: Include special characters (default: True)

    Returns:
        str: Cryptographically secure random password

    Example:
        >>> password = generate_secure_password(20)
        >>> len(password)
        20
        >>> # Password will contain letters, digits, and symbols
    """
    if length < 8:
        raise ValueError("Password length must be at least 8 characters")

    # Define character sets
    letters = string.ascii_letters  # a-z, A-Z
    digits = string.digits  # 0-9
    symbols = string.punctuation if include_symbols else ''

    # Combine all characters
    all_characters = letters + digits + symbols

    # Ensure password has at least one character from each set
    password_chars = [
        secrets.choice(letters),  # At least one letter
        secrets.choice(digits),   # At least one digit
    ]

    if include_symbols:
        password_chars.append(secrets.choice(symbols))  # At least one symbol

    # Fill remaining length with random characters
    remaining_length = length - len(password_chars)
    password_chars.extend(secrets.choice(all_characters) for _ in range(remaining_length))

    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password_chars)

    return ''.join(password_chars)


def get_password_from_env(env_var_name: str, default: Optional[str] = None) -> str:
    """
    Get password from environment variable with fallback to secure generation.

    Security best practice: Always use environment variables for passwords
    in production. This function helps maintain backward compatibility while
    encouraging secure practices.

    Args:
        env_var_name: Name of environment variable to check
        default: Default password if env var not set (None = generate secure password)

    Returns:
        str: Password from env var or default/generated password

    Example:
        >>> import os
        >>> os.environ['ADMIN_PASSWORD'] = 'my_secure_pass'
        >>> password = get_password_from_env('ADMIN_PASSWORD')
        >>> password
        'my_secure_pass'
    """
    import os

    password = os.environ.get(env_var_name)

    if password:
        return password

    if default is None:
        # Generate secure password if no default provided
        return generate_secure_password()

    return default


def validate_password_strength(password: str) -> tuple[bool, list[str]]:
    """
    Validate password strength and return feedback.

    Checks password against common security requirements:
    - Minimum length of 8 characters
    - Contains uppercase letters
    - Contains lowercase letters
    - Contains digits
    - Contains special characters (optional but recommended)

    Args:
        password: Password to validate

    Returns:
        tuple: (is_valid, list of issues)

    Example:
        >>> is_valid, issues = validate_password_strength('admin123')
        >>> is_valid
        False
        >>> 'no uppercase letters' in issues
        True
    """
    issues = []

    if len(password) < 8:
        issues.append("must be at least 8 characters long")

    if not any(c.isupper() for c in password):
        issues.append("must contain at least one uppercase letter")

    if not any(c.islower() for c in password):
        issues.append("must contain at least one lowercase letter")

    if not any(c.isdigit() for c in password):
        issues.append("must contain at least one digit")

    if not any(c in string.punctuation for c in password):
        issues.append("should contain at least one special character (recommended)")

    # Check for common weak passwords
    weak_passwords = {
        'password', 'password123', '12345678', 'admin123',
        'trader123', 'qwerty', 'letmein'
    }
    if password.lower() in weak_passwords:
        issues.append("is a commonly used weak password")

    is_valid = len(issues) == 0 or (len(issues) == 1 and "should contain" in issues[0])

    return is_valid, issues
