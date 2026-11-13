# Preset: docs

Someone demos a flow on a call ("let me show you how to..."). The output is a
how-to guide with a screenshot per step. Details may name the audience (end
users, new staff, developers) and where the guide should end up.

## Moments

Every step of the flow: each click, page change, field filled or choice
made, in order. Also every tip ("you can also..."), warning ("don't do X
before Y") and prerequisite ("you need admin rights"). Skip small talk and
detours that are not part of the flow, but note detours that show a second
way to do a step.

## Groups

1. **Step**: in order; each needs a screenshot.
2. **Tip or warning**: attached to the step it belongs to.
3. **Prerequisite**: goes at the top.
4. **Unclear** (working group): a step that happened off screen, too fast, or two ways were
   shown and it is not clear which to document. Asked with AskUserQuestion.

## Frames

Frames are the output here. For each step pick the frame that shows the state
the reader needs to recognise (often just after the click, so try
`--after 3`). Read every step frame. Copy the chosen ones to
`<task folder>/images/step-01.jpg`, `step-02.jpg`, ... and crop with ffmpeg to
the app window when the call layout (webcam tiles, the meeting toolbar) is
around it. List any frame that shows personal data (names, emails, real
customer records) under "Needs redaction"; never publish those as they are.

## Check

When the guide is for a product in a repo, check the UI copy in the repo so
button and page names in the guide match the code, and note any step where
the recording and the current code differ (the UI has changed since).

## Output: `guide.md`

```markdown
# How to <task>

For: <audience>. Before you start: <prerequisites>.

1. **<Action in the imperative>.** <one or two sentences>.
   ![<what the screenshot shows>](images/step-01.jpg)
   > Tip: <...>

## Source
Recorded <date>, <video file name>. Steps from [mm:ss] to [mm:ss].

## Needs redaction
- images/step-04.jpg: <what> 

## Questions asked
- [03:20] <question> -> <answer>
```

## On go

Ask where the guide should go (a docs folder in a repo, a help center draft,
a shared doc), then adapt it to that place's format and conventions. In a
repo, follow its docs layout and open a PR. Redact or retake the screenshots
listed under "Needs redaction" first.
