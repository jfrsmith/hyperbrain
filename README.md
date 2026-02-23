# Hyperbrain

A Claude Code skill for daily work management with calendar integration.

## What it does

Hyperbrain helps maintain strategic focus by tracking goals, commitments, and daily progress. It integrates with Google Calendar to understand your schedule and identify available focus time.

## Commands

| Command | Description |
|---------|-------------|
| `/hyperbrain morning` | Daily planning - shows calendar, goals, commitments, identifies focus time |
| `/hyperbrain capture [item]` | Quick-add a commitment with context |
| `/hyperbrain debrief` | Process meetings from today, extract outcomes and action items |
| `/hyperbrain review` | On-demand status check of goals and commitments |
| `/hyperbrain eod` | End-of-day reflection, checks for undebriefed meetings |
| `/hyperbrain weekly` | Weekly strategic review with calendar pattern analysis |

## Setup

1. Clone this repo
2. Set up Google Calendar MCP server (see [google-calendar-mcp](https://www.npmjs.com/package/@cocal/google-calendar-mcp))
3. Create a `data/` directory with:
   - `goals.md` - Your quarterly goals
   - `commitments.md` - Active work items
   - `patterns.md` - Learned preferences (updated by weekly reviews)
   - `journal/` - Daily logs
   - `journal/weekly/` - Weekly summaries
   - `archive/` - Completed items

The `data/` directory contains personal information and is gitignored.

## Philosophy

- Be direct. State facts without padding.
- Strategic work matters. The system flags when tactical work crowds out goals.
- Meetings generate commitments. Debrief them to capture action items.
- Deletion is progress. Regularly prune stale items.

## License

MIT
