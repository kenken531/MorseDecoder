# MorseDecoder

Tap the spacebar in Morse code. Python measures inter-tap timing to distinguish dots from dashes and letter/word gaps, decodes in real time, sends the decoded text to a local LLM via ollama, and displays the reply encoded back as Morse.

**Day 23 — BUILDCORED ORCAS**

---

## How It Works

- **Spacebar hold duration** determines dot vs dash (< 200 ms = dot, ≥ 200 ms = dash)
- **Silence after release** determines framing:
  - ≥ 600 ms → end of letter
  - ≥ 1400 ms → end of word (inserts space)
- A background thread watches elapsed silence and auto-commits letters/words
- On ESC the decoded sentence is sent to `ollama` via subprocess
- The LLM reply is encoded back to Morse and displayed

This mirrors **UART serial communication**: a dot is a short pulse, a dash is a long pulse, and gaps are framing — exactly how a UART receiver distinguishes bits from a continuous voltage stream.

---

## Requirements

- Python 3.8+
- [ollama](https://ollama.com) installed and running locally with a model pulled (default: `llama3.2`)

```bash
ollama pull llama3.2
```

## Python Packages

```
pynput>=1.7.6
rich>=13.0.0
```

---

## Setup

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
python morse_decoder.py
```

- Tap and hold **SPACEBAR** for dots (short) and dashes (long)
- Wait **600 ms** between letters, **1400 ms** between words
- Press **ESC** to finish input and query the LLM

### Morse reference

| Symbol | Letter | Symbol | Letter |
|--------|--------|--------|--------|
| `.-`   | A      | `-..`  | D      |
| `-...` | B      | `.`    | E      |
| `-.-.` | C      | `..`   | I      |
| `---`  | O      | `...`  | S      |
| `-`    | T      | `..-`  | U      |

---

## Common Fixes

**All taps read as dots**
→ Timing threshold too aggressive. Lower `DOT_DASH_BOUNDARY_MS` to `150` or tap dashes more slowly (hold ≥ 200 ms).

**Letters run together / wrong decode**
→ Increase `LETTER_GAP_MS` to `800` and `WORD_GAP_MS` to `2000` at the top of `morse_decoder.py`.

**pynput needs Accessibility on Mac**
→ System Settings → Privacy & Security → Accessibility → add Terminal (or your terminal app).

**pynput not working on Linux**
→ Try `keyboard` library instead: `pip install keyboard` (requires sudo to run).

**ollama not found**
→ Install from https://ollama.com and run `ollama pull llama3.2` before starting.

**Want a different LLM model**
→ Change `model="llama3.2"` in the `query_ollama()` call to any model you have pulled (e.g., `"mistral"`, `"phi3"`).

---

## Hardware Concept

Morse code is **manual serial communication** — the same logic as UART bit timing.

| Morse        | UART analog              |
|--------------|--------------------------|
| Dot pulse    | Short high bit           |
| Dash pulse   | Long high bit (3× dot)   |
| Letter gap   | Stop bit / framing gap   |
| Word gap     | Inter-frame gap          |
| Silence      | Idle line (logic high)   |

A UART receiver samples the line at fixed intervals to distinguish 0s and 1s. MorseDecoder does the same with your fingertip — measuring pulse width against a threshold instead of a baud-rate clock.

---

## Credits

Built as part of the **BUILDCORED ORCAS** daily Python challenge series.
