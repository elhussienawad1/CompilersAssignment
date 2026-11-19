"""
Compilers Programming Assignment
  Part 1: Regular expression -> NFA   (Thompson's construction)
  Part 2: NFA -> DFA (subset construction) -> minimized DFA (partition refinement)

The algorithms (parsing, validation, Thompson's construction, subset construction,
minimization) are implemented from scratch using only built-in Python data types.
The only imports are:
  * json      - to write / read the required JSON files (I/O only)
  * sys, os   - command-line handling and paths
  * graphviz  - ONLY to draw the output images (allowed: "any graphics library")

Command-line usage:
    python regex_automata.py "[A-Za-z]+[0-9]*"            # runs both parts
    python regex_automata.py convert "[A-Za-z]+[0-9]*"    # part 1 only
    python regex_automata.py minimize nfa.json            # part 2 only (input = NFA JSON file)
"""

import json
import os
import sys

EPSILON = "ε"

# ---------------------------------------------------------------------------
# Character helpers (input literals are alphanumeric only)
# ---------------------------------------------------------------------------

DIGITS = "0123456789"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
ALPHANUMERIC = DIGITS + UPPER + LOWER  # the universe matched by "."


def is_literal(ch):
    return ch in ALPHANUMERIC


def char_category(ch):
    if ch in DIGITS:
        return "digit"
    if ch in UPPER:
        return "upper"
    return "lower"


class RegexError(Exception):
    """Raised when the input regular expression is invalid."""


# ---------------------------------------------------------------------------
# Part 1a: Parsing / validation  (recursive descent -> syntax tree)
#
#   expr    := concat ( '|' concat )*
#   concat  := repeat repeat*
#   repeat  := atom ( '*' | '+' | '?' )*
#   atom    := literal | '.' | '(' expr ')' | '[' class ']'
#   class   := item item*        item := literal | literal '-' literal
#
# Tree nodes are tuples:
#   ('sym', label)       label is a literal "a", "." or a class text "[a-c]"
#   ('cat', left, right) ('alt', left, right)
#   ('star', n) ('plus', n) ('opt', n)
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else None

    def error(self, msg):
        pointer = " " * self.pos + "^"
        raise RegexError(f"{msg} at position {self.pos}\n  {self.text}\n  {pointer}")

    def parse(self):
        if self.text == "":
            raise RegexError("Empty regular expression")
        tree = self.parse_expr()
        if self.pos != len(self.text):
            ch = self.peek()
            if ch == ")":
                self.error("Unmatched ')'")
            self.error(f"Unexpected character '{ch}'")
        return tree

    def parse_expr(self):
        node = self.parse_concat()
        while self.peek() == "|":
            self.pos += 1
            node = ("alt", node, self.parse_concat())
        return node

    def parse_concat(self):
        ch = self.peek()
        if ch is None or ch in "|)":
            self.error("Missing operand (empty alternative or empty group)")
        node = self.parse_repeat()
        while self.peek() is not None and self.peek() not in "|)":
            node = ("cat", node, self.parse_repeat())
        return node

    def parse_repeat(self):
        node = self.parse_atom()
        while self.peek() is not None and self.peek() in "*+?":
            op = self.peek()
            self.pos += 1
            node = ({"*": "star", "+": "plus", "?": "opt"}[op], node)
        return node

    def parse_atom(self):
        ch = self.peek()
        if ch is None:
            self.error("Unexpected end of expression")
        if is_literal(ch):
            self.pos += 1
            return ("sym", ch)
        if ch == ".":
            self.pos += 1
            return ("sym", ".")
        if ch == "(":
            self.pos += 1
            node = self.parse_expr()
            if self.peek() != ")":
                self.error("Missing ')'")
            self.pos += 1
            return node
        if ch == "[":
            return ("sym", self.parse_class())
        if ch in "*+?":
            self.error(f"Quantifier '{ch}' has nothing to repeat")
        if ch == "]":
            self.error("Unmatched ']'")
        self.error(f"Invalid character '{ch}' (literals must be alphanumeric)")

    def parse_class(self):
        start = self.pos
        self.pos += 1  # skip '['
        if self.peek() == "]":
            self.error("Empty character class '[]'")
        while self.peek() != "]":
            ch = self.peek()
            if ch is None:
                self.pos = start
                self.error("Missing ']' for character class")
            if not is_literal(ch):
                self.error(f"Invalid character '{ch}' inside character class")
            self.pos += 1
            if self.peek() == "-":
                self.pos += 1
                hi = self.peek()
                if hi is None or not is_literal(hi):
                    self.error("Invalid range end in character class")
                if char_category(ch) != char_category(hi) or ord(ch) > ord(hi):
                    self.error(f"Invalid range '{ch}-{hi}'")
                self.pos += 1
        self.pos += 1  # skip ']'
        return self.text[start:self.pos]


