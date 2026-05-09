"""
MorseDecoder — Day 23 of BUILDCORED ORCAS
Tap spacebar in Morse code → decode → LLM response → encode back to Morse
Tech: pynput, ollama, time, rich
Hardware concept: Serial bit encoding / pulse-width timing / UART framing
"""

import time
import threading
import subprocess
import json
from collections import deque

try:
    from pynput import keyboard
except ImportError:
    raise SystemExit("pynput not installed. Run: pip install pynput")

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.live import Live
    from rich.layout import Layout
    from rich.align import Align
    from rich import print as rprint
except ImportError:
    raise SystemExit("rich not installed. Run: pip install rich")

# ─────────────────────────────────────────────
# Morse tables
# ─────────────────────────────────────────────
MORSE_TO_CHAR = {
    ".-": "A", "-...": "B", "-.-.": "C", "-..": "D", ".": "E",
    "..-.": "F", "--.": "G", "....": "H", "..": "I", ".---": "J",
    "-.-": "K", ".-..": "L", "--": "M", "-.": "N", "---": "O",
    ".--.": "P", "--.-": "Q", ".-.": "R", "...": "S", "-": "T",
    "..-": "U", "...-": "V", ".--": "W", "-..-": "X", "-.--": "Y",
    "--..": "Z", "-----": "0", ".----": "1", "..---": "2",
    "...--": "3", "....-": "4", ".....": "5", "-....": "6",
    "--...": "7", "---..": "8", "----.": "9",
    ".-.-.-": ".", "--..--": ",", "..--..": "?",
    "-.-.--": "!", "-..-.": "/", "-.--.": "(", "-.--.-": ")",
    ".-...": "&", "---...": ":", "-.-.-.": ";", "-...-": "=",
    ".-.-.": "+", "-....-": "-", "..--.-": "_", ".-..-.": '"',
    "...-..-": "$", ".--.-.": "@", "...---...": "SOS",
}

CHAR_TO_MORSE = {v: k for k, v in MORSE_TO_CHAR.items()}

def encode_to_morse(text: str) -> str:
    """Encode a string to Morse code display string."""
    parts = []
    for char in text.upper():
        if char == " ":
            parts.append("/")
        elif char in CHAR_TO_MORSE:
            parts.append(CHAR_TO_MORSE[char])
    return " ".join(parts)

# ─────────────────────────────────────────────
# Timing thresholds (ms)
# ─────────────────────────────────────────────
DOT_DASH_BOUNDARY_MS  = 200   # < = dot, >= = dash
LETTER_GAP_MS         = 600   # gap >= this → new letter
WORD_GAP_MS           = 1400  # gap >= this → new word (space)

# ─────────────────────────────────────────────
# State
# ─────────────────────────────────────────────
state = {
    "press_time":     None,   # when spacebar went down
    "last_release":   None,   # when spacebar last came up
    "current_symbol": "",     # dots/dashes building up current letter
    "current_word":   [],     # letters building up current word
    "decoded_words":  [],     # fully decoded words
    "raw_symbols":    [],     # all raw symbols so far (for display)
    "llm_response":   "",
    "llm_morse":      "",
    "status":         "Ready — tap spacebar in Morse code. Press ESC to send & quit.",
    "running":        True,
    "lock":           threading.Lock(),
}

console = Console()

# ─────────────────────────────────────────────
# Gap processing (called from timer thread)
# ─────────────────────────────────────────────
def flush_symbol():
    """Commit current_symbol as a letter."""
    with state["lock"]:
        sym = state["current_symbol"]
        if not sym:
            return
        char = MORSE_TO_CHAR.get(sym, f"[{sym}?]")
        state["current_word"].append(char)
        state["raw_symbols"].append(sym)
        state["current_symbol"] = ""

def flush_word():
    """Commit current_word as a decoded word."""
    flush_symbol()
    with state["lock"]:
        word = state["current_word"]
        if word:
            state["decoded_words"].append("".join(word))
            state["current_word"] = []

def gap_watcher():
    """Background thread: fires letter/word gaps based on silence duration."""
    letter_flushed = False
    word_flushed   = False
    while state["running"]:
        time.sleep(0.05)
        with state["lock"]:
            last = state["last_release"]
            press = state["press_time"]
            sym = state["current_symbol"]
            word = state["current_word"]
        if last is None or press is not None:
            letter_flushed = False
            word_flushed   = False
            continue
        elapsed_ms = (time.time() - last) * 1000
        if elapsed_ms >= WORD_GAP_MS and not word_flushed and (sym or word):
            flush_word()
            word_flushed   = True
            letter_flushed = True
        elif elapsed_ms >= LETTER_GAP_MS and not letter_flushed and sym:
            flush_symbol()
            letter_flushed = True

# ─────────────────────────────────────────────
# pynput callbacks
# ─────────────────────────────────────────────
def on_press(key):
    if not state["running"]:
        return False
    if key == keyboard.Key.esc:
        state["running"] = False
        return False
    if key == keyboard.Key.space:
        with state["lock"]:
            if state["press_time"] is None:   # ignore held-down repeat
                state["press_time"] = time.time()
                state["last_release"] = None

