# Claude Code slash commands

Slash-command definitions for the weekly-trade-strategy pipeline.

Claude Code reads slash commands from `~/.claude/commands/`, which is **not a git
repository**. A command that lives only there is unversioned and unbacked-up —
`weekly-pipeline.md` is a 23 KB operating procedure that accreted over months of
live runs (the Step 0a reordering, the Step 0c gamma overlay, the Step 2c
earnings gate, the Step 4c adversarial review, the Step 5 validator gate), and a
single `rm` would have taken all of it. These files live here so they are
versioned, and `~/.claude/commands/` symlinks to them.

## Install

Symlink, don't copy — a copy drifts the moment either side is edited, which is
how the file became unarchived in the first place.

```bash
ln -sfn ~/src/claude-trading-skills/examples/weekly-trade-strategy/commands/weekly-pipeline.md \
        ~/.claude/commands/weekly-pipeline.md
```

Verify:

```bash
readlink -f ~/.claude/commands/weekly-pipeline.md   # -> this directory
```

`/weekly-pipeline` then works unchanged, and every future edit is tracked by git
automatically.

## Commands

| File | Invoked as | What it does |
|---|---|---|
| `weekly-pipeline.md` | `/weekly-pipeline` | Sunday-evening five-step pipeline: earnings fetch → charts → Markov → gamma → technical → us-market → indicator cards → news → blog → data-quality → adversarial posture review → order plans + Monday cron |

## Paths

These commands are `~/`-relative, not repo-relative, because Claude Code executes
them from the user's home directory rather than from a checkout. They therefore
assume a specific layout — see the **Prerequisites** section at the top of
`weekly-pipeline.md` for the full list.

The one worth repeating: **`~/src/markov-hedge-fund-method` is a separate
repository** with no copy vendored here, so a fresh checkout of this repo alone
will fail at the Markov overlay step. Everything else is either this repo, the
`~/.venv` virtualenv, or the schwab-mcp tool install.

## Editing

Edit the file **here**, in the repo. The symlink means `/weekly-pipeline` picks
up changes immediately — there is no copy step and no sync to remember.

Because the pipeline is a live operating procedure that moves real and paper
money, prefer small reviewed edits over rewrites, and record *why* a step exists
when adding one. Several steps in this file are scar tissue from specific
incidents (the DTE-window requirement, the two-band sleeve check, the earnings
fetch ordering); a future reader who does not know that will delete them as
redundant.
