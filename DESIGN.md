# Design Documentation

This document explains how the tool is built and why. It also lists the choices we made where the assignment does not say what to do.

## 1. Pipeline

```
regex text ──► Parser (validation) ──► syntax tree ──► Thompson's construction ──► NFA ──► nfa.json / nfa.png
                                                                                    │
                                    min_dfa.json / min_dfa.png ◄── minimization ◄── subset construction
```

Part 2 takes the NFA **as JSON** (the same format Part 1 writes). It reads that JSON back with `read_automaton`, so it also works on any NFA file written in that format, not only on output from Part 1.

## 2. Libraries and the "no libraries" rule

Every algorithm is written by hand using only built-in Python lists, dicts and sets:

| Step | Function(s) |
|------|-------------|
| Regex parsing and validation | `Parser` |
| Thompson's construction | `NFABuilder` |
| ε-closure and subset construction | `epsilon_closure`, `subset_construction` |
| Splitting overlapping labels into separate symbols | `build_alphabet` |
| DFA minimization | `minimize` |

The only imports are:

| Import | Used for |
|--------|----------|
| `json` | Writing and reading the JSON files (input/output only) |
| `os`, `sys` | File paths and the command line |
| `graphviz` | Drawing the PNG graphs only (the assignment allows "any graphics library") |

Python's `re` module is **not** used anywhere.

## 3. Parsing and validation

The parser is a recursive-descent parser that follows this grammar. The order of the rules gives the usual precedence: postfix operators bind tightest, then concatenation, then `|`.

```
expr    := concat ( '|' concat )*
concat  := repeat repeat*
repeat  := atom ( '*' | '+' | '?' )*
atom    := literal | '.' | '(' expr ')' | '[' class ']'
class   := item item*          item := literal | literal '-' literal
literal := [0-9A-Za-z]
```

It builds a syntax tree, so we don't need to insert explicit concatenation operators or convert to postfix (shunting-yard). Each error is reported with its position and a `^` marker under the bad character.

The parser rejects:

| Problem | Example |
|---------|---------|
| Empty expression | `""` |
| Unclosed bracket | `[A-Za-z` |
| Unclosed group | `(a` |
| Unmatched `)` or `]` | `a)` |
| Empty group or empty `\|` branch | `()`, `a\|`, `\|a`, `(\|a)` |
| Empty class | `[]` |
| Quantifier with nothing before it | `*a`, `(*a)` |
| Range that is backwards or crosses character types | `[z-a]`, `[a-Z]`, `[0-z]` |
| Range with no end | `[a-]` |
| Any non-alphanumeric literal, including spaces and `^` | `a$`, `a b`, `[^a]` |

**Choice:** stacked quantifiers such as `a**` or `a*+` are accepted. Each quantifier is applied on top of the previous one, so `a**` means `(a*)*`. This is well defined, so we did not reject it.

Ranges must stay within one character type (digits, uppercase or lowercase). A range like `[A-z]` would otherwise include the non-alphanumeric characters `[ \ ] ^ _ `` ` that lie between `Z` and `a` in ASCII.

## 4. Thompson's construction (Part 1)

Each syntax-tree node becomes an NFA fragment with **one start state and one accepting state**. We do not optimize the result: the output is exactly what the construction produces.

| Regex | Fragment |
|-------|----------|
| symbol `a` | new `i` —a→ new `f` |
| `s\|t` | new `i` —ε→ s.start, t.start; s.accept, t.accept —ε→ new `f` |
| `st` | **s.accept is merged with t.start** (Dragon Book form) |
| `s*` | new `i` —ε→ s.start, `f`; s.accept —ε→ s.start, `f` |
| `s+` | new `i` —ε→ s.start; s.accept —ε→ s.start, `f` |
| `s?` | new `i` —ε→ s.start, `f`; s.accept —ε→ `f` |

### Choices

- **Concatenation merges states.** We follow the Dragon Book (Aho, Lam, Sethi, Ullman, Algorithm 3.23). The accepting state of the first fragment and the start state of the second become one state; no ε-edge is added between them. As a check, `(a|b)*abb` produces exactly the 11-state NFA in the textbook's Figure 3.34. Some lecture slides add an ε-edge instead. Switching to that version only means changing the `cat` case in `NFABuilder.build`.
- **`+` and `?` are not part of the original algorithm.** Strictly, `r+ = rr*` and `r? = r|ε`. We use the common shortcuts: `+` is the `*` fragment without the skip edge, and `?` is the `*` fragment without the loop-back edge. These accept the same language with fewer states, and they are the usual textbook and course versions.
- **`[...]` and `.` are single symbols.** A character class is one transition labelled with its text, for example `"[A-Za-z]"`. Expanding `[A-Za-z]` into a 52-way chain of `|` would produce a very large NFA that is hard to read. `.` matches any one alphanumeric character (`0-9A-Za-z`).
- **State numbering.** States are renamed `S0, S1, …` in breadth-first order starting from the start state, so the start state is always `S0`. This changes only the names, never the structure.