def parse_regex(text):
    return Parser(text).parse()


def label_chars(label):
    """Set of characters matched by a transition label ("a", ".", "[a-c5]")."""
    if label == ".":
        return set(ALPHANUMERIC)
    if len(label) == 1:
        return {label}
    chars = set()
    body = label[1:-1]
    i = 0
    while i < len(body):
        if i + 2 < len(body) and body[i + 1] == "-":
            for code in range(ord(body[i]), ord(body[i + 2]) + 1):
                chars.add(chr(code))
            i += 3
        else:
            chars.add(body[i])
            i += 1
    return chars


# ---------------------------------------------------------------------------
# Part 1b: Thompson's construction
#
# Each fragment has exactly one start state and one accepting state.
# Every state has either: one symbol transition, or up to two ε transitions,
# or nothing (the accepting state).  Concatenation follows the Dragon Book:
# the accepting state of N(s) is merged with the start state of N(t).
# ---------------------------------------------------------------------------

class NFABuilder:
    def __init__(self):
        self.trans = []  # trans[state] = list of (label, target)

    def new_state(self):
        self.trans.append([])
        return len(self.trans) - 1

    def add(self, src, label, dst):
        self.trans[src].append((label, dst))

    def build(self, node):
        """Returns (start, accept) of the fragment for this tree node."""
        kind = node[0]

        if kind == "sym":                      # i --a--> f
            i, f = self.new_state(), self.new_state()
            self.add(i, node[1], f)
            return i, f

        if kind == "cat":                      # N(s) N(t), merge s.accept with t.start
            s_start, s_accept = self.build(node[1])
            t_start, t_accept = self.build(node[2])
            self.trans[s_accept] = self.trans[t_start]
            self.trans[t_start] = None         # t.start no longer exists
            self._redirect(t_start, s_accept)
            return s_start, t_accept

        if kind == "alt":                      # i -ε-> s,t ; s.f,t.f -ε-> f
            i = self.new_state()
            s_start, s_accept = self.build(node[1])
            t_start, t_accept = self.build(node[2])
            f = self.new_state()
            self.add(i, EPSILON, s_start)
            self.add(i, EPSILON, t_start)
            self.add(s_accept, EPSILON, f)
            self.add(t_accept, EPSILON, f)
            return i, f

        if kind in ("star", "plus", "opt"):
            i = self.new_state()
            s_start, s_accept = self.build(node[1])
            f = self.new_state()
            self.add(i, EPSILON, s_start)
            if kind in ("star", "opt"):        # may skip the body
                self.add(i, EPSILON, f)
            if kind in ("star", "plus"):       # may repeat the body
                self.add(s_accept, EPSILON, s_start)
            self.add(s_accept, EPSILON, f)
            return i, f

        raise ValueError(f"Unknown node {kind}")

    def _redirect(self, old, new):
        # Nothing can point to a fragment's start state from outside the
        # fragment before it is combined, but loops inside N(t) (e.g. from
        # a star) may target t.start, so redirect them to the merged state.
        for edges in self.trans:
            if edges is None:
                continue
            for k, (label, dst) in enumerate(edges):
                if dst == old:
                    edges[k] = (label, new)


def number_states(start, transitions_of, accepting):
    """Rename states S0, S1, ... in breadth-first order from the start state."""
    order, seen, queue = [], {start}, [start]
    while queue:
        state = queue.pop(0)
        order.append(state)
        for _, dst in transitions_of(state):
            if dst not in seen:
                seen.add(dst)
                queue.append(dst)
    names = {state: f"S{k}" for k, state in enumerate(order)}
    result = {"startingState": names[start]}
    for state in order:
        entry = {"isTerminatingState": state in accepting}
        for label, dst in transitions_of(state):
            target = names[dst]
            if label in entry:                 # several targets for one symbol (ε)
                if not isinstance(entry[label], list):
                    entry[label] = [entry[label]]
                entry[label].append(target)
            else:
                entry[label] = target
        result[names[state]] = entry
    return result


def regex_to_nfa(regex):
    """Part 1: returns the NFA as a dict in the required JSON format."""
    tree = parse_regex(regex)
    builder = NFABuilder()
    start, accept = builder.build(tree)
    return number_states(start, lambda s: builder.trans[s], {accept})


# ---------------------------------------------------------------------------
# Part 2: NFA -> DFA (subset construction) -> minimized DFA
# ---------------------------------------------------------------------------

