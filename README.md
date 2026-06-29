# 🪈 pipper

**Drive Claude Code headlessly in a tmux session — script and automate the `claude` CLI from shell, cron, or code.**

![python](https://img.shields.io/badge/python-3.9+-blue)
![deps](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-black)

---

`pipper` is a tiny harness that runs the interactive `claude` CLI inside **tmux**, auto-accepts its permission dialogs, sends a prompt, and returns Claude's answer. It lets you call Claude Code from scripts, cron jobs, pipelines, or another program — without sitting at the terminal.

It drives your normal, already-logged-in `claude` client, so it inherits whatever plan and limits that login has. **Use it within [Anthropic's terms of service](https://www.anthropic.com/legal/aup).**

## Why

- **Automate Claude Code** in CI, cron, or batch jobs
- **Glue it into other tools** — get an answer back as text or JSON
- **TUI-version-proof** — instead of scraping the terminal, pipper asks Claude to write its answer to a temp file, then reads it back

## Requires

- [`tmux`](https://github.com/tmux/tmux)
- the [`claude` CLI](https://docs.claude.com/en/docs/claude-code) — installed **and already authenticated** (`claude` runs without a login prompt)

## Install

```bash
pip install pipper-cli      # once published; command is `pipper`
# or from source:
git clone https://github.com/sanjoxtech/pipper && cd pipper && pip install -e .
```

Zero dependencies — Python stdlib only.

## Use

```bash
pipper "summarize this repo's README in 3 bullets"
echo "list the riskiest lines in auth.py" | pipper --cwd ./myproject
pipper -f task.txt --timeout 900 --json
```

Options: `--cwd <dir>`, `--session <name>`, `--timeout <s>`, `--boot-timeout <s>`, `--json`.

From Python:

```python
import pipper
answer = pipper.run("explain what this project does", cwd="./repo")
```

## How it works

1. Spawns `claude --permission-mode bypassPermissions` in a fresh tmux session
2. Auto-accepts the startup/permission dialogs (handles different orderings + plain y/n)
3. Pastes your prompt via an isolated tmux buffer (so parallel runs don't clash)
4. Asks Claude to **write its final answer to a temp file**, then polls that file
5. Returns the answer; tears the session down; bails early on repeated API errors

## Limitations / honest notes

- Relies on `tmux` + the interactive `claude` TUI. If Claude Code changes its startup dialogs a lot, the auto-accept heuristics may need a tweak.
- `bypassPermissions` means Claude can run tools without asking — only point it at directories you trust.
- It automates your normal `claude` login; respect Anthropic's usage terms and rate limits.

## Author

Built by **Sanjay** ([sanjoxtech](https://github.com/sanjoxtech)) — [sanjox.tech](https://sanjox.tech) · sanjox.tech@gmail.com

## License

MIT — see [LICENSE](LICENSE).
