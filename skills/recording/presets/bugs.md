# Preset: bugs

A user, customer or tester tries the product on a call, often thinking aloud.
Details may name the person and the product area or repo.

## Moments

Every moment where something goes wrong or nearly does: an error message,
something that does not respond, wrong data, the person hesitating, getting
lost, misreading the screen, finding a workaround, or saying "I expected...".
Also every request or wish. Where the tester is shown how to do something by
the other person, that is a moment too (the product did not make it clear).

## Groups

1. **Bug**: the product did something wrong. Needs steps to reproduce,
   expected, actual, and how bad (blocks the task / annoying / cosmetic).
2. **Friction**: the product worked but the person struggled (confusing copy,
   hidden control, too many steps).
3. **Request**: something they want that is not there.
4. **Unclear** (working group): cannot tell whether it is a bug, a misunderstanding or
   intended. Asked with AskUserQuestion.
5. **Not ours**: their network, browser, another product.

## Frames

Frames are the evidence here. Read the frame for every bug and friction item,
and widen the burst (`--before 6`) for bugs so the steps leading up to them
show. Write down what is on screen: the page, the error text, the data shown.
Note anything in a frame that is personal data (names, emails, payment
details) so it is kept out of issues.

## Check

The repo for the code path behind each bug, and the branch history for a fix
already made since the call. The issue tracker (`gh issue list --search`) for
an existing issue: link it instead of opening a duplicate.

## Output: `bugs.md`

```markdown
# Bugs and friction: <video file name>

Tester: <name> (speaker <X>). Call length: <mm> min. Product area: <area>.

## Bugs
1. **[04:12] <short title>** (blocks the task | annoying | cosmetic)
   - Steps: <1, 2, 3, from the frames and what was said>
   - Expected: <...>  Actual: <...>
   - Tester: "<quote>". Frame: frames/note-n04.jpg
   - <"Existing issue: #123" or "Fixed on branch: <sha>" when it is>

## Friction
- **[06:30] <title>.** <what they struggled with and what would help>. "<quote>". Frame: ...

## Requests
- **[11:02] <title>.** <what and why>.

## Not ours
- [08:15] <what>.

## Questions asked
- [04:12] <question> -> <answer>
```

## On go

Ask which the user wants, with AskUserQuestion: open one GitHub issue per bug
(and optionally per friction item), or fix the bugs on a branch (one commit
per bug, with a test that reproduces it first, the repo's checks, and a PR).
Issues carry the steps, expected and actual, and the frame only if it shows no
personal data.