def read_automaton(data):
    """Turns the JSON dict into (start, accepting set, {state: [(label, dst)]})."""
    if "startingState" not in data:
        raise ValueError("NFA JSON has no 'startingState'")
    start = data["startingState"]
    accepting, trans = set(), {}
    for name, info in data.items():
        if name == "startingState":
            continue
        trans[name] = []
        if info.get("isTerminatingState"):
            accepting.add(name)
        for label, dst in info.items():
            if label == "isTerminatingState":
                continue
            targets = dst if isinstance(dst, list) else [dst]
            for t in targets:
                trans[name].append((label, t))
    for name in list(trans):
        for _, t in trans[name]:
            if t not in trans:
                trans[t] = []
    if start not in trans:
        trans[start] = []
    return start, accepting, trans


def epsilon_closure(states, trans):
    closure, stack = set(states), list(states)
    while stack:
        s = stack.pop()
        for label, dst in trans[s]:
            if label == EPSILON and dst not in closure:
                closure.add(dst)
                stack.append(dst)
    return frozenset(closure)


def char_set_to_label(chars, original_labels):
    """Readable label for a set of characters, reusing the NFA's labels when possible."""
    if chars == set(ALPHANUMERIC):
        return "."
    for label in original_labels:
        if label_chars(label) == chars:
            return label
    ordered = sorted(chars, key=ALPHANUMERIC.index)
    if len(ordered) == 1:
        return ordered[0]
    parts, k = [], 0
    while k < len(ordered):
        j = k
        while (j + 1 < len(ordered) and ord(ordered[j + 1]) == ord(ordered[j]) + 1
               and char_category(ordered[j + 1]) == char_category(ordered[k])):
            j += 1
        if j - k >= 2:
            parts.append(f"{ordered[k]}-{ordered[j]}")
        else:
            parts.extend(ordered[k:j + 1])
        k = j + 1
    return "[" + "".join(parts) + "]"


def build_alphabet(trans):
    """
    NFA labels may overlap (e.g. "a", "[a-c]" and "."), so the DFA cannot use
    them directly as symbols.  Split the characters into disjoint groups of
    characters that behave identically for every label; each group becomes one
    DFA input symbol.  Returns {dfa_symbol: set_of_nfa_labels_it_belongs_to}.
    """
    labels = []
    for edges in trans.values():
        for label, _ in edges:
            if label != EPSILON and label not in labels:
                labels.append(label)
    label_sets = {label: label_chars(label) for label in labels}
    groups = {}  # signature (labels containing the char) -> chars
    for ch in ALPHANUMERIC:
        signature = frozenset(l for l in labels if ch in label_sets[l])
        if signature:
            groups.setdefault(signature, set()).add(ch)
    alphabet = {}
    for signature, chars in groups.items():
        alphabet[char_set_to_label(chars, labels)] = signature
    return alphabet


def subset_construction(start, accepting, trans):
    alphabet = build_alphabet(trans)
    symbols = list(alphabet)
    start_set = epsilon_closure({start}, trans)
    dfa_states, dfa_trans, queue = [start_set], {}, [start_set]
    while queue:
        current = queue.pop(0)
        dfa_trans[current] = {}
        for sym in symbols:
            labels = alphabet[sym]
            moved = {dst for s in current for label, dst in trans[s] if label in labels}
            if not moved:
                continue
            target = epsilon_closure(moved, trans)
            if target not in dfa_trans and target not in queue:
                dfa_states.append(target)
                queue.append(target)
            dfa_trans[current][sym] = target
    dfa_accepting = {S for S in dfa_states if S & accepting}
    return start_set, dfa_states, dfa_accepting, dfa_trans, symbols


def minimize(start, states, accepting, trans, symbols):
    """
    Partition refinement (Moore's algorithm).  The DFA from subset construction
    is partial, so a dead state is added to make it complete, the partition is
    refined until stable, and the dead group is removed at the end.
    """
    DEAD = "__dead__"
    all_states = list(states) + [DEAD]
    delta = {s: dict(trans[s]) for s in states}
    delta[DEAD] = {}

    def move(s, sym):
        return delta[s].get(sym, DEAD)

    group_of = {s: (0 if s in accepting else 1) for s in all_states}
    while True:
        signatures, new_group_of = {}, {}
        for s in all_states:
            sig = (group_of[s],) + tuple(group_of[move(s, sym)] for sym in symbols)
            if sig not in signatures:
                signatures[sig] = len(signatures)
            new_group_of[s] = signatures[sig]
        stable = len(signatures) == len(set(group_of.values()))
        group_of = new_group_of
        if stable:
            break

    dead_group = group_of[DEAD]
    min_trans = {}
    for s in states:
        g = group_of[s]
        if g == dead_group or g in min_trans:
            continue
        min_trans[g] = []
        for sym in symbols:
            tg = group_of[move(s, sym)]
            if tg != dead_group:
                min_trans[g].append((sym, tg))
    min_accepting = {group_of[s] for s in accepting}
    min_start = group_of[start]
    if min_start == dead_group:  # language is empty: keep a single rejecting state
        min_trans[min_start] = []
    return min_start, min_accepting, min_trans


