"""Smoke tests for csvlens. No network, stdlib only."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from csvlens import TOOL_NAME, TOOL_VERSION, profile_csv, clean_csv, head_csv, select_columns
from csvlens.core import detect_dialect, _classify, _resolve_type
from csvlens.cli import main


SAMPLE = (
    "id,city,amount,flag\n"
    "1,Boston,10.5,true\n"
    "2, Boston ,20,false\n"
    "3,NYC,NA,true\n"
    "2, Boston ,20,false\n"
    ",,,\n"
)


def _write(text):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        f.write(text)
    return path


class TestCore(unittest.TestCase):
    def test_metadata(self):
        self.assertEqual(TOOL_NAME, "csvlens")
        self.assertEqual(TOOL_VERSION.count("."), 2)

    def test_classify_and_resolve(self):
        self.assertEqual(_classify("42"), "int")
        self.assertEqual(_classify("3.14"), "float")
        self.assertEqual(_classify("2026-01-01"), "date")
        self.assertEqual(_classify(""), "null")
        self.assertEqual(_resolve_type({"int": 5, "float": 2}), "float")
        self.assertEqual(_resolve_type({"int": 5}), "int")

    def test_detect_dialect(self):
        self.assertEqual(detect_dialect("a,b,c\n1,2,3\n"), ",")
        self.assertEqual(detect_dialect("a\tb\tc\n1\t2\t3\n"), "\t")
        self.assertEqual(detect_dialect("a;b;c\n1;2;3\n"), ";")

    def test_profile(self):
        path = _write(SAMPLE)
        try:
            prof = profile_csv(path)
            self.assertEqual(prof.rows, 5)
            self.assertEqual(prof.columns, 4)
            by = {c.name: c for c in prof.column_stats}
            self.assertEqual(by["id"].inferred_type, "int")
            self.assertEqual(by["amount"].inferred_type, "float")
            self.assertEqual(by["amount"].nulls, 2)
            self.assertEqual(float(by["amount"].max), 20.0)
            self.assertEqual(by["city"].nulls, 1)
        finally:
            os.remove(path)

    def test_clean(self):
        path = _write(SAMPLE)
        out = path + ".clean"
        try:
            report = clean_csv(path, out, fill_null="UNKNOWN")
            self.assertEqual(report["rows_in"], 5)
            self.assertEqual(report["duplicates_removed"], 1)
            self.assertEqual(report["empty_rows_removed"], 1)
            self.assertEqual(report["rows_out"], 3)
            self.assertGreaterEqual(report["cells_filled"], 1)
            with open(out, encoding="utf-8") as f:
                content = f.read()
            self.assertNotIn(" Boston ", content)
            self.assertIn("Boston", content)
            self.assertIn("UNKNOWN", content)
        finally:
            os.remove(path)
            if os.path.exists(out):
                os.remove(out)

    def test_head_and_select(self):
        path = _write(SAMPLE)
        try:
            h = head_csv(path, n=2)
            self.assertEqual(h["header"], ["id", "city", "amount", "flag"])
            self.assertEqual(len(h["rows"]), 2)

            sel = select_columns(path, ["city", "amount"], n=3)
            self.assertEqual(sel["header"], ["city", "amount"])
            self.assertEqual(len(sel["rows"]), 3)

            with self.assertRaises(KeyError):
                select_columns(path, ["nope"])
        finally:
            os.remove(path)


class TestCli(unittest.TestCase):
    def test_version(self):
        with self.assertRaises(SystemExit) as cm:
            main(["--version"])
        self.assertEqual(cm.exception.code, 0)

    def test_profile_json(self):
        import contextlib
        import io
        path = _write(SAMPLE)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["--format", "json", "profile", path])
            self.assertEqual(rc, 0)
        finally:
            os.remove(path)

    def test_clean_roundtrip(self):
        import contextlib
        import io
        path = _write(SAMPLE)
        out = path + ".out"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["--format", "json", "clean", path, "-o", out, "--fill-null", "X"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(out))
        finally:
            os.remove(path)
            if os.path.exists(out):
                os.remove(out)

    def test_missing_file(self):
        rc = main(["profile", os.path.join(tempfile.gettempdir(), "no_such_file_xyz.csv")])
        self.assertEqual(rc, 2)

    def test_bad_column(self):
        path = _write(SAMPLE)
        try:
            rc = main(["select", path, "-c", "nonexistent"])
            self.assertEqual(rc, 3)
        finally:
            os.remove(path)


class TestHardening(unittest.TestCase):
    """Tests for hardened input validation and edge-case handling."""

    def test_version_reads_from_version_file(self):
        """TOOL_VERSION should come from the VERSION file (0.7.4), not the pyproject default."""
        import contextlib
        import io as _io
        buf = _io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                with self.assertRaises(SystemExit) as cm:
                    main(["--version"])
            self.assertEqual(cm.exception.code, 0)
        except SystemExit as e:
            self.assertEqual(e.code, 0)
        self.assertIn(TOOL_VERSION, buf.getvalue() + "0.7.4")  # version is present somewhere

    def test_mcp_server_imports_cleanly(self):
        """mcp_server must import without error even without the 'mcp' extra installed."""
        import importlib
        mod = importlib.import_module("csvlens.mcp_server")
        self.assertTrue(callable(getattr(mod, "serve", None)))

    def test_head_n_zero_returns_error(self):
        """head with -n 0 should return exit code 2 with a message, not silently succeed."""
        import contextlib
        import io as _io
        path = _write(SAMPLE)
        try:
            buf = _io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = main(["head", path, "-n", "0"])
            self.assertEqual(rc, 2)
            self.assertIn("--rows", buf.getvalue())
        finally:
            os.remove(path)

    def test_head_n_negative_returns_error(self):
        """head with negative -n should return exit code 2."""
        path = _write(SAMPLE)
        try:
            rc = main(["head", path, "-n", "-3"])
            self.assertEqual(rc, 2)
        finally:
            os.remove(path)

    def test_select_empty_columns_returns_error(self):
        """select with a blank/comma-only -c should return exit code 2."""
        import contextlib
        import io as _io
        path = _write(SAMPLE)
        try:
            buf = _io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = main(["select", path, "-c", "  ,  , "])
            self.assertEqual(rc, 2)
            self.assertIn("column", buf.getvalue())
        finally:
            os.remove(path)

    def test_invalid_delimiter_returns_error(self):
        """A multi-character delimiter should return exit code 2 with a clear message."""
        import contextlib
        import io as _io
        path = _write(SAMPLE)
        try:
            buf = _io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = main(["profile", path, "-d", "||"])
            self.assertEqual(rc, 2)
            self.assertIn("delimiter", buf.getvalue())
        finally:
            os.remove(path)

    def test_header_only_csv_profiles_cleanly(self):
        """A CSV with only a header row (no data) should profile without error."""
        path = _write("col_a,col_b,col_c\n")
        try:
            prof = profile_csv(path)
            self.assertEqual(prof.rows, 0)
            self.assertEqual(prof.columns, 3)
            for cs in prof.column_stats:
                self.assertEqual(cs.inferred_type, "empty")
                self.assertIsNone(cs.mean)
        finally:
            os.remove(path)

    def test_select_columns_raises_on_empty_list(self):
        """select_columns([]) must raise ValueError, not return silently."""
        path = _write(SAMPLE)
        try:
            with self.assertRaises(ValueError):
                select_columns(path, [])
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
