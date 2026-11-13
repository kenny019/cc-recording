# Preset: review

Someone (the reviewer) walks through an app on a call and says what to change.
Details after the preset name may give the reviewer's name and the target repo
or branch (default: the current directory and branch).

## Moments

Every moment where the reviewer asks for a change, reports something wrong,
questions a behaviour, or raises something to follow up. Also what they
explicitly approved ("this is okay"), briefly, so nothing is lost. A change
the other speaker proposes and the reviewer accepts ("remove the length,
right?" "Yes") counts; quote the reviewer's acceptance.

## Groups

1. **Clear change**: what to change and where is unambiguous.
2. **Unclear** (working group): two readings are possible, or the reviewer
   was thinking aloud. Asked with AskUserQuestion, then moved to another group.
3. **Not code**: billing, vendor plans, process, ideas for later. These stay
   in the notes with who follows up, and never go into the PR.
4. **Approved as is**.

## Frames

Reviewers tend to select the text they mean, so zooms matter here. Read a
frame for every change and every unclear item.

## Check

The target branch for work already done since the call (`git log
--since=<start>`): a change already committed is marked "Already on branch: <sha>" and checked against what the
reviewer asked; only what is missing stays open. The code behind any item
whose meaning rests on how it works today.

## Output: `notes.md`

```markdown
# Review notes: <video file name>

Reviewer: <name> (speaker <X>). Call length: <mm> min. Target: <repo> @ <branch>.

## Changes
1. **[07:00] <short title>.** <what to change, concretely>. Reviewer: "<quote>". Frame: frames/note-n09-zoom.jpg. <"Clear" or "Confirmed: <answer>">. <"Already on branch: <sha>" when it is, plus anything still missing>

## Not code
- **[00:59] <title>.** <what, and who follows up>.

## Approved as is
- [01:39] <what>.

## Questions asked
- [02:00] <question> -> <answer>
```

Report the counts per group, and how many changes are already on the branch.

## On go

Hand `notes.md` to one implementer (a subagent, or do it here for a handful
of small items) with:

- the target repo and branch, and whether to update an existing PR or open a
  new one;
- one commit per open item in "Changes", in order, each message naming the
  item (items already on the branch only get the missing part);
- the repo's checks (type check, tests, lint) before pushing;
- a browser check of every UI change, with what could not be checked said
  plainly;
- a PR section that lists the items by timestamp.
