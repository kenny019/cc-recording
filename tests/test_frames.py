import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "skills" / "recording" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import frames  # noqa: E402


class Helpers(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(frames.seconds("07:05"), 425)
        self.assertEqual(frames.seconds("1:02:03"), 3723)
        self.assertEqual(frames.seconds(12.5), 12.5)

    def test_refine_moves_to_quote(self):
        words = [{"text": w, "start": 1000 * i} for i, w in enumerate(
            "okay so here the bars are not aligned for some reason".split())]
        t, moved = frames.refine(0, "the bars are not aligned", words)
        self.assertTrue(moved)
        self.assertEqual(t, 3)

    def test_refine_keeps_t_without_match(self):
        words = [{"text": "hello", "start": 0}, {"text": "there", "start": 1000}]
        self.assertEqual(frames.refine(5, "something else entirely", words), (5, False))

    def test_selection_shape(self):
        k = frames.K
        band = (40 * k * 4 * k, 100 * k, 50 * k, 139 * k, 53 * k)  # 40 wide, 4 tall, full
        blob = (50 * 50 * k * k, 100 * k, 50 * k, 149 * k, 99 * k)  # square: webcam background
        self.assertTrue(frames.is_selection(band))
        self.assertFalse(frames.is_selection(blob))

    def test_cells_cover_box(self):
        self.assertEqual(frames.cells((0, 0, 0, 15, 7)), {(0, 0), (1, 0)})

    def test_same_box(self):
        self.assertTrue(frames.same_box((0, 10, 10, 60, 14), (0, 11, 10, 60, 14)))
        self.assertFalse(frames.same_box((0, 10, 10, 60, 14), (0, 10, 10, 200, 14)))

    def test_merge_joins_lines(self):
        a = (100, 10, 10, 60, 14)
        b = (80, 10, 18, 40, 22)
        far = (50, 300, 200, 340, 204)
        region = frames.merge([a, b, far])
        self.assertEqual(region[1:], [10, 10, 60, 22])


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class EndToEnd(unittest.TestCase):
    def test_audio_only_recording_stops_with_a_message(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            memo = d / "memo.m4a"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=d=1", str(memo)], check=True)
            (d / "candidates.json").write_text(json.dumps([{"id": "n01", "t": "00:00"}]))
            r = subprocess.run([sys.executable, str(SCRIPTS / "frames.py"), str(memo), str(d / "candidates.json")],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("no video", r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_finds_selection_and_ignores_pale_tile(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            video = d / "call.mp4"
            # 20 s of a white page. A pale blue "webcam tile" (greyer than a selection)
            # is on screen throughout; a selection band appears from 12 s to 15 s.
            draw = ",".join([
                "drawbox=x=1500:y=200:w=380:h=300:color=0xD6E4F8:t=fill",
                "drawbox=x=400:y=500:w=300:h=24:color=0xBEDAF8:t=fill:enable='between(t,12,15)'",
                "drawbox=x=410:y=508:w=280:h=6:color=0x333333:t=fill:enable='between(t,12,15)'",
            ])
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=1920x1080:d=20:r=10",
                            "-vf", draw, "-pix_fmt", "yuv420p", str(video)], check=True)
            cands = d / "candidates.json"
            cands.write_text(json.dumps([{"id": "a", "t": "00:11", "also": ["00:18"]}, {"id": "b", "t": "00:01"},
                                         {"id": "c", "t": "00:15", "frame": False}]))
            out = subprocess.run([sys.executable, str(SCRIPTS / "frames.py"), str(video), str(cands)],
                                 capture_output=True, text=True, check=True).stdout
            report = {r["id"]: r for r in json.loads((d / "frames" / "frames.json").read_text())}
            self.assertTrue(report["a"]["highlight"], out)
            x0, y0, x1, y1 = report["a"]["highlight_box"]
            self.assertTrue(380 <= x0 <= 420 and 680 <= x1 <= 720 and 480 <= y0 <= 520, report["a"])
            self.assertTrue((d / "frames" / "note-a-zoom.jpg").is_file())
            self.assertFalse(report["b"]["highlight"], out)
            self.assertTrue((d / "frames" / "note-b.jpg").is_file())
            self.assertFalse((d / "frames" / "burst").exists())
            self.assertEqual(report["a"]["also"], ["00:18"])
            self.assertEqual(report["c"], {"id": "c", "t": "00:15", "skipped": True})
            self.assertFalse((d / "frames" / "note-c.jpg").exists())

    def test_reads_the_shared_transcript_from_the_parent_folder(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            video = d / "call.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=640x360:d=12:r=5",
                            "-pix_fmt", "yuv420p", str(video)], check=True)
            words = [{"text": w, "start": 1000 * (3 + i)} for i, w in enumerate("the bars are not aligned".split())]
            (d / "transcript.json").write_text(json.dumps({"words": words}))
            task = d / "bugs"
            task.mkdir()
            (task / "candidates.json").write_text(json.dumps([{"id": "a", "t": "00:00", "quote": "the bars are not aligned"}]))
            subprocess.run([sys.executable, str(SCRIPTS / "frames.py"), str(video), str(task / "candidates.json")],
                           capture_output=True, check=True)
            report = json.loads((task / "frames" / "frames.json").read_text())[0]
            self.assertEqual(report["t_quote"], "00:03")

    def test_box_lands_on_the_selection_in_a_16_10_recording(self):
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            video = d / "call.mp4"
            draw = ",".join([
                "drawbox=x=400:y=900:w=300:h=24:color=0xBEDAF8:t=fill",
                "drawbox=x=410:y=908:w=280:h=6:color=0x333333:t=fill",
            ])
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=white:s=1920x1200:d=4:r=10",
                            "-vf", draw, "-pix_fmt", "yuv420p", str(video)], check=True)
            cands = d / "candidates.json"
            cands.write_text(json.dumps([{"id": "a", "t": "00:02"}]))
            subprocess.run([sys.executable, str(SCRIPTS / "frames.py"), str(video), str(cands)],
                           capture_output=True, check=True)
            report = json.loads((d / "frames" / "frames.json").read_text())[0]
            self.assertTrue(report["highlight"], report)
            x0, y0, x1, y1 = report["highlight_box"]
            self.assertTrue(380 <= x0 <= 420 and 680 <= x1 <= 720, report)
            self.assertTrue(880 <= y0 <= 920 and 910 <= y1 <= 940, report)


if __name__ == "__main__":
    unittest.main()