As a result, every NFA state has exactly one of the following:
- one symbol transition,
- one or two ε-transitions,
- no transitions (this is the single accepting state).

## 5. JSON output format

We follow the given format exactly, with one addition that the format needs for NFAs:

- **ε-transitions use the key `"ε"`.**
- **Several targets for one key are written as a list.** A JSON object can't repeat a key, so when a state has two ε-targets they appear as `"ε": ["S1", "S2"]`. When there is one target, the value stays a plain string, as in the specification.

```json
"S0": { "isTerminatingState": false, "ε": ["S1", "S2"] }
```

Symbol transitions always have a single target, because of how Thompson's construction works, so they are always plain strings. The DFA JSON contains no `ε` keys and no lists, so it matches the specified format exactly. Files are written as UTF-8 with `ensure_ascii=False`, so the `ε` key appears as the character itself rather than `ε`.

## 6. NFA → DFA (Part 2)

### 6.1 Splitting labels into separate input symbols

NFA labels can overlap. In `[a-c]a.`, for example, the character `a` matches the labels `[a-c]`, `a` and `.`. If the DFA used those labels directly as input symbols, it would be wrong, because one input character could follow two different edges.

`build_alphabet` fixes this:
1. For each alphanumeric character, it records the set of NFA labels that match it.
2. Characters with the same set of labels are grouped together. Each group becomes one DFA input symbol.

Each group is then given a readable name:
- If the group is exactly the characters of an existing NFA label, that label is reused. For `[A-Za-z]+[0-9]*`, the DFA symbols are still `[A-Za-z]` and `[0-9]`.
- If the group is every alphanumeric character, it is named `.`.
- Otherwise a compact class is built, e.g. `[bc]` or `[0-9A-Zd-z]`.

This guarantees that the DFA is deterministic: every input character follows at most one edge from each state.

### 6.2 Subset construction

This is the standard algorithm:
1. The start DFA state is the ε-closure of the NFA start state.
2. For each DFA state and each input symbol, find every NFA state reachable on that symbol, take the ε-closure of that set, and use the result as the target DFA state.
3. Repeat until no new DFA states appear. States are processed in breadth-first order.
4. A DFA state is accepting if it contains the NFA's accepting state.

Empty target sets are not created, so the DFA produced here is *partial*: some states have no edge for some symbols.

### 6.3 Minimization

This uses Moore's partition-refinement algorithm:
1. A **dead state** is added temporarily, so that every state has an edge for every symbol. Minimization is defined on complete DFAs.
2. Start with two groups: accepting states and non-accepting states.
3. Split groups repeatedly. Each state gets a signature: its own group, plus the group it moves to on each symbol. States with different signatures go into different groups. Stop when the number of groups no longer changes.
4. Each group becomes one state of the minimized DFA.
5. **The dead state's group is removed**, together with every edge into it. Any state equivalent to the dead state can never reach an accepting state, so removing it doesn't change the language. Leaving these "trap" edges out keeps the graphs readable; a missing edge means "reject". If the language is empty, the result is a single non-accepting start state.

States are then renamed `S0, S1, …` in breadth-first order, so the start state is `S0`.

## 7. Graphs

Graphs are drawn with the `graphviz` DOT layout engine. It places nodes in left-to-right ranks and routes edges so they don't overlap.

- **Accepting states:** green double circles.
- **Other states:** plain light-blue circles.
- **Start state:** an incoming arrow labelled `start`, drawn from a small point.
- **Parallel edges:** several edges from the same state to the same target are drawn as one arrow with a combined label (e.g. `a, [bc]`). The JSON still lists each symbol separately.
- **Title:** each graph is titled with the input regex.

## 8. Verification

During development, a separate test script (not included in the submission) checked the following:

1. **Correctness against Python's regex engine.** For 15 regexes covering every operator, both the NFA and the minimized DFA were compared with Python's `re.fullmatch` on 3,000 random strings each. The regexes included nested groups, character classes, `.`, overlapping labels and stacked quantifiers. All results agreed.
2. **Determinism.** No DFA state had two edges that could match the same character.
3. **Minimality on known examples.** `(a|b)*abb` gives the textbook's 4-state minimal DFA, `A*` and `(a*b*)*` give 1 state, and `[A-Za-z]+[0-9]*` gives 3 states.
4. **Validation.** All of the invalid inputs listed in section 3 are rejected with a clear message.
