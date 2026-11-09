# Questions before you use it

Short answers to what people ask first. How each number is counted is in [METHODOLOGY.md](METHODOLOGY.md).

## Can I do this without installing anything?

Yes. These commands read the same files and need only `jq`. They give totals, not projects, prices or a dashboard.

Claude Code, all tokens, each message counted once at its largest record (the same rule this tool uses):

```
find ~/.claude/projects -name '*.jsonl' -exec cat {} + | jq -s '
  [.[] | select(.message.usage) | {id: .message.id, t: (.message.usage |
    .input_tokens + .output_tokens + (.cache_read_input_tokens // 0) + (.cache_creation_input_tokens // 0))}]
  | group_by(.id) | map(max_by(.t).t) | add'
```

Codex, all tokens: the last running total in each session file, added up:

```
find ~/.codex/sessions ~/.codex/archived_sessions -name '*.jsonl' 2>/dev/null | while read f; do
  jq -r 'select(.type=="event_msg" and .payload.type=="token_count" and .payload.info!=null)
    | .payload.info.total_token_usage.total_tokens' "$f" | tail -1
done | awk '{s+=$1} END {print s}'
```

On the test data both commands give the same totals as `tokens report`. On real logs the Codex command can differ: a forked or resumed session repeats its history (counted twice here, once by the tool), and a counter reset loses the usage before it. For Claude Code there is also `npx ccusage`, a separate open-source counter with daily and monthly views.

## How do I get my own projects on it?

Most of it is automatic. A cost goes to a project when the agent was started inside that project's folder.

1. **Start agents in the project folder.** `cd ~/code/shop && claude` puts that work on `shop`. Subfolders count for the top folder: `~/code/shop/api` is still `shop`.
2. **Tell it where your code lives** if it is not in a usual place (`~/code`, `~/src`, `~/projects`, `~/dev`, `~/repos`, `~/Developer`, `~/work`, `~/git` and a few more).
3. **Add rules for the rest.** A rule maps a folder pattern to a name you choose. Use it to group folders into one product, to split a large repository, or to name work done outside a code folder.

```
{
  "code_roots": ["~/code", "~/clients"],
  "rules": [
    {"match": "~/clients/acme/*", "project": "Acme"},
    {"match": "~/code/monorepo/apps/web*", "project": "Web app"},
    {"match": "~/notes", "project": "Writing"}
  ]
}
```

Save it at the path `tokens config` prints, run `tokens scan`, then check `tokens report`. Rules are tried first, in order, and the first match wins. The rule pattern is matched against the full folder path in memory; only the project name is stored.

What stays unknown, and how to move it:

| Unknown because | Fix |
|---|---|
| Claude Code started in your home folder, touching several projects | Start it in the project folder |
| Codex started in your home folder | Start it in the project folder, or add a rule for the folder you use |
| Cursor usage | No fix: the Cursor export has no folder |

## What are the privacy and security risks?

What it does:

- **Reads** your agents' log files. Those files contain your prompts and replies. The tool parses each line in memory and keeps only timestamps, message ids, model names, token counters and folder names. A test checks that prompt text, file names and your home path never reach its output.
- **Stores** daily sums per tool, project and model in `~/.local/share/where-did-the-tokens-go`. The folder is readable by your account only, and so are its files.
- **Sends** nothing. There is no network code. The dashboard listens on 127.0.0.1 only, refuses requests that name another host, refuses a rescan request from another site, and the pages may not load anything from outside.

Risks that remain, plainly:

| Risk | What it means | What you can do |
|---|---|---|
| No password on the dashboard | Any program running as you on this machine can read it while `tokens serve` runs. Such a program could read your agent logs directly anyway | Stop the server with Ctrl-C when you are done |
| Project names can be sensitive | A client or product name in a folder becomes a row on the dashboard and in the report | Rename it with a rule before you share anything |
| Screenshots and reports | They show your spend estimate, models and project names | Check before you post. Nothing is shared unless you share it |
| Installing a package | You run code from PyPI on a machine that holds your logs | It has no dependencies. Pin a version. The code is small enough to read |
| Shared computers | Other accounts cannot read the inventory folder. Your agent logs keep their own permissions | Check the permissions of `~/.claude` and `~/.codex` |

## What are the trade-offs?

- **Estimate, not bill.** A list-price estimate makes tools and months comparable. It does not match a subscription or a plan allowance, and it never will.
- **Strict evidence means a bigger unknown.** The tool would rather say unknown than guess. A model could label more sessions, but a guessed label looks the same as a measured one on a chart.
- **Folder names, not repositories.** Matching by folder is simple and private. Two folders with the same name under different code roots merge unless a rule separates them.
- **Shell commands are never read.** A session that only runs shell commands in another folder is placed by where it started. Reading commands would place more work and read much more of your text.
- **Days, not turns.** It keeps daily sums, so it cannot show a single conversation. Smaller storage, less to leak.
- **Full rescan.** Each scan reads every log again. Simple and always consistent. Its speed on a large history is not measured yet.

## When will it not work?

- **Work that ran somewhere else.** Cloud agents, remote machines, containers and CI write their logs there, not here. Run the tool on each machine; it does not merge machines.
- **Logs that are gone.** It counts only what is still on disk. Claude Code can delete old transcripts on its own schedule: check the `cleanupPeriodDays` setting if your history looks short.
- **Moved config folders.** If you set `CLAUDE_CONFIG_DIR` or `CODEX_HOME` for your agents, set them for `tokens` too. `tokens where` shows what it reads.
- **New models.** A model newer than the price table shows as "no price" until you add a rate in the config.
- **Changed log formats.** It reads the agents' own files. If a new agent version changes them, counts can drop. Unknown fields are skipped, never guessed.
- **Cursor without an export.** Cursor keeps no local counters this tool can read.
- **Compressed archives** (`.jsonl.zst`) are not read.
- **Only macOS is tested.** Linux uses the same paths and should work, but has not been tested. Windows has not been tested. It needs Python 3.9 or newer.
