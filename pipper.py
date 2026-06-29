#!/usr/bin/env python3
"""
pipper — drive Claude Code headlessly in a tmux session.

A tiny harness that runs the interactive `claude` CLI inside tmux, auto-accepts its
permission dialogs, sends a prompt, and returns Claude's answer — so you can script
and automate Claude Code from a shell, cron job, or another program.

It drives your normal, already-logged-in `claude` client (so it inherits whatever
plan and limits that login has). Use it within Anthropic's terms of service.

Requires: `tmux` and the `claude` CLI installed and already authenticated.

  pipper "summarize this repo's README in 3 bullets"
  echo "list the riskiest lines in auth.py" | pipper --cwd ./myproject
  pipper -f task.txt --timeout 900 --json

How it works: pipper asks Claude to write its final answer to a temp file (instead of
scraping the terminal UI), then polls that file — robust and TUI-version-proof.

Zero dependencies. Python stdlib only.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, tempfile, time
from pathlib import Path

__version__ = "0.1.0"

_OPT_RE = re.compile(r"^\s*(?:❯\s*)?(\d+)\.\s*(.+)$")
_DIALOG_HINTS = ("enter to confirm", "do you want", "do you trust", "i accept",
                 "proceed?", "(y/n)", "[y/n]", "trust the files")
_YES_WORDS = ("yes", "accept", "proceed", "trust", "continue", "allow")


def _tmux(*args) -> subprocess.CompletedProcess:
    return subprocess.run(["tmux", *args], capture_output=True, text=True)


def _require_tools():
    for tool in ("tmux", "claude"):
        if subprocess.run(["which", tool], capture_output=True).returncode != 0:
            sys.exit(f"pipper: `{tool}` not found on PATH. Install it and make sure it works first.")


def auto_accept(session: str) -> bool:
    """If a yes/no confirmation dialog is showing, press the affirmative option.
    Handles different option orderings (Yes can be 1 or 2) and plain y/n prompts."""
    pane = _tmux("capture-pane", "-t", session, "-p").stdout
    low = pane.lower()
    if not any(h in low for h in _DIALOG_HINTS):
        return False
    for line in pane.splitlines():
        m = _OPT_RE.match(line.strip())
        if m and any(w in m.group(2).lower() for w in _YES_WORDS):
            _tmux("send-keys", "-t", session, m.group(1)); time.sleep(0.3)
            _tmux("send-keys", "-t", session, "Enter"); time.sleep(1.0)
            return True
    if "(y/n)" in low or "[y/n]" in low:
        _tmux("send-keys", "-t", session, "y")
        _tmux("send-keys", "-t", session, "Enter"); time.sleep(0.8)
        return True
    return False


def run(prompt: str, cwd: str = ".", session: str | None = None,
        boot_timeout: int = 30, work_timeout: int = 600) -> str:
    """Run `prompt` through interactive claude in tmux; return Claude's answer text."""
    _require_tools()
    session = session or f"pipper_{os.getpid()}"
    cwd = str(Path(cwd).resolve())
    tmp = Path(tempfile.mkdtemp(prefix="pipper_"))
    outfile = tmp / "answer.txt"
    promptfile = tmp / "prompt.txt"

    wrapped = (
        "Work autonomously. Do NOT ask me any questions. Do NOT print the final answer "
        f"to chat. When done, use your Write tool to save your FINAL ANSWER to:\n{outfile}\n\n"
        "--- TASK ---\n" + prompt
    )
    promptfile.write_text(wrapped, encoding="utf-8")

    _tmux("kill-session", "-t", session)
    _tmux("new-session", "-d", "-s", session, "-x", "220", "-y", "50")
    _tmux("send-keys", "-t", session,
          f"cd {cwd} && claude --permission-mode bypassPermissions", "Enter")

    # wait for the input box, accepting any startup dialogs
    t0 = time.time(); ready = False
    while time.time() - t0 < boot_timeout:
        pane = _tmux("capture-pane", "-t", session, "-p").stdout
        low = pane.lower()
        if ("shortcuts" in pane or "Welcome to Claude" in pane) and not any(
            h in low for h in ("i accept", "do you trust", "trust the files", "enter to confirm")):
            ready = True; break
        auto_accept(session); time.sleep(1)
    if not ready:
        time.sleep(4)

    # paste the prompt via an isolated named buffer, then submit
    buf = f"b_{session}"
    _tmux("load-buffer", "-b", buf, str(promptfile))
    _tmux("paste-buffer", "-b", buf, "-t", session, "-d")
    time.sleep(1.5)
    _tmux("send-keys", "-t", session, "Enter")

    # poll for the answer file; bail early on repeated API errors
    t0 = time.time()
    while time.time() - t0 < work_timeout:
        if outfile.exists():
            text = outfile.read_text(encoding="utf-8").strip()
            if text:
                _tmux("kill-session", "-t", session)
                return text
        pane = _tmux("capture-pane", "-t", session, "-p").stdout
        auto_accept(session)
        m = re.search(r"(API error.*?attempt\s+(\d+)/10|overloaded|rate.?limit|Connection error)", pane, re.I)
        if m and (int(m.group(2)) if m.group(2) else 99) >= 4:
            line = next((l.strip() for l in pane.splitlines() if "error" in l.lower()), m.group(0))
            _tmux("kill-session", "-t", session)
            raise RuntimeError(f"claude reported a repeated error: {line}")
        time.sleep(3)

    tail = _tmux("capture-pane", "-t", session, "-p").stdout[-1200:]
    _tmux("kill-session", "-t", session)
    raise TimeoutError(f"pipper timed out after {work_timeout}s. claude pane tail:\n{tail}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pipper", description="Drive Claude Code headlessly via tmux.")
    ap.add_argument("prompt", nargs="?", help="the prompt (or use -f / stdin)")
    ap.add_argument("-f", "--file", help="read the prompt from a file")
    ap.add_argument("--cwd", default=".", help="working directory to run claude in")
    ap.add_argument("--session", default=None, help="tmux session name (default: pipper_<pid>)")
    ap.add_argument("--timeout", type=int, default=600, help="max seconds to wait for the answer")
    ap.add_argument("--boot-timeout", type=int, default=30, help="max seconds to wait for claude to start")
    ap.add_argument("--json", action="store_true", help="print {\"answer\": ...} as JSON")
    ap.add_argument("--version", action="version", version=f"pipper {__version__}")
    args = ap.parse_args(argv)

    if args.file:
        prompt = Path(args.file).read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt
    elif not sys.stdin.isatty():
        prompt = sys.stdin.read()
    else:
        ap.error("no prompt given (pass it as an argument, with -f, or via stdin)")

    if not prompt.strip():
        ap.error("empty prompt")

    answer = run(prompt, cwd=args.cwd, session=args.session,
                 boot_timeout=args.boot_timeout, work_timeout=args.timeout)
    print(json.dumps({"answer": answer}) if args.json else answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
