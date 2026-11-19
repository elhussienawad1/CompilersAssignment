# Regex → NFA → Minimized DFA

Compilers and Languages programming assignment (Cairo University, Computer Eng. Dept., Fall 2024).

- **Part 1:** converts a regular expression into an NFA using Thompson's construction.
- **Part 2:** converts that NFA into a minimized DFA (subset construction, then partition refinement).

Both parts write a JSON file in the format the assignment requires and draw a PNG graph of the automaton.

## Files

| File | Purpose |
|------|---------|
| `RegexToMinDFA.ipynb` | Google Colab notebook to submit. Its last cell runs a test case. |
| `regex_automata.py` | The same code as a command-line tool. |
| `DESIGN.md` | Design choices and how the algorithms are implemented. |

## Running on Google Colab (required for submission)

1. Go to [colab.research.google.com](https://colab.research.google.com), choose **File → Upload notebook**, and select `RegexToMinDFA.ipynb`.
2. Choose **Runtime → Run all**.
3. The last cell asks for a regular expression, for example:
   ```
   Enter a regular expression: [A-Za-z]+[0-9]*
   ```
4. The cell prints both JSON documents and shows both graphs. It also saves the 4 outputs in the `output/` folder, which you can open from the Files sidebar on the left:

   | Output | File |
   |--------|------|
   | Part 1 JSON (NFA) | `output/nfa.json` |
   | Part 1 graph | `output/nfa.png` |
   | Part 2 JSON (minimized DFA) | `output/min_dfa.json` |
   | Part 2 graph | `output/min_dfa.png` |

To try another test case, run only the last cell again.

If the regex is invalid, the cell prints an error that points to where the problem is, for example:
```
Invalid regular expression: Missing ']' for character class at position 0
  [A-Za-z
  ^
```

## Running locally from the command line

### Requirements

- Python 3.8 or newer
- The Graphviz program (`dot`) and its Python package. These are used only to draw the images.
  ```bash
  sudo apt install graphviz        # macOS: brew install graphviz
  pip install graphviz
  ```

### Commands

```bash
# Part 1 only: regex -> NFA  (writes nfa.json and nfa.png)
python regex_automata.py convert "[A-Za-z]+[0-9]*"

# Part 2 only: NFA JSON file -> minimized DFA  (writes min_dfa.json and min_dfa.png)
python regex_automata.py minimize nfa.json

# Both parts at once  (writes all 4 outputs to output/)
python regex_automata.py "[A-Za-z]+[0-9]*"
```

Put the regex in quotes so the shell doesn't interpret characters like `*`, `|`, `(` and `[`.

## Supported regex syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `a` | A literal (letters and digits only) | `abc` |
| `\|` | Or | `a\|b\|c` |
| `( … )` | Group | `((ABC)\|(abc))` |
| `[ … ]` | Any character or range in the brackets | `[a-cA-C5]` |
| `.` | Any single alphanumeric character | `a.c` |
| `?` | Zero or one | `a?` |
| `*` | Zero or more | `A*` |
| `+` | One or more | `A+` |

## Example output

For `ab`, the file `nfa.json` contains:
```json
{
  "startingState": "S0",
  "S0": { "isTerminatingState": false, "a": "S1" },
  "S1": { "isTerminatingState": false, "b": "S2" },
  "S2": { "isTerminatingState": true }
}
```

For `[A-Za-z]+[0-9]*`, the file `min_dfa.json` contains:
```json
{
  "startingState": "S0",
  "S0": { "isTerminatingState": false, "[A-Za-z]": "S1" },
  "S1": { "isTerminatingState": true, "[0-9]": "S2", "[A-Za-z]": "S1" },
  "S2": { "isTerminatingState": true, "[0-9]": "S2" }
}
```

In the graphs, accepting states are green double circles and the start state has an arrow labelled `start` pointing to it.
