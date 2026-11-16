#!/usr/bin/env python3
"""Extract a recording's audio and transcribe it with AssemblyAI.

The recording is a screen recording or an audio file (.m4a, .mp3, .wav, ...).

Writes <out>/audio.mp3, <out>/transcript.json and <out>/transcript.txt, then
deletes the transcript at AssemblyAI so the local copy is the only one.
Re-running reuses the local transcript and uploads nothing, and retries the
AssemblyAI delete if an earlier run could not finish it.
"""
import argparse
import collections
import datetime
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOSTS = {"us": "https://api.assemblyai.com", "eu": "https://api.eu.assemblyai.com"}
LONG_AUDIO_S = 2 * 3600


def fail(msg):
    sys.exit(f"error: {msg}")


def find_key(env_file):
    if os.environ.get("ASSEMBLYAI_API_KEY"):
        return os.environ["ASSEMBLYAI_API_KEY"].strip()
    candidates = [pathlib.Path(env_file)] if env_file else [pathlib.Path(".env.local"), pathlib.Path(".env")]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[len("export "):]
            if line.startswith("ASSEMBLYAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    fail("ASSEMBLYAI_API_KEY not found. Set it in the environment or pass --env-file.")


def probe_duration(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        fail(f"ffprobe could not read {video}: {out.stderr.strip()}")
    return float(out.stdout.strip())


def has_video(path):
    """True when the file has a picture to pull frames from. Cover art attached
    to an audio file is a still image, not a recording of the screen."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream_disposition=attached_pic",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.split()
    return "0" in out


def call_start(video, duration):
    """When the call started: the container's creation_time tag, else the
    file's creation time, else its last write minus the duration."""
    tag = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    ).stdout.strip()
    if tag:
        try:
            return datetime.datetime.fromisoformat(tag.replace("Z", "+00:00")).astimezone(), "creation_time tag"
        except ValueError:
            pass
    st = video.stat()
    if getattr(st, "st_birthtime", None):
        return datetime.datetime.fromtimestamp(st.st_birthtime).astimezone(), "file creation time"
    return datetime.datetime.fromtimestamp(st.st_mtime - duration).astimezone(), "file modified time minus duration"


def clock(ms, hours):
    s = ms // 1000
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if hours else f"{s // 60:02d}:{s % 60:02d}"


class Api:
    def __init__(self, host, key):
        self.host, self.key = host, key

    def call(self, path, data=None, content_type=None, method=None):
        headers = {"authorization": self.key}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self.host + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            fail(f"AssemblyAI {method or ('POST' if data else 'GET')} {path} returned {e.code}: {e.read().decode(errors='replace')[:500]}")


def write_atomic(path, text):
    part = path.with_name(path.name + ".part")
    part.write_text(text)
    os.replace(part, path)


def lock(out):
    """Hold an exclusive lock on the output folder for the whole run, so a
    second run on the same video cannot start a duplicate paid job or upload
    half-written audio. Released when the process exits."""
    handle = open(out / ".prepare.lock", "w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        fail(f"prepare.py is already running for {out}. Wait for it to finish.")
    return handle


def delete_remote(out, env_file):
    """Delete the AssemblyAI copy named in <out>/.remote-pending.json, then
    forget it. The marker is written before the transcript is saved, so an
    interrupted or failed delete is retried on the next run."""
    marker = out / ".remote-pending.json"
    if not marker.is_file():
        return
    pending = json.loads(marker.read_text())
    api = Api(HOSTS[pending["region"]], find_key(env_file))
    gone = api.call(f"/v2/transcript/{pending['id']}", method="DELETE")
    marker.unlink()
    print(f"deleted the transcript at AssemblyAI (status: {gone.get('status')}, text now: {str(gone.get('text'))[:40]!r})")


def transcribe(api, audio, max_speakers, on_job):
    upload = api.call("/v2/upload", audio.read_bytes(), "application/octet-stream")
    body = {
        "audio_url": upload["upload_url"],
        "speaker_labels": True,
        "speaker_options": {"min_speakers_expected": 1, "max_speakers_expected": max_speakers},
        "language_detection": True,
    }
    job = api.call("/v2/transcript", json.dumps(body).encode(), "application/json")
    on_job(job["id"])
    print(f"transcribing (job {job['id']})...", flush=True)
    while job["status"] not in ("completed", "error"):
        time.sleep(5)
        job = api.call(f"/v2/transcript/{job['id']}")
    return job


def main():
    held = []
    try:
        run(held)
    finally:
        for handle in held:
            handle.close()


def run(held):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("video")
    p.add_argument("--out", help="output folder (default: <video>.recording next to the video)")
    p.add_argument("--env-file", help="file holding ASSEMBLYAI_API_KEY= (default: env var, then ./.env.local, ./.env)")
    p.add_argument("--region", choices=sorted(HOSTS), default="us")
    p.add_argument("--max-speakers", type=int, default=4)
    p.add_argument("--keep-remote", action="store_true", help="do not delete the transcript at AssemblyAI")
    p.add_argument("--yes", action="store_true", help=f"allow audio longer than {LONG_AUDIO_S // 3600} h")
    a = p.parse_args()

    video = pathlib.Path(a.video).expanduser().resolve()
    if not video.is_file():
        fail(f"no such file: {video}")
    out = pathlib.Path(a.out).expanduser().resolve() if a.out else video.with_name(video.stem + ".recording")
    out.mkdir(parents=True, exist_ok=True)
    held.append(lock(out))  # released by main() when the run ends, failed or not
    duration = probe_duration(video)
    start, source = call_start(video, duration)
    picture = has_video(video)
    kind = "video" if picture else "audio only"
    print(f"{kind}: {video.name}, {duration / 60:.1f} min, started {start:%Y-%m-%d %H:%M %Z} ({source})")
    write_atomic(out / "recording.json", json.dumps({
        "video": str(video), "has_video": picture, "duration_s": round(duration, 1),
        "start": start.isoformat(timespec="seconds"), "start_source": source,
        "end": (start + datetime.timedelta(seconds=duration)).isoformat(timespec="seconds"),
    }, indent=1))
    print(f"output: {out}")

    tjson = out / "transcript.json"
    started = time.time()
    if tjson.is_file():
        job = json.loads(tjson.read_text())
        print("reusing existing transcript.json (nothing uploaded)")
        if not a.keep_remote:
            delete_remote(out, a.env_file)
    else:
        if duration > LONG_AUDIO_S and not a.yes:
            fail(f"audio is {duration / 3600:.1f} h, over the {LONG_AUDIO_S // 3600} h guard. Re-run with --yes to transcribe it.")
        key = find_key(a.env_file)
        if not a.keep_remote:
            delete_remote(out, a.env_file)  # a job an interrupted run left behind
        audio = out / "audio.mp3"
        if not audio.is_file():
            part = out / "audio.part.mp3"
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(part)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                part.unlink(missing_ok=True)
                fail(f"ffmpeg audio extraction failed: {r.stderr.strip()}")
            os.replace(part, audio)
        print(f"audio: {audio.stat().st_size / 1e6:.1f} MB, uploading to AssemblyAI ({a.region.upper()})", flush=True)
        api = Api(HOSTS[a.region], key)
        def remember(job_id):
            if not a.keep_remote:
                write_atomic(out / ".remote-pending.json", json.dumps({"id": job_id, "region": a.region}))
        job = transcribe(api, audio, a.max_speakers, remember)
        if job["status"] != "completed":
            fail(f"transcription failed: {job.get('error')}")
        write_atomic(tjson, json.dumps(job, indent=1))
        if a.keep_remote:
            print("kept the transcript at AssemblyAI (--keep-remote)")
        else:
            delete_remote(out, a.env_file)

    utts = job.get("utterances") or []
    hours = duration >= 3600
    lines = [f"[{clock(u['start'], hours)}-{clock(u['end'], hours)}] {u['speaker']}: {u['text']}" for u in utts]
    write_atomic(out / "transcript.txt", "\n".join(lines) + "\n")

    talk = collections.Counter()
    count = collections.Counter()
    for u in utts:
        talk[u["speaker"]] += (u["end"] - u["start"]) / 1000
        count[u["speaker"]] += 1
    print(f"model: {job.get('speech_model_used')}, language: {job.get('language_code')}, utterances: {len(utts)}")
    for spk, secs in talk.most_common():
        print(f"  speaker {spk}: {secs / 60:.1f} min talking, {count[spk]} turns")
    print(f"transcript: {out / 'transcript.txt'} ({time.time() - started:.0f} s)")


if __name__ == "__main__":
    main()
