#!/usr/bin/env python3
"""Pull the screen frame that goes with each moment in a recording.

For every candidate moment it grabs a short burst of frames around it, looks
for a text-selection highlight (people often select the text they talk
about), and keeps the best frame plus a zoomed crop around the highlight.

candidates.json: [{"id": "n01", "t": "07:00", "quote": "the bars are not aligned"}, ...]
  t     mm:ss, h:mm:ss or seconds; the utterance start is fine.
  also  optional list of later timestamps where the same point came back; kept
        in frames.json for the write-up, not used for frames.
  frame optional; false skips this moment (nothing on screen matters).
  quote optional; words that were said. When a transcript.json is found (next
        to candidates.json, in its parent folder, or via --transcript), t is
        moved to where those words were spoken.
"""
import argparse
import collections
import json
import pathlib
import re
import shutil
import subprocess
import sys

SW, SH = 960, 540  # detection size; SH is reset per video to keep its aspect ratio
K = SW // 480  # shape thresholds below were tuned at 480 wide


def fail(msg):
    sys.exit(f"error: {msg}")


def seconds(t):
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).strip().split(":")]
    s = 0.0
    for p in parts:
        s = s * 60 + p
    return s


def clock(s):
    s = int(round(s))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        fail(f"{cmd[0]} failed: {r.stderr.decode(errors='replace').strip()[:500]}")
    return r.stdout


def norm(text):
    return re.findall(r"[a-z0-9']+", text.lower())


