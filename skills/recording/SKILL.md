---
name: recording
description: Turn a screen recording of a call into confirmed, timestamped output for a task the user chooses (review notes, bug reports, a how-to guide, meeting decisions, or anything they describe), each item backed by the speaker's words and the screen frame behind it. Use when the user gives a call or screen recording and a task to do with it.
argument-hint: <video.mp4> [review | bugs | docs | meeting | a task in your own words]
disable-model-invocation: true
---

# Recording to confirmed output

A recording goes in, with a task. Out comes a file where every item has a
timestamp, the words behind it and the screen frame that was showing. Unclear
points are asked, not guessed. Anything that changes a repo, posts or sends
waits for the user's go.

## The task

Arguments: `$ARGUMENTS`. The first is the video path (ask for it if missing).
The rest is the task:

- Nothing: the `review` preset.
- Starts with a preset name: that preset; any words after it are details
  (a person's name, the target repo or branch, a focus). For example
  `review the designer, target feat/onboarding` or `bugs the tester's checkout session`.
- Anything else: a free-text task, for example `list every question the
  client asked about pricing`.

Presets, in `${CLAUDE_SKILL_DIR}/presets/`:

| Preset | For | Output |
|---|---|---|
| `review.md` | Someone walks through an app and says what to change | `notes.md`, then code changes on go |
| `bugs.md` | A user or tester tries the product | `bugs.md`, then issues or fixes on go |
| `docs.md` | Someone demos a flow | `guide.md` with screenshots, then into a repo on go |
| `meeting.md` | A planning, sales or team call | `meeting.md`, then tasks or a summary on go |

Read the chosen preset in full before step 2. Each has six sections: Moments
(what counts), Groups, Frames (which matter), Check (what to verify and
against what), Output (file name and template) and On go. For a free-text
task, write those six yourself as a short brief, show it to the user in a few
lines, and carry on (ask with AskUserQuestion first only if the task can be
read two very different ways). Name the output file after the task, for
example `pricing-questions.md`. If a free-text task is close to a preset,
start from that preset and adapt it.

**Target repo.** The one the task details name; else the current directory
when the call is about that project; else none. Ask if it matters and is not
clear.

Each task works in its own folder, `<video name>.recording/<task>/`, where
`<task>` is the preset name or a short slug of the free-text task. The
transcript is shared by all tasks on the same video.

Requires `ffmpeg`/`ffprobe` and an AssemblyAI key in `ASSEMBLYAI_API_KEY`
(environment, or a `.env.local`/`.env` in the current directory, or
`--env-file`).

## 0. Say where the data goes, first

Before running anything, tell the user in one or two lines:

- The audio track is uploaded to AssemblyAI (US endpoint) for transcription.
  On AssemblyAI's free tier, uploaded audio may be used for model training.
  The transcript is deleted at AssemblyAI as soon as it is saved locally.
- The video and frames stay on this machine. Frames you look at go to the
  model as part of this conversation, like any image.
- If the call shows customer data or private conversations, they should say
  so now. `--region eu` keeps data in the EU and out of training.

Then continue without waiting, unless they object. Skip this when the
transcript already exists (nothing is uploaded).

## 1. Transcribe

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/prepare.py" "<video>"
```

Writes to `<video name>.recording/` next to the video (never inside a repo):
`transcript.json`, `transcript.txt` (`[mm:ss-mm:ss] A: text`), `audio.mp3`
(when it uploads) and `recording.json` with when the call started and ended.
It prints how long each speaker talked. Re-running reuses the transcript and
uploads nothing; if an earlier run could not delete the AssemblyAI copy, it
retries that delete. Only one run per video at a time: a second one stops
with a message. Audio over 2 hours stops with a message; re-run with `--yes`
only after the user agrees. Run it in the background if the call is long.

## 2. Find the moments

Read `transcript.txt` in full.

- Work out who is who from what is said (names, roles, who is sharing the
  screen). Match any person the task names to a speaker letter. If it is not
  clear and it matters for the task, ask with AskUserQuestion.
- Walk the transcript in order and list every moment the preset (or your
  brief) counts. Long utterances often hold several moments; give each its own
  entry. A point that comes back later and is settled there is one moment
  with both timestamps.
- Write `<task folder>/candidates.json`:

```json
[{"id": "n01", "t": "00:19", "quote": "I will remove the review the transcript", "speaker": "A"},
 {"id": "n02", "t": "09:09", "quote": "20 of 27 needed", "speaker": "A", "also": ["24:17"]},
 {"id": "n03", "t": "04:12", "quote": "start paying when we launch", "speaker": "A", "frame": false}]
```

`also` lists later timestamps where the same point came back. `"frame":
false` skips the frame step for a moment the transcript settles alone
(pricing, vendors, plans, process).

`t` is the start of the utterance that holds the moment; `quote` is the exact
words for it (5 to 10, copied from that utterance). The frame step looks for
the quote from 5 s before `t` to 90 s after and moves to the second it was
said, so keep the quote distinctive.

## 3. Look at the screen

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/frames.py" "<video>" "<task folder>/candidates.json"
```

For each moment it takes a short burst of frames (2 s before to 5 s after),
looks for a text-selection highlight (people often select the text they are
talking about), and writes `<task folder>/frames/note-<id>.jpg`, plus
`note-<id>-zoom.jpg` when it found a highlight. `frames/frames.json` lists
which have one. It takes seconds. `--before`/`--after` widen the burst.

- With a zoom: read it first. Check it really is selected text; a pale blue
  webcam tile can fool the detector, and then the full frame is the one to
  read. `"carried_over": true` means the selection was already on screen
  before the moment began, so it may belong to the previous one.
- Without a zoom: read the full frame when the moment is about something on
  screen. Use the cursor, open dialogs and the quote.
- Moments marked `"frame": false` have no frame; the preset decides which
  (in `docs`, every step needs one).

One or two images per moment at most.

## 4. Sort, check, ask

Sort the moments into the preset's groups, each item with its timestamp.
"Unclear" is a working group: once asked, each item moves to its final group
and the question and answer go under "Questions asked". The output has no
Unclear section.

Before asking anything, do the preset's Check. Times come from
`recording.json`:

- **What was true at the call** (to judge what someone said about the code):
  the target repo as of the call's start, `git log --until=<start>` and
  `git show <sha>:<path>`.
- **What changed since** (to find work already done): `git log
  --since=<start>` on the target branch. Commits from before the call that day
  are not "since".

An answer built on a wrong assumption costs a second round.

Ask about the unclear items with AskUserQuestion, at most 4 questions per
call. Each question stands alone: the timestamp, the words, what the frame
shows, and the likely readings as options with your recommendation first. Do
not list the unclear items in prose instead.

When the answers arrive, check them against what you found. If an answer
rests on something the code or data contradicts, say so and ask again.

## 5. Write the output and stop

Write the preset's output file in the task folder, using its template. Do not
reuse the names `candidates.json`, `frames/`, `transcript.*` or
`recording.json`. Every
item carries its timestamp(s), the words behind it (a short quote), and the
frame path when a frame was used. Keep a "Questions asked" section with the
answers.

Then give the user the counts per group and the path to the file, and stop.
Say what "go" would do for this task.

## 6. On "go"

Only when the user says so, do what the preset's "On go" section says (or what
your brief said for a free-text task). Before anything that writes outside the
task folder, changes a repo, posts or sends, follow that repo's own rules
(CLAUDE.md, AGENTS.md, contribution guide). Keep transcript quotes out of
anything shared beyond a few words: the call may include private content.
Report back with links and anything skipped.
