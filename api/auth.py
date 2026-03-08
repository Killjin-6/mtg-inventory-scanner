from __future__ import annotations

import base64
import binascii
import os
import secrets
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class AuthConfig:
    enabled: bool
    username: str | None
    password: str | None


def get_auth_config() -> AuthConfig:
    username = os.getenv("MTG_AUTH_USERNAME")
    password = os.getenv("MTG_AUTH_PASSWORD")
    enabled = bool(username and password)
    return AuthConfig(enabled=enabled, username=username, password=password)


def parse_basic_auth_header(header_value: str | None) -> tuple[str, str] | None:
    if not header_value:
        return None

    scheme, _, encoded = header_value.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None

    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return None

    username, separator, password = decoded.partition(":")
    if not separator:
        return None
    return username, password


def require_app_auth(request: Request) -> None:
    config = get_auth_config()
    if not config.enabled:
        return

    credentials = parse_basic_auth_header(request.headers.get("Authorization"))
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Basic"},
        )

    username, password = credentials
    if not (
        config.username
        and config.password
        and secrets.compare_digest(username, config.username)
        and secrets.compare_digest(password, config.password)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Basic"},
        )
