# Hyperbrain Output Formats

Reference file for output templates and examples. Read the relevant section when producing output for a subcommand.

## Table of Contents
- [Morning Planning Output](#morning-planning-output)
- [Meeting Debrief Output](#meeting-debrief-output)
- [Journal Entry Formats](#journal-entry-formats)
- [Weekly Summary Format](#weekly-summary-format)
- [Commitment Format](#commitment-format)

---

## Morning Planning Output

Example opening for morning planning:

```
## Today: Tuesday, Jan 14

**Calendar** (5 hrs in meetings):
- 9:00-9:20 Daily Review (focus time)
- 10:30-11:20 1:1 with Alex
- 12:00-1:00 Lunch
- 2:00 PM onwards: Back-to-back meetings until 5:30 PM

**Available Focus Time**: 9:20-10:30 (70 mins), 1:00-2:00 (60 mins)
→ Heavy afternoon. Do strategic work before 2 PM.

**Open Action Items** (from previous days):
- [ ] Follow up with Acme on proposal (from Monday, due Friday) - 1 day old
- [ ] Review PR #1234 (from Friday) - 4 days old, was marked HIGH PRIORITY

**Quarterly Goals**:
1. Launch Beta - In progress, 2 weeks to deadline
2. Hire Senior Engineer - Not started (waiting 12 days)

**Active Strategic Commitments**:
- Write job description for senior role (waiting 12 days, 0% progress)

**Observation**: You've spent the last 3 days in tactical work. Strategic items are aging.
```

### Calendar Analysis Notes
- Calculate available focus time (gaps between meetings > 30 mins)
- Flag "meeting-heavy" days (> 4 hours in meetings) - suggest limiting new commitments
- Note back-to-back meetings that may cause context-switching fatigue
- If afternoon is packed, suggest doing strategic work in morning focus blocks

---

## Meeting Debrief Output

Example debrief flow:

```
## Meetings to Debrief

1. **Weekly Team Sync** (5:00 PM) - Alice, Bob, Carol [Google Meet]
2. **Project Alpha Steering** (4:00 PM) - Alex, Jordan [Zoom]

Let's go through each one.

### 1. Weekly Team Sync

📝 **Smart Notes available** for this meeting.

**Summary (from Gemini):**
Alice and Bob discussed the Q2 release timeline, with Alice committing to finalize
the project schedule by Friday. The team identified API integration issues blocking
the frontend work and agreed Bob would coordinate with the backend team.

**Suggested Next Steps (from Gemini):**
- Alice will finalize the project timeline for Q2 release by end of week
- Bob will schedule a follow-up meeting with the backend team to resolve API integration issues
- Carol will review the API documentation and flag any gaps to the team
- Alice will send calendar invites for the weekly sync to include the new team members

**Strategic Context (from Details):**
- **Decision**: Team agreed to deprioritize the mobile app work until Q3 (affects Goal #2)
- **Risk identified**: Backend team is at capacity; API work may slip if not escalated
- **Goal update**: Q2 release timeline now targeting May 15 (was May 1) - 2 week slip
- **Waiting on**: Legal approval for new vendor contract (blocking Carol's integration work)

Any corrections or additional items to capture?

### 2. Project Alpha Steering
(No Smart Notes - Zoom meeting)
What was the outcome?
```

### Smart Notes Integration

When Smart Notes are available, extract from the structured response:
- **Summary** section: High-level overview paragraph
- **Details** section: Rich strategic context (decisions, goal updates, risks, blockers)
- **Suggested next steps**: Complete action items - display verbatim, don't summarize

---

## Journal Entry Formats

### Meeting Notes (in daily journal)

**For routine meetings with no significant outcomes:**
```markdown
### [Meeting Name] ([Time])
BAU, no actions.
```

**For meetings with outcomes worth tracking:**
```markdown
### [Meeting Name] ([Time])
- **Attendees**: [Names]
- **Outcome**: [What was decided/discussed]
- **Decisions**:
  - [Key decision and rationale]
- **Action items**:
  - [ ] [Item] (owner: you)
  - [ ] [Item] (waiting on: [name])
- **Strategic context** (if relevant):
  - Goal updates: [Any changes to quarterly goal status/timeline]
  - Risks: [Issues that need monitoring]
  - Blockers: [Things waiting on external dependencies]
```

Use the short format by default. Only expand when there's meaningful content.

### End of Day Journal Structure

```markdown
# [Date]

## Morning Plan
[What was planned]

## Accomplishments
- [What got done]

## Carried Forward
- [What didn't get done and why]

## Reflections
[How the day went, energy level, observations]

## Tomorrow
[What needs attention first]
```

---

## Weekly Summary Format

```markdown
# Week [Number] - [Date Range]

## Goal Progress
[Status of each quarterly goal]

## Completed This Week
- [List of completed items]

## Calendar Shape
- Meeting hours: [X hrs]
- Best focus days: [Days with most available time]
- Strategic work happened: [When]

## Patterns Observed
- [What worked, what didn't]
- [Calendar patterns: productive days, meeting overload, etc.]

## Deferred/Blocked
- [Items that didn't move and why]

## Next Week
- **Calendar shape**: [Meeting-heavy vs focus days]
- **Top priorities**: [Matched to available focus time]
```

---

## Commitment Format

Format for items in `commitments.md`:

```markdown
- [ ] [Description]
  - **Goal**: [Goal # or None]
  - **Source**: [Where it came from]
  - **Done when**: [Exit criteria]
  - **Time-box**: [Allocated time]
  - **Added**: [Date] | **Last touched**: [Date]
```

### Review Plan Section

When showing today's plan in review subcommand:

```
**Today's Plan** (from this morning):
- Focus block 1:30-3:00 PM was earmarked for:
  - **HIGH PRIORITY**: Code review for PR #1234
  - Goal #2: Work on hiring pipeline
- Success criteria: Decision X made, next steps on Y defined
```

If no morning plan exists for today, note: "No morning plan found for today."
