import contextlib
import fcntl
import http.server
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "skills" / "recording" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import prepare  # noqa: E402


class FakeAssemblyAI(http.server.BaseHTTPRequestHandler):
    """Just enough of the AssemblyAI v2 API: upload, transcribe, get, delete."""
    calls = []
    delete_status = 200

    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.calls.append(("POST", self.path))
        if self.path == "/v2/upload":
            self._send(200, {"upload_url": "https://fake/upload"})
        else:
            self._send(200, {"id": "job1", "status": "completed", "speech_model_used": "fake",
                             "language_code": "en", "words": [],
                             "utterances": [{"speaker": "A", "start": 0, "end": 1000, "text": "hello"}]})

    def do_DELETE(self):
        self.calls.append(("DELETE", self.path))
        if self.delete_status == 200:
            self._send(200, {"id": "job1", "status": "completed", "text": "Deleted by user."})
        else:
            self._send(self.delete_status, {"error": "boom"})


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class Prepare(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAssemblyAI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeAssemblyAI.calls = []
        FakeAssemblyAI.delete_status = 200
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.video = self.dir / "call.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", "-f", "lavfi", "-i",
                        "color=c=white:s=320x180:d=1", "-shortest", str(self.video)], check=True)
        self.out = self.dir / "call.recording"

    def run_prepare(self, *extra):
        argv = ["prepare.py", str(self.video), *extra]
        stdout = io.StringIO()
        with mock.patch.dict(prepare.HOSTS, {"us": self.base}), \
                mock.patch.dict("os.environ", {"ASSEMBLYAI_API_KEY": "test"}), \
                mock.patch.object(sys, "argv", argv), \
                mock.patch.object(prepare.time, "sleep"), \
                contextlib.redirect_stdout(stdout):
            try:
                prepare.main()
                return 0, stdout.getvalue()
            except SystemExit as e:
                return e.code, stdout.getvalue()

    def test_deletes_remote_copy(self):
        code, _ = self.run_prepare()
        self.assertEqual(code, 0)
        self.assertIn(("DELETE", "/v2/transcript/job1"), FakeAssemblyAI.calls)
        self.assertTrue((self.out / "transcript.json").is_file())
        self.assertEqual(sorted(p.name for p in self.out.iterdir() if p.name.startswith(".") and p.name != ".prepare.lock"), [])

    def test_failed_delete_is_retried_on_the_next_run(self):
        FakeAssemblyAI.delete_status = 500
        code, _ = self.run_prepare()
        self.assertNotEqual(code, 0)
        self.assertTrue((self.out / "transcript.json").is_file())

        FakeAssemblyAI.delete_status = 200
        FakeAssemblyAI.calls = []
        code, out = self.run_prepare()
        self.assertEqual(code, 0, out)
        self.assertEqual(FakeAssemblyAI.calls, [("DELETE", "/v2/transcript/job1")])

        FakeAssemblyAI.calls = []
        self.run_prepare()
        self.assertEqual(FakeAssemblyAI.calls, [], "a finished delete is not repeated")

    def test_job_left_by_an_interrupted_run_is_deleted_before_a_new_upload(self):
        self.out.mkdir()
        (self.out / ".remote-pending.json").write_text(json.dumps({"id": "old", "region": "us"}))
        code, out = self.run_prepare()
        self.assertEqual(code, 0, out)
        self.assertEqual(FakeAssemblyAI.calls[0], ("DELETE", "/v2/transcript/old"))
        self.assertIn(("DELETE", "/v2/transcript/job1"), FakeAssemblyAI.calls)
        self.assertFalse((self.out / ".remote-pending.json").exists())

    def test_records_when_the_call_started(self):
        code, out = self.run_prepare()
        self.assertEqual(code, 0, out)
        info = json.loads((self.out / "recording.json").read_text())
        self.assertEqual(info["duration_s"], 1.0)
        self.assertIn(info["start_source"], ("creation_time tag", "file creation time", "file modified time minus duration"))
        self.assertLess(info["start"], info["end"])

    def test_keep_remote_never_deletes(self):
        self.run_prepare("--keep-remote")
        self.run_prepare()
        self.assertNotIn("DELETE", [m for m, _ in FakeAssemblyAI.calls])

    def test_second_run_on_the_same_folder_waits_its_turn(self):
        self.out.mkdir()
        with open(self.out / ".prepare.lock", "w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, _ = self.run_prepare()
        self.assertNotEqual(code, 0)
        self.assertIn("already running", str(code))
        self.assertEqual(FakeAssemblyAI.calls, [])
        self.assertFalse((self.out / "audio.mp3").exists())

    def test_no_partial_files_under_final_names(self):
        code, _ = self.run_prepare()
        self.assertEqual(code, 0)
        self.assertEqual(sorted(p.name for p in self.out.iterdir() if ".part" in p.name), [])


if __name__ == "__main__":
    unittest.main()
