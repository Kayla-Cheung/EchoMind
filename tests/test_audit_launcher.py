"""Windows launchers must work independently of their current directory."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt', 'Windows batch launcher')
class AuditLauncherTests(unittest.TestCase):
    def invoke(self, launcher, cwd):
        result = subprocess.run(['cmd.exe','/d','/c',str(launcher),'--help'], cwd=cwd,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
        self.assertEqual(result.returncode,0,result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
        self.assertIn(b'--scan-only',result.stdout)
        self.assertNotIn(b"can't open file",result.stderr)

    def test_repository_launcher_from_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory(prefix='echomind unrelated ') as tmp:
            self.invoke(ROOT/'start_data_audit_windows.bat',tmp)

    def test_copied_outer_launcher_without_a_sibling_repository(self):
        with tempfile.TemporaryDirectory(prefix='echomind desktop copy ') as tmp:
            launcher=Path(tmp)/'start_data_review.bat'
            shutil.copyfile(ROOT.parent/'start_data_review.bat',launcher)
            self.invoke(launcher,tmp)


if __name__=='__main__': unittest.main()
