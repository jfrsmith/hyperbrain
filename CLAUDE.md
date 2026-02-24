# Hyperbrain

Personal work management system for tracking goals, commitments, and daily progress.

## On Startup

Always load the hyperbrain skill at the start of each session:
```
/hyperbrain
```

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

Before committing any changes, always run a full sanitization check:

1. Review all staged files for sensitive data:
   - Absolute local paths
   - Email addresses, names, or company references
   - Credentials, API keys, tokens
   - Meeting content, journal entries, or personal notes
2. Use `git diff --staged` to inspect changes
3. Search tracked files: `git ls-files | xargs grep -E "pattern"`

The `data/` directory contains personal information and is gitignored. Never commit files from `data/`.
