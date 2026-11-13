# Preset: meeting

A planning, sales, customer or team call. The output is what was decided,
who does what, and what is still open. Details may name the meeting, the
people or a focus ("only the pricing discussion").

## Moments

Every decision ("let's go with...", "agreed"), action item (someone says they
will do something, or is asked to and accepts), deadline, open question, risk
or concern raised, and number that matters (prices, dates, limits). Where
something was shown on screen (a slide, a dashboard, a document), the moment
it was shown.

## Groups

1. **Decision**: what, and who made or agreed it.
2. **Action item**: what, owner, due date if one was said. The owner is
   whoever will do the work: when someone dictates a change ("I will remove
   this") to the person who builds it, the builder owns it.
3. **Open question**: raised and not settled; who is meant to answer.
4. **Risk or concern**.
5. **Unclear** (working group): two people left with different readings, or an owner or date
   is ambiguous. Asked with AskUserQuestion.

## Frames

Only for moments about something on screen; most meeting moments need none.
Read the frame when a decision or number rests on what was shown.

## Check

When there is a target repo and decisions are about it, check what has been
done since the call (`git log --since=<start>`) and mark those decisions and
action items "Done since: <sha>". If an action item is about a ticket, check
the tracker for its state. Otherwise nothing.

## Output: `meeting.md`

```markdown
# <meeting name>: <date>

People: <name (speaker X), ...>. Length: <mm> min.

## Decisions
- **[12:40] <decision>.** Agreed by <who>. "<quote>"

## Action items
- [ ] **<owner>: <action>** (due <date>). [15:02]

## Open questions
- **[18:30] <question>.** For <who>.

## Risks and concerns
- **[21:10] <risk>.** Raised by <who>.

## Questions asked
- [15:02] <question> -> <answer>
```

## On go

Ask what the user wants done with it, with AskUserQuestion: create tasks or
issues for the action items, draft a follow-up message to the attendees, or
nothing more. Never send a message or create tasks in a shared tool without
that answer; show any message text before it is sent.
