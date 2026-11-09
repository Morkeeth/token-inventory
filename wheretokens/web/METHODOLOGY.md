# How it is counted

This tool counts what your coding agents logged on this machine. It estimates what those tokens would cost at public API list price. It names a project for a cost only when there is evidence, and says **unknown** where there is none. It does not know what you paid.

Everything below happens on your machine. Nothing is uploaded, and the tool makes no network request.

## Three kinds of number

| Kind | What it is | Example on the dashboard |
|---|---|---|
| Measured | Tokens, exactly as each agent logged them | Tokens per tool, model and day |
| Estimated | Logged tokens times a dated public list price | Every dollar figure |
| Stated | A figure a file you imported says, taken as written | Cursor "export states" cost |

A dollar figure is never money paid. A subscription or a plan allowance is billed differently. The same usage on a flat plan and at list price are two views of one thing, so they are never added together.

## What is read

| Source | Where | One count is |
|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` (or `$CLAUDE_CONFIG_DIR/projects`) | One assistant API message |
| Codex | `~/.codex/sessions` and `~/.codex/archived_sessions` (or `$CODEX_HOME`) | One increase of the logged counters |
| Cursor | A usage export (CSV) you download and import with `tokens import-cursor` | One export row |

From each record the tool keeps: the timestamp, the message id, the model name, the token counters, and the working folder. For Claude Code it also looks at the **path argument** of file tools (Read, Edit, Write, MultiEdit, NotebookEdit, Glob, Grep), in memory, to find a project. Paths are reduced to a project name and dropped.

Never read into any number: prompt text, reply text, file contents, tool results, shell command text.

## Counting Claude Code

1. **One count per API message.** Claude Code writes one line per content block of the same message and repeats the usage on each line. Summing lines over-counts. Each message is counted once, keyed by its message id (or request id, or line id when both are missing).
2. **The largest record wins.** The first record of a streamed message can carry a placeholder output count of two or three tokens, and a later record carries the final count. Counting the first record undercounts output. Each message is counted at its record with the largest total. Ties keep the first.
3. **All token kinds count.** Total = input + output + cache read + cache write (5 minute and 1 hour).
4. **By event time.** Each message is placed on the local day of its own timestamp. A session that runs past midnight is split across days.

Subagent transcripts are separate files and are counted. A message repeated across files counts once.

## Counting Codex

Codex logs **running totals**, not per-request counts. Each file is read in time order and differenced:

- A repeated snapshot (same totals) is dropped.
- A total that goes **down** is a reset. That row is excluded, never guessed, and becomes the new starting point.
- An event copied into a forked or resumed session (same timestamp, model and totals) counts once.
- The window is applied after differencing. Filtering first would charge all earlier usage of a session to its first row inside the window.
- An increase is priced only when it equals the "last request" counters Codex logged beside it. Otherwise its tokens count with **no price**: one aggregate increase cannot say which request size, and so which long-context rate, applied.

In Codex counters, cache reads and cache writes are part of input, and reasoning is part of output. The dashboard shows ordinary input, cache read, cache write and output as separate parts.

## Counting Cursor

Cursor keeps no local token counters this tool can read, and this tool never logs in anywhere. Download the usage export from your Cursor dashboard and run `tokens import-cursor FILE.csv`. Exact duplicate rows are dropped. Sums are kept per day, model and kind.

No list price is applied to Cursor tokens, so Cursor adds tokens and no estimate. The export's Cost column can hold a number, Included or Free, and the file does not say what was billed. It is shown as "export states", on its own, and never added to the estimate. Cursor rows have no working folder, so their project is unknown.

## Prices

| Provider | Price date | Source |
|---|---|---|
| Anthropic | 2026-10-04 | platform.claude.com/docs/en/about-claude/pricing |
| OpenAI (Codex, standard tier) | 2026-10-04 | developers.openai.com/api/docs/pricing |

- Model names with a date suffix (`-20251001`) are priced as the base model.
- Claude cache writes cost 1.25 times input for 5 minutes and 2 times input for 1 hour. Cache reads cost 0.1 times input, or the per-model multiple where Anthropic publishes one.
- Claude fast mode uses the fast rate. A Haiku 5.5 request over 100,000 prompt tokens uses the higher tier.
- A Codex request over 272,000 input tokens pays twice the input rate and 1.5 times the output rate, per request, never per session.
- **A model with no rate shows as "no price", never as zero dollars.** Add a rate in your config if you know it.

Prices change. Treat an estimate as "what this would cost on the API on the price date", not as history.

## How a cost gets a project

Each counted record gets a project for one stated reason, tried in this order. The first that holds wins. Nothing is split by a share and nothing is spread over projects.

| Order | Reason | Meaning |
|---|---|---|
| 1 | your rule | A rule in your config matches the working folder |
| 2 | working folder | The working folder, reduced to its first folder under a code root, or its own name |
| 3 | files touched | The working folder said nothing (your home folder, or a code root itself) and every file the message's file tools touched sits in one project |
| 4 | unknown | None of the above |

Code roots by default: `~/code`, `~/CODE`, `~/Code`, `~/src`, `~/projects`, `~/Projects`, `~/dev`, `~/repos`, `~/Developer`, `~/work`, `~/git`, `~/github`. A working folder of `~/code/shop/api` belongs to `shop`. A worktree under `~/code/.worktrees/shop-fix` belongs to `shop-fix`.

## What unknown means

**Unknown is a finding.** It is the share of the estimate with no evidence of a project. It is always drawn on the dashboard, hatched, and never dropped from a total.

Common causes:

- You started the agent in your home folder and it touched files in several projects, or none.
- Codex was started in your home folder. Codex logs one working folder per turn and no file arguments, so there is nothing else to go on.
- Cursor rows, which carry no folder.

To shrink it, start agents inside the project folder, or add a rule:

```
{
  "code_roots": ["~/code", "~/work"],
  "rules": [
    {"match": "~/work/client-a/*", "project": "Client A"},
    {"match": "~/notes", "project": "Writing"}
  ]
}
```

Save it at the path `tokens config` prints. Rules are matched against the full path in memory. Only the project name is stored.

## Limits

- Only the three sources above. ChatGPT, Claude on the web, and other tools keep no local counters and are not counted. Not counted means unknown, not zero.
- Compressed transcript archives (`.jsonl.zst`) are not read.
- Records start where your agents' logs start. Agents may delete old logs; this tool cannot recover them.
- A folder is matched by name. Two different folders with the same name under different code roots get the same project. Add a rule to separate them.
- Each tool has its own definition of a token. Totals across tools add logged counts; they do not convert between them.
- Shell commands are never read, so a session that only runs shell commands in another folder is placed by its working folder.
- No invoice is fetched. What you actually paid stays outside this tool.

## What it writes

One folder: `~/.local/share/where-did-the-tokens-go` (or `$XDG_DATA_HOME`, or `$TOKENS_DATA`). It holds `inventory.json`, daily sums per tool, project, reason and model, and `cursor-usage.json` if you imported an export. No transcript text is copied. Delete the folder to remove everything.

## Checks you can run yourself

Claude Code totals per file, each message counted once:

```
jq -s '[.[]|select(.message.usage)|{id:.message.id,u:.message.usage}]|unique_by(.id)
  |map(.u.input_tokens+.u.output_tokens+(.u.cache_read_input_tokens//0)+(.u.cache_creation_input_tokens//0))|add' FILE.jsonl
```

This keeps the first record per message, so on streamed messages it can come out slightly lower than this tool, which keeps the largest. A plain sum without `unique_by` comes out higher.
