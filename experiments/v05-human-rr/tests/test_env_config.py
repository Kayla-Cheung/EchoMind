import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from env_config import load_local_keys


class LocalEnvTests(unittest.TestCase):
    def test_loads_only_nonempty_keys_and_preserves_process_override(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("# local\nDEEPSEEK_API_KEY=from-file\nMINIMAX_API_KEY=\n"
                            "OPENAI_API_KEY='from-file-openai'\n", encoding="utf-8")
            with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "process-key"}, clear=True):
                load_local_keys(path)
                self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "process-key")
                self.assertEqual(os.environ["OPENAI_API_KEY"], "from-file-openai")
                self.assertNotIn("MINIMAX_API_KEY", os.environ)

    def test_rejects_unknown_names_without_echoing_value(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("UNKNOWN_KEY=secret-value\n", encoding="utf-8")
            with self.assertRaises(ValueError) as error:
                load_local_keys(path)
            self.assertNotIn("secret-value", str(error.exception))


if __name__ == "__main__":
    unittest.main()
