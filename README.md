# cc-recording

A Claude Code plugin that turns a screen recording of a call into confirmed,
timestamped output for a task you choose. Every item it produces carries a
timestamp, the words behind it and the screen frame that was showing. Unclear
points are asked, not guessed, and nothing touches a repo or gets sent until
you say go.

## Install

In Claude Code:

```
/plugin marketplace add kenny019/cc-recording
/plugin install recording@cc-recording
```

Requires `python3` (standard library only), `ffmpeg`/`ffprobe` on the PATH,
and an [AssemblyAI](https://www.assemblyai.com) API key in
`ASSEMBLYAI_API_KEY` (environment, or `.env.local`/`.env` in the directory you
run Claude from).

## Use

```
/recording <video> [preset or task]
```

| Task | For | You get | On "go" |
|---|---|---|---|
| `review` (default) | Someone walks through your app and says what to change | `notes.md`: changes, not-code items, approvals | One commit per change, pushed as a PR |
| `bugs` | A user or tester tries the product | `bugs.md`: bugs with steps, friction, requests | GitHub issues, or fixes on a branch |
| `docs` | Someone demos a flow | `guide.md`: a how-to with a screenshot per step | The guide added where you say |
| `meeting` | A planning, sales or team call | `meeting.md`: decisions, action items, open questions | Tasks or a follow-up draft, after you confirm |
| anything else | Whatever you describe | A file shaped for the task | What the task needs, after you confirm |

Examples:

```
/recording ~/Movies/call.mp4
/recording ~/Movies/call.mp4 review the designer, target feat/onboarding
/recording ~/Movies/onboarding.mp4 bugs the tester's first session
/recording ~/Movies/demo.mp4 docs for new coaches
/recording ~/Movies/sales.mp4 list every question the client asked about pricing
```

How it works:

1. **Transcribe.** The audio track goes to AssemblyAI with speaker labels. The
   transcript is deleted at AssemblyAI once it is saved locally; a failed
   delete is retried on the next run.
2. **Find the moments** the task cares about in the transcript.
3. **Look at the screen.** For each moment, a short burst of frames is pulled
   and the frame where someone selected text on screen is kept, with a zoomed
   crop. Selecting what you talk about makes this much more precise.
4. **Sort and ask.** Claude checks the repo or tracker where it can, then asks
   about unclear points a few at a time.
5. **Write the output** and stop.
6. **Go.** Only when you say so.

Everything for a run is saved next to the video, in
`<video name>.recording/<task>/`, never inside a repo. Several tasks on the
same video share one transcript.

## Privacy

- The **audio** leaves your machine, to AssemblyAI. On their free tier,
  uploaded audio may be used for model training. Pass `--region eu` to
  `prepare.py` (or ask Claude to) to keep data in the EU and out of training,
  per [AssemblyAI's docs](https://www.assemblyai.com/docs/data-retention-and-model-training).
- The **video and frames** stay local. Frames Claude looks at are sent to the
  model as part of the conversation, like any image.
- If a call shows customer data or private conversations, decide before running
  it whether that is acceptable. The `bugs` and `docs` tasks list frames with
  personal data so they are kept out of issues and guides.

## Tips for the call

- Share the app window or screen and talk through it.
- Select the text you are talking about with the mouse. It is the strongest
  signal of what each point refers to.

## Tests

```bash
python3 -m unittest discover -s tests
```

## License

MIT
