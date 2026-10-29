"""Launcher lifecycle tests; no OCR or actual document conversion."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

spec = importlib.util.spec_from_file_location("launcher", Path(__file__).with_name("mineru_web_launcher.py"))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.clock = 0
        self.life = launcher.BrowserLifetime(lambda: self.clock)

    def test_refresh_reconnect_cancels_shutdown(self):
        self.life.connect("old")
        self.life.disconnect("old")
        self.clock = 29
        self.assertFalse(self.life.should_close())
        self.life.connect("new")
        self.clock = 90
        self.assertFalse(self.life.should_close())

    def test_last_tab_closes_after_30_seconds(self):
        self.life.connect("tab")
        self.life.disconnect("tab")
        self.clock = 29.9
        self.assertFalse(self.life.should_close())
        self.clock = 30
        self.assertTrue(self.life.should_close())
        self.assertFalse(self.life.connect("too_late"))

    def test_multiple_tabs_and_background_idle(self):
        self.life.connect("a")
        self.life.connect("b")
        self.life.disconnect("a")
        self.clock = 100000
        self.assertFalse(self.life.should_close())

    def test_startup_without_any_tab_has_longer_timeout(self):
        self.clock = 31
        self.assertFalse(self.life.should_close())
        self.clock = launcher.START_TIMEOUT
        self.assertTrue(self.life.should_close())

    def test_interruption_only_updates_current_running_jobs(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            runtime = Path(folder)
            for name, instance, status in [("active", "our", "running"),
                                            ("complete", "our", "completed_needs_review"),
                                            ("other", "other", "running")]:
                launcher.save(runtime / "runs" / (name + ".json"),
                              {"instance": instance, "status": status})
            launcher.interrupt_runs(runtime, "our", "browser closed")
            self.assertEqual(launcher.read(runtime / "runs/active.json")["status"], "interrupted")
            self.assertEqual(launcher.read(runtime / "runs/complete.json")["status"], "completed_needs_review")
            self.assertEqual(launcher.read(runtime / "runs/other.json")["status"], "running")

    def test_job_object_kills_only_owned_process_tree(self):
        import psutil
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            child_file = Path(folder) / "child.json"
            code = (
                "import sys,subprocess,time,json; from pathlib import Path; "
                "sys.stdin.readline(); "
                "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'],creationflags=0x08000000); "
                "Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid}));time.sleep(120)"
            )
            sentinel = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(120)"],
                                        creationflags=0x08000000)
            worker = None
            try:
                with launcher.windows_job() as assign:
                    worker = subprocess.Popen([sys.executable, "-c", code, str(child_file)],
                                              stdin=subprocess.PIPE, creationflags=0x08000000)
                    assign(worker)
                    worker.stdin.write(b"go\n")
                    worker.stdin.flush()
                    worker.stdin.close()
                    deadline = time.monotonic() + 10
                    while not child_file.exists() and time.monotonic() < deadline:
                        time.sleep(0.05)
                    self.assertTrue(child_file.exists())
                    child_pid = json.loads(child_file.read_text())["pid"]
                    self.assertTrue(psutil.pid_exists(child_pid))
                worker.wait(timeout=5)
                deadline = time.monotonic() + 5
                while psutil.pid_exists(child_pid) and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertFalse(psutil.pid_exists(child_pid))
                self.assertIsNone(sentinel.poll())
            finally:
                sentinel.terminate()
                sentinel.wait(timeout=5)
                if worker is not None and worker.poll() is None:
                    worker.terminate()
                    worker.wait(timeout=5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