def nfa_to_min_dfa(nfa):
    """Part 2: takes the NFA dict (JSON format), returns the minimized DFA dict."""
    start, accepting, trans = read_automaton(nfa)
    d_start, d_states, d_accepting, d_trans, symbols = subset_construction(start, accepting, trans)
    m_start, m_accepting, m_trans = minimize(d_start, d_states, d_accepting, d_trans, symbols)
    return number_states(m_start, lambda g: m_trans[g], m_accepting)


# ---------------------------------------------------------------------------
# Output: JSON files and graph images
# ---------------------------------------------------------------------------

def save_json(automaton, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(automaton, f, indent=2, ensure_ascii=False)
    return path


def draw_automaton(automaton, path_without_ext, title=""):
    """Draws the automaton with graphviz: double circles = accepting states."""
    import graphviz  # graphics library, used only for drawing

    g = graphviz.Digraph(format="png")
    g.attr(rankdir="LR", label=title, labelloc="t", fontsize="16",
           nodesep="0.5", ranksep="0.7", splines="true", overlap="false")
    g.attr("node", fontname="Helvetica", style="filled", fillcolor="#eef2ff")
    g.attr("edge", fontname="Helvetica", fontsize="12")

    g.node("__start__", shape="point", width="0.12", fillcolor="black")
    for name, info in automaton.items():
        if name == "startingState":
            continue
        accept = info["isTerminatingState"]
        g.node(name, shape="doublecircle" if accept else "circle",
               fillcolor="#c8f7c5" if accept else "#eef2ff")
    g.edge("__start__", automaton["startingState"], label="start")

    for name, info in automaton.items():
        if name == "startingState":
            continue
        edges = {}  # merge labels of parallel edges into one arrow
        for label, dst in info.items():
            if label == "isTerminatingState":
                continue
            for t in (dst if isinstance(dst, list) else [dst]):
                edges.setdefault(t, []).append(label)
        for t, labels in edges.items():
            g.edge(name, t, label=", ".join(labels))

    return g.render(path_without_ext, cleanup=True)


def run_all(regex, out_dir="output", draw=True):
    """Produces the 4 outputs: part-1 JSON + graph, part-2 JSON + graph."""
    os.makedirs(out_dir, exist_ok=True)
    nfa = regex_to_nfa(regex)
    dfa = nfa_to_min_dfa(nfa)
    files = [save_json(nfa, os.path.join(out_dir, "nfa.json")),
             save_json(dfa, os.path.join(out_dir, "min_dfa.json"))]
    if draw:
        files.append(draw_automaton(nfa, os.path.join(out_dir, "nfa"), f"NFA for {regex}"))
        files.append(draw_automaton(dfa, os.path.join(out_dir, "min_dfa"), f"Minimized DFA for {regex}"))
    return nfa, dfa, files


# ---------------------------------------------------------------------------
# Command-line interface
# ---------------------------------------------------------------------------

def main(argv):
    if len(argv) == 2 and argv[0] == "convert":
        nfa = regex_to_nfa(argv[1])
        print(json.dumps(nfa, indent=2, ensure_ascii=False))
        save_json(nfa, "nfa.json")
        draw_automaton(nfa, "nfa", f"NFA for {argv[1]}")
        print("Saved nfa.json and nfa.png")
    elif len(argv) == 2 and argv[0] == "minimize":
        with open(argv[1], encoding="utf-8") as f:
            nfa = json.load(f)
        dfa = nfa_to_min_dfa(nfa)
        print(json.dumps(dfa, indent=2, ensure_ascii=False))
        save_json(dfa, "min_dfa.json")
        draw_automaton(dfa, "min_dfa", "Minimized DFA")
        print("Saved min_dfa.json and min_dfa.png")
    elif len(argv) == 1:
        _, _, files = run_all(argv[0])
        print("Saved:", ", ".join(files))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RegexError as e:
        print(f"Invalid regular expression: {e}")
        sys.exit(1)