def on_release(key):
    if key == keyboard.Key.space:
        with state["lock"]:
            if state["press_time"] is None:
                return
            duration_ms = (time.time() - state["press_time"]) * 1000
            state["press_time"] = None
            state["last_release"] = time.time()
            symbol = "." if duration_ms < DOT_DASH_BOUNDARY_MS else "-"
            state["current_symbol"] += symbol
            state["raw_symbols"].append(symbol)   # live preview

# ─────────────────────────────────────────────
# LLM via ollama REST API
# ─────────────────────────────────────────────
def query_ollama(prompt: str, model: str = "phi3") -> str:
    """Call ollama REST API — faster than CLI subprocess, better errors."""
    import urllib.request
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("response", "(empty response)").strip()
    except ConnectionRefusedError:
        return "(ollama server not running — run: ollama serve)"
    except TimeoutError:
        return "(timed out — try a smaller model)"
    except Exception as e:
        return f"(error: {e})"

# ─────────────────────────────────────────────
# Rich live display
# ─────────────────────────────────────────────
def build_display() -> str:
    """Build the terminal UI string for Rich Live."""
    with state["lock"]:
        raw        = " ".join(state["raw_symbols"][-40:])   # last 40 symbols
        cur_sym    = state["current_symbol"]
        cur_word   = "".join(state["current_word"])
        decoded    = " ".join(state["decoded_words"])
        llm_resp   = state["llm_response"]
        llm_morse  = state["llm_morse"]
        status     = state["status"]
        press_time = state["press_time"]

    # Animate live tap
    tap_indicator = "●" if press_time else "○"

    lines = []
    lines.append(f"[bold cyan]── MorseDecoder ──  Day 23 BUILDCORED ORCAS[/bold cyan]")
    lines.append("")
    lines.append(f"[dim]Tap spacebar: [/dim][yellow]<200ms[/yellow]=dot  [yellow]≥200ms[/yellow]=dash  "
                 f"[yellow]600ms silence[/yellow]=letter  [yellow]1400ms[/yellow]=word")
    lines.append("")
    lines.append(f"[bold]Tap indicator:[/bold] {tap_indicator}")
    lines.append(f"[bold]Live symbol:[/bold]   [green]{cur_sym or '…'}[/green]")
    lines.append(f"[bold]Building word:[/bold] [green]{cur_word or '…'}[/green]")
    lines.append("")
    lines.append(f"[bold]Raw stream:[/bold]")
    lines.append(f"  [dim]{raw or '(none yet)'}[/dim]")
    lines.append("")
    lines.append(f"[bold]Decoded text:[/bold]")
    lines.append(f"  [bright_white]{decoded or '(nothing decoded yet)'}[/bright_white]")
    lines.append("")
    if llm_resp:
        lines.append(f"[bold magenta]LLM Response:[/bold magenta]")
        lines.append(f"  {llm_resp[:300]}")
        lines.append("")
        lines.append(f"[bold magenta]Morse (LLM):[/bold magenta]")
        lines.append(f"  [yellow]{llm_morse[:200]}[/yellow]")
        lines.append("")
    lines.append(f"[dim]{status}[/dim]")
    return "\n".join(lines)

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
def main():
    console.print(Panel.fit(
        "[bold cyan]MorseDecoder[/bold cyan]  [dim]Day 23 — BUILDCORED ORCAS[/dim]\n"
        "Tap [bold]SPACEBAR[/bold] in Morse code. Press [bold]ESC[/bold] to send & get LLM reply.",
        border_style="cyan"
    ))
    console.print()

    # Start gap watcher thread
    watcher = threading.Thread(target=gap_watcher, daemon=True)
    watcher.start()

    # Start pynput listener (non-blocking)
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    # Live display loop
    with Live(build_display(), refresh_per_second=10, console=console) as live:
        while state["running"]:
            live.update(build_display())
            time.sleep(0.1)
        live.update(build_display())

    listener.stop()

    # Flush any remaining input
    flush_word()

    with state["lock"]:
        decoded = " ".join(state["decoded_words"]).strip()

    console.print()
    if not decoded:
        console.print("[yellow]No text decoded. Nothing to send to LLM.[/yellow]")
        return

    console.print(f"[bold]Final decoded text:[/bold] [bright_white]{decoded}[/bright_white]")
    console.print()
    console.print("[bold magenta]Querying LLM (ollama)…[/bold magenta]")

    prompt = (
        f"The user tapped the following message in Morse code: \"{decoded}\"\n"
        "Reply conversationally and concisely (1-2 sentences max)."
    )
    response = query_ollama(prompt)
    morse_response = encode_to_morse(response)

    state["llm_response"] = response
    state["llm_morse"]    = morse_response

    console.print()
    console.print(Panel(
        f"[bright_white]{response}[/bright_white]",
        title="[magenta]LLM Response[/magenta]",
        border_style="magenta"
    ))
    console.print()
    console.print(Panel(
        f"[yellow]{morse_response}[/yellow]",
        title="[yellow]Encoded back as Morse[/yellow]",
        border_style="yellow"
    ))
    console.print()
    console.print("[dim]Done. Timing constants: dot<200ms | letter gap 600ms | word gap 1400ms[/dim]")

if __name__ == "__main__":
    main()