def refine(t, quote, words):
    """Move t to where the quote's opening words were spoken, near t."""
    want = norm(quote)[:6]
    if len(want) < 2 or not words:
        return t, False
    best, best_score = None, 0
    toks = [(norm(w["text"]) or [""])[0] for w in words]
    for i, w in enumerate(words):
        ws = w["start"] / 1000
        if ws < t - 5 or ws > t + 90:
            continue
        score = sum(1 for k, tok in enumerate(want) if i + k < len(toks) and toks[i + k] == tok)
        if score > best_score or (score == best_score and best is not None and abs(ws - t) < abs(best - t)):
            best, best_score = ws, score
    if best is not None and best_score >= max(2, len(want) // 2 + 1):
        return best, True
    return t, False


def mask_of(planar, target, tol):
    """1 where a pixel has the selection colour. planar is ffmpeg gbrp (G, B, R planes).

    Each channel is tested with a lookup table and the three results ANDed as
    big integers, which keeps this fast in plain Python. The red range is the
    one that matters most: a pale blue webcam background is close in green and
    blue but noticeably redder (greyer)."""
    n = SW * SH
    tr, tg, tb = target
    def plane(i, centre, lo_extra=0, hi_extra=0):
        table = bytes(1 if centre - tol - lo_extra <= v <= centre + tol + hi_extra else 0 for v in range(256))
        return int.from_bytes(planar[i * n:(i + 1) * n].translate(table), "big")
    m = plane(0, tg) & plane(1, tb, 4, 255) & plane(2, tr)
    return m.to_bytes(n, "big")


def components(mask):
    seen = bytearray(SW * SH)
    found = []
    s = mask.find(1)
    while s != -1:
        if not seen[s]:
            stack, seen[s] = [s], 1
            n, x0, y0, x1, y1 = 0, SW, SH, 0, 0
            while stack:
                k = stack.pop()
                y, x = divmod(k, SW)
                n += 1
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
                for dy in (-1, 0, 1):
                    yy = y + dy
                    if not 0 <= yy < SH:
                        continue
                    for dx in (-2, -1, 0, 1, 2):
                        xx = x + dx
                        if 0 <= xx < SW:
                            j = yy * SW + xx
                            if mask[j] and not seen[j]:
                                seen[j] = 1
                                stack.append(j)
            if n >= 12 * K * K:
                found.append((n, x0, y0, x1, y1))
        s = mask.find(1, s + 1)
    return found


def is_selection(c):
    """A selection is a short, wide, fairly filled band (text cuts the fill)."""
    n, x0, y0, x1, y1 = c
    w, h = x1 - x0 + 1, y1 - y0 + 1
    # One line of text: at least 3x as wide as tall. Taller (several lines) must
    # be much wider, which rules out squarish patches of a pale webcam background.
    wide = w >= 3 * h and (h <= 6 * K or w >= 6 * h)
    return 2 * K <= h <= 40 * K and w >= 8 * K and wide and n / (w * h) >= 0.33


def cells(c, size=8):
    """The grid cells (size px at detection scale) a blob's box covers."""
    return {(x, y) for x in range(c[1] // size, c[3] // size + 1) for y in range(c[2] // size, c[4] // size + 1)}


def same_box(a, b):
    """True when two blobs cover nearly the same box (an unchanged selection)."""
    ix = min(a[3], b[3]) - max(a[1], b[1]) + 1
    iy = min(a[4], b[4]) - max(a[2], b[2]) + 1
    if ix <= 0 or iy <= 0:
        return False
    area = lambda c: (c[3] - c[1] + 1) * (c[4] - c[2] + 1)
    return ix * iy / max(area(a), area(b)) >= 0.8


def on_backdrop(band, comps):
    """True when a band touches a much bigger patch of the same colour that is
    not text-shaped, such as a pale blue webcam background around a person."""
    m = 8 * K
    for c in comps:
        if c is band or c[0] < 3 * band[0] or is_selection(c):
            continue
        if c[1] - m <= band[3] and band[1] <= c[3] + m and c[2] - m <= band[4] and band[2] <= c[4] + m:
            return True
    return False


def merge(blobs):
    """Join selection bands on neighbouring lines into one region."""
    blobs = sorted(blobs, key=lambda c: c[2])
    regions = []
    for n, x0, y0, x1, y1 in blobs:
        for r in regions:
            if y0 - r[4] <= 6 * K and x0 <= r[3] + 10 * K and x1 >= r[1] - 10 * K:
                r[0] += n
                r[1], r[2], r[3], r[4] = min(r[1], x0), min(r[2], y0), max(r[3], x1), max(r[4], y1)
                break
        else:
            regions.append([n, x0, y0, x1, y1])
    return max(regions, key=lambda r: r[0]) if regions else None


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video")
    p.add_argument("candidates")
    p.add_argument("--out", help="output folder (default: frames/ next to candidates.json)")
    p.add_argument("--before", type=float, default=2.0, help="seconds before t (default 2)")
    p.add_argument("--after", type=float, default=5.0, help="seconds after t (default 5)")
    p.add_argument("--fps", type=float, default=2.0, help="burst frame rate (default 2)")
    p.add_argument("--highlight", default="190,218,248", help="selection colour as r,g,b (default: macOS blue as seen through Meet)")
    p.add_argument("--tolerance", type=int, default=10, help="per-channel colour tolerance (default 10)")
    p.add_argument("--transcript", help="transcript.json (default: next to candidates.json, else its parent folder)")
    p.add_argument("--keep-burst", action="store_true")
    a = p.parse_args()

    video = pathlib.Path(a.video).expanduser().resolve()
    cand_path = pathlib.Path(a.candidates).expanduser().resolve()
    out = pathlib.Path(a.out).expanduser().resolve() if a.out else cand_path.parent / "frames"
    out.mkdir(parents=True, exist_ok=True)
    target = tuple(int(v) for v in a.highlight.split(","))
    cands = json.loads(cand_path.read_text())
    if a.transcript:
        tjson = pathlib.Path(a.transcript).expanduser().resolve()
    else:
        tjson = next((d / "transcript.json" for d in (cand_path.parent, cand_path.parent.parent)
                      if (d / "transcript.json").is_file()), None)
    words = json.loads(tjson.read_text()).get("words", []) if tjson and tjson.is_file() else []
    if not words:
        print("no transcript.json with word timings found; using t as given")

    w, h = (int(v) for v in run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height", "-of", "csv=p=0", str(video)]).decode().strip().split(","))
    global SH
    SH = max(2, round(SW * h / w / 2) * 2)  # same aspect as the video, even for ffmpeg
    sx, sy = w / SW, h / SH

    skipped = [c for c in cands if c.get("frame") is False]
    cands = [c for c in cands if c.get("frame") is not False]
    notes = []
    for c in cands:
        t0 = seconds(c["t"])
        t, moved = refine(t0, c.get("quote", ""), words)
        start = max(0.0, t - a.before)
        burst = out / "burst" / str(c["id"])
        if burst.exists():
            shutil.rmtree(burst)
        burst.mkdir(parents=True)
        run(["ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-i", str(video), "-t", f"{a.before + a.after:.2f}",
             "-vf", f"fps={a.fps}", "-q:v", "3", str(burst / "f_%03d.jpg")])
        files = sorted(burst.glob("f_*.jpg"))
        if not files:
            fail(f"no frames for {c['id']} at {clock(t)} (past the end of the video?)")
        raw = run(["ffmpeg", "-v", "error", "-i", str(burst / "f_%03d.jpg"), "-vf", f"scale={SW}:{SH}",
                   "-f", "rawvideo", "-pix_fmt", "gbrp", "-"])
        size = SW * SH * 3
        frames = []
        for i, f in enumerate(files):
            comps = components(mask_of(raw[i * size:(i + 1) * size], target, a.tolerance))
            blobs = [b for b in comps if is_selection(b) and not on_backdrop(b, comps)]
            frames.append({"file": f, "t": start + i / a.fps, "blobs": blobs, "comps": comps})
        notes.append({"c": c, "t0": t0, "t": t, "moved": moved, "frames": frames, "burst": burst})

    # Screen cells that show the selection colour in many different notes are
    # call chrome (Meet's pale blue "Presenting" pill, a webcam background),
    # not a selection, even when they break into differently sized fragments.
    cell_notes = collections.Counter()
    for n in notes:
        cell_notes.update({cell for fr in n["frames"] for c in fr["comps"] for cell in cells(c)})
    min_notes = max(3, 0.25 * len(notes))
    chrome_cells = {cell for cell, k in cell_notes.items() if k >= min_notes}

    def chrome(b):
        own = cells(b)
        return len(own & chrome_cells) >= 0.5 * len(own)

    report = []
    for n in notes:
        # Prefer a selection made during this note over one still showing from
        # before it (unchanged since the burst's first frame).
        before = [b for b in n["frames"][0]["blobs"] if not chrome(b)]
        best = None
        for idx, fr in enumerate(n["frames"]):
            live = [b for b in fr["blobs"] if not chrome(b)]
            fresh = [b for b in live if idx == 0 or not any(same_box(b, o) for o in before)]
            region = merge(fresh) if idx and fresh else merge(live)
            is_fresh = bool(idx and fresh)
            score = region[0] if region else 0
            key = (is_fresh, score, -abs(fr["t"] - n["t"]))
            if best is None or key > best[0]:
                best = (key, fr, region)
        (carried, _, _), fr, region = best
        carried = bool(region) and not carried
        if not region:
            fr = min(n["frames"], key=lambda f: abs(f["t"] - n["t"]))
        nid = n["c"]["id"]
        full = out / f"note-{nid}.jpg"
        shutil.copyfile(fr["file"], full)
        entry = {
            "id": nid, "t": clock(n["t0"]), "t_quote": clock(n["t"]) if n["moved"] else None,
            "frame_t": clock(fr["t"]), "highlight": bool(region), "frame": str(full),
        }
        if n["c"].get("also"):
            entry["also"] = n["c"]["also"]
        if region:
            _, x0, y0, x1, y1 = region
            bx0, by0, bx1, by1 = int(x0 * sx), int(y0 * sy), int((x1 + 1) * sx), int((y1 + 1) * sy)
            cw, ch = max(bx1 - bx0 + 400, 900), max(by1 - by0 + 300, 450)
            cw, ch = min(cw, w), min(ch, h)
            cx = min(max(0, (bx0 + bx1) // 2 - cw // 2), w - cw)
            cy = min(max(0, (by0 + by1) // 2 - ch // 2), h - ch)
            zoom = out / f"note-{nid}-zoom.jpg"
            run(["ffmpeg", "-v", "error", "-y", "-i", str(full), "-vf", f"crop={cw}:{ch}:{cx}:{cy}", "-q:v", "2", str(zoom)])
            entry["highlight_box"] = [bx0, by0, bx1, by1]
            entry["carried_over"] = carried
            entry["zoom"] = str(zoom)
        report.append(entry)
        if not a.keep_burst:
            shutil.rmtree(n["burst"])
        mark = ("highlight, already there before the note" if carried else "highlight") if region else "no highlight"
        moved = f" (quote at {entry['t_quote']})" if n["moved"] else ""
        print(f"{nid}: t {entry['t']}{moved}, frame {entry['frame_t']}, {mark}")
    if not a.keep_burst and (out / "burst").exists() and not any((out / "burst").iterdir()):
        (out / "burst").rmdir()
    report += [{"id": c["id"], "t": clock(seconds(c["t"])), "skipped": True, **({"also": c["also"]} if c.get("also") else {})}
               for c in skipped]
    (out / "frames.json").write_text(json.dumps(report, indent=1))
    found = sum(bool(r.get("highlight")) for r in report)
    print(f"{found}/{len(notes)} moments have a selection highlight ({len(skipped)} skipped); details in {out / 'frames.json'}")


if __name__ == "__main__":
    main()
