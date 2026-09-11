"""Check provider-specific credential names without loading real secrets."""

import importlib
import os
import unittest
from unittest.mock import patch

from backend import config


class CredentialConfigTests(unittest.TestCase):
    def test_deepseek_name_and_legacy_fallback(self) -> None:
        cases = (
            ({"DEEPSEEK_API_KEY": "provider-key"}, "provider-key"),
            ({"OPENAI_API_KEY": "legacy-key"}, "legacy-key"),
            ({"DEEPSEEK_API_KEY": "provider-key", "OPENAI_API_KEY": "legacy-key"}, "provider-key"),
            ({"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "legacy-key"}, "legacy-key"),
            ({}, ""),
        )
        try:
            for variables, expected in cases:
                with self.subTest(variables=variables), patch.dict(os.environ, variables, clear=True):
                    importlib.reload(config)
                    self.assertEqual(config.OPENAI_API_KEY, expected)
        finally:
            importlib.reload(config)

    def test_bocha_key_is_read_independently(self) -> None:
        try:
            with patch.dict(os.environ, {"BOCHA_API_KEY": "search-key"}, clear=True):
                importlib.reload(config)
                self.assertEqual(config.BOCHA_API_KEY, "search-key")
                self.assertEqual(config.OPENAI_API_KEY, "")
        finally:
            importlib.reload(config)
