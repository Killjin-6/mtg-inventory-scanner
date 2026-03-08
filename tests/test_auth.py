from __future__ import annotations

import base64
import os
import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from api.auth import get_auth_config, parse_basic_auth_header, require_app_auth


class AuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_username = os.environ.get("MTG_AUTH_USERNAME")
        self.original_password = os.environ.get("MTG_AUTH_PASSWORD")

    def tearDown(self) -> None:
        if self.original_username is None:
            os.environ.pop("MTG_AUTH_USERNAME", None)
        else:
            os.environ["MTG_AUTH_USERNAME"] = self.original_username

        if self.original_password is None:
            os.environ.pop("MTG_AUTH_PASSWORD", None)
        else:
            os.environ["MTG_AUTH_PASSWORD"] = self.original_password

    @staticmethod
    def request_with_auth(header_value: str | None) -> SimpleNamespace:
        return SimpleNamespace(headers={"Authorization": header_value} if header_value else {})

    def test_parse_basic_auth_header(self) -> None:
        encoded = base64.b64encode(b"user:pass").decode("ascii")
        self.assertEqual(parse_basic_auth_header(f"Basic {encoded}"), ("user", "pass"))
        self.assertIsNone(parse_basic_auth_header("Bearer abc"))
        self.assertIsNone(parse_basic_auth_header("Basic not-base64"))

    def test_auth_disabled_by_default(self) -> None:
        os.environ.pop("MTG_AUTH_USERNAME", None)
        os.environ.pop("MTG_AUTH_PASSWORD", None)

        config = get_auth_config()
        self.assertFalse(config.enabled)
        require_app_auth(self.request_with_auth(None))

    def test_auth_rejects_missing_credentials_when_enabled(self) -> None:
        os.environ["MTG_AUTH_USERNAME"] = "scanner"
        os.environ["MTG_AUTH_PASSWORD"] = "secret"

        with self.assertRaises(HTTPException) as context:
            require_app_auth(self.request_with_auth(None))

        self.assertEqual(context.exception.status_code, 401)

    def test_auth_accepts_valid_credentials_when_enabled(self) -> None:
        os.environ["MTG_AUTH_USERNAME"] = "scanner"
        os.environ["MTG_AUTH_PASSWORD"] = "secret"
        encoded = base64.b64encode(b"scanner:secret").decode("ascii")

        require_app_auth(self.request_with_auth(f"Basic {encoded}"))


if __name__ == "__main__":
    unittest.main()
