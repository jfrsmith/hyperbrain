# Hyperbrain

You are running in Windows via Terminal.

Personal work management system for tracking goals, commitments, and daily progress.

## On Startup

Always load the hyperbrain skill at the start of each session:
```
/hyperbrain
```

## Time-Based Statements

Before stating how much time is available, time until a meeting, or suggesting time blocks, always check the current system time first:

```powershell
powershell "Get-Date -Format 'yyyy-MM-dd HH:mm'"
```

Never rely on a cached timestamp from earlier in the conversation.

## Windows Path Bug Workaround

If you encounter this error when editing files:
```
Error: File has been unexpectedly modified. Read it again before attempting to write it.
```

**Use relative paths instead of absolute paths.** This is a Windows-specific bug where absolute paths trigger false modification detection.

- Bad: `C:/path/to/repo/data/journal/2026-02-23.md`
- Good: `data/journal/2026-02-23.md`

This applies to Read, Edit, and Write tool calls.

## Sensitive Information in Files

**Public files** (anything outside `data/`) will be committed to git and pushed to a public repository. When editing these files:

- Never include real names, email addresses, or company references
- Never reference specific work items, meeting content, or journal entries
- Use generic placeholder examples (e.g., "Alice", "PR #1234", "Project X")
- Don't copy content from `data/` files into public files

**Private files** (`data/` directory) contain personal information and are gitignored. Sensitive content is expected and fine here.

The key principle: **don't let sensitive information enter public files in the first place.** The commit check below is a safety net, not the primary control.

## Git Commits

**REQUIRED: Run this checklist BEFORE every `git commit` command:**

- [ ] `git diff --staged` - review all changes line by line
- [ ] Check for: absolute paths, real names, emails, company references
- [ ] Check for: credentials, API keys, tokens
- [ ] Check for: meeting content, journal entries, personal notes from `data/`
- [ ] Verify no files from `data/` are staged

Do not skip this check. Do not assume changes are safe because you wrote them.

The `data/` directory contains personal information and is gitignored. Never commit files from `data/`.

## Research

When researching a topic you should first check if this research should be done by a separate agent to ensure it doesn't pollute the current context.

When performing research with the sub-agent you should provide it with the relevant context. Research output should be annotated with references where appropriate, including when findings are synthesised.