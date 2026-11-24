"""Check notebook input selection without loading any real participant data."""
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("echomind_reference_copy", ROOT / "human-analysis/copy_data.py")
REFERENCE_COPY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFERENCE_COPY)


class AnalysisPortabilityTests(unittest.TestCase):
    def test_reference_copy_and_identical_repeat_preserve_source_and_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source's & example.csv"
            source.write_bytes(b"synthetic_fixture\n")
            destination = Path(directory) / "raw/rr.csv"
            self.assertEqual(REFERENCE_COPY.copy_reference(source, destination)[0], "copied")
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            stamp = destination.stat().st_mtime_ns
            self.assertEqual(REFERENCE_COPY.copy_reference(source, destination)[0], "unchanged")
            self.assertEqual(destination.stat().st_mtime_ns, stamp)
            self.assertEqual(source.read_bytes(), b"synthetic_fixture\n")

    def test_conflicting_raw_reference_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / "source.csv", Path(directory) / "rr.csv"
            source.write_bytes(b"new_synthetic_fixture\n")
            destination.write_bytes(b"original_synthetic_fixture\n")
            with self.assertRaisesRegex(ValueError, "existing data was preserved"):
                REFERENCE_COPY.copy_reference(source, destination)
            self.assertEqual(destination.read_bytes(), b"original_synthetic_fixture\n")

    def test_missing_source_does_not_create_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "raw/rr.csv"
            with self.assertRaises(FileNotFoundError):
                REFERENCE_COPY.copy_reference(Path(directory) / "missing.csv", destination)
            self.assertFalse(destination.parent.exists())

    @classmethod
    def setUpClass(cls):
        notebook = json.loads((ROOT / "human-analysis/notebooks/01_data_exploration.ipynb").read_text(encoding="utf-8"))
        cls.code = "".join(next(c["source"] for c in notebook["cells"] if "data-loading" in c.get("metadata", {}).get("tags", [])))

    def test_checkout_and_notebook_working_directories_select_same_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            analysis = checkout / "human-analysis"
            (analysis / "notebooks").mkdir(parents=True)
            (analysis / "notebooks/01_data_exploration.ipynb").write_text("{}", encoding="utf-8")
            target = analysis / "data/raw/rr.csv"
            target.parent.mkdir(parents=True)
            target.write_text("synthetic_fixture\n", encoding="utf-8")
            for cwd in (checkout, analysis, analysis / "notebooks"):
                loaded = []
                reader = SimpleNamespace(read_csv=lambda p: (loaded.append(p) or SimpleNamespace(shape=(1, 1))))
                with patch.object(Path, "cwd", return_value=cwd), contextlib.redirect_stdout(io.StringIO()):
                    exec(self.code, {"Path": Path, "pd": reader})
                self.assertEqual(loaded, [target])

    def test_missing_reference_fails_before_reading_other_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = Path(directory)
            notebooks = checkout / "human-analysis/notebooks"
            notebooks.mkdir(parents=True)
            (notebooks / "01_data_exploration.ipynb").write_text("{}", encoding="utf-8")
            reader = SimpleNamespace(read_csv=lambda _: self.fail("Unexpected data read"))
            with patch.object(Path, "cwd", return_value=checkout):
                with self.assertRaisesRegex(FileNotFoundError, "data-access.md"):
                    exec(self.code, {"Path": Path, "pd": reader})
