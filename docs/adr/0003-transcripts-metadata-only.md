# ADR-0003: Claude Code transcripts are ingested as metadata only

Date: 2026-10-15. Status: accepted.

## Context

Claude Code writes every session to `~/.claude/projects/<project>/<session>.jsonl`. The
files hold everything typed and everything the model wrote back, including file contents
and tool output. They are also the only record of token usage per message, which is what
a cost model needs.

## Decision

The source keeps timestamps, ids, model names, token counts, stop reasons, the kinds of
content blocks, and the project directory name. It never stores message text, tool inputs
or tool results. The project name can be replaced by a hash (`--hash-projects`).

One API message appears as several transcript lines, one per content block, each repeating
the full `usage`. The record key is the message id, and silver takes one row per key. Counting
lines would overstate cost by two to three times.

## Consequences

- The bronze directory for this source is safe to keep, back up, or query from a shared
  engine later, because it cannot leak what was said in a session.
- Analyses that need prompt content (for example "which prompts led to the most tool calls")
  are out of scope by design.
- The source re-reads only appended bytes, so a nightly run over hundreds of transcripts
  finishes in seconds.
