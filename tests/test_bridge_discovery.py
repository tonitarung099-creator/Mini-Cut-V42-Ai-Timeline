import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from minicut_agent.bridge_discovery import (
    discovery_path,
    read_discovery,
    remove_discovery,
    write_discovery,
)


class BridgeDiscoveryTests(unittest.TestCase):
    def test_round_trip_with_override_path(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bridge.json"
            with patch.dict(
                os.environ,
                {"MINICUT_BRIDGE_INFO_FILE": str(path)},
                clear=False,
            ):
                written = write_discovery(
                    url="http://127.0.0.1:8765",
                    token="token-123",
                    pid=42,
                )
                self.assertEqual(written, path)
                data = read_discovery()
                self.assertEqual(data["url"], "http://127.0.0.1:8765")
                self.assertEqual(data["token"], "token-123")
                self.assertEqual(data["pid"], 42)

                remove_discovery(token="wrong-token")
                self.assertTrue(path.exists())
                remove_discovery(token="token-123")
                self.assertFalse(path.exists())

    def test_environment_url_override(self):
        with patch.dict(
            os.environ,
            {
                "MINICUT_BRIDGE_URL": "http://127.0.0.1:9999/",
                "MINICUT_BRIDGE_TOKEN": "abc",
            },
            clear=False,
        ):
            data = read_discovery()
            self.assertEqual(data["url"], "http://127.0.0.1:9999")
            self.assertEqual(data["token"], "abc")


if __name__ == "__main__":
    unittest.main()
