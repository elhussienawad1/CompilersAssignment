"""
Compilers Programming Assignment

Part 1: regex -> NFA using Thompson's construction
Part 2: NFA -> DFA using subset construction, then minimize the DFA

Usage:
    python regex_automata.py "[A-Za-z]+[0-9]*"            # both parts
    python regex_automata.py convert "[A-Za-z]+[0-9]*"    # part 1 only
    python regex_automata.py minimize nfa.json            # part 2 only
"""

import json
import os
import sys

EPSILON = "ε"

DIGITS = "0123456789"
UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LOWER = "abcdefghijklmnopqrstuvwxyz"
ALPHANUMERIC = DIGITS + UPPER + LOWER   # this is what "." matches


def is_literal(ch):
    return ch in ALPHANUMERIC


def char_type(ch):
    # used to make sure a range like [a-Z] or [0-z] doesn't mix types
    if ch in DIGITS:
        return "digit"
    if ch in UPPER:
        return "upper"
    return "lower"


class RegexError(Exception):
    pass


# ===================== Part 1a: parsing the regex =====================
#
# Recursive descent, one function per level (lowest precedence first):
#   expr    -> concat ('|' concat)*
#   concat  -> repeat repeat*
#   repeat  -> atom ('*' | '+' | '?')*
#   atom    -> literal | '.' | '(' expr ')' | '[' class ']'
#
# The tree is made of tuples:
#   ("sym", label)   label is "a", "." or the whole class text like "[a-c]"
#   ("cat", left, right)   ("alt", left, right)
#   ("star", x)   ("plus", x)   ("opt", x)

class Parser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        if self.pos < len(self.text):
            return self.text[self.pos]
        return None

    def error(self, msg):
        # show where the problem is with a ^ under it
        arrow = " " * self.pos + "^"
        raise RegexError(f"{msg} at position {self.pos}\n  {self.text}\n  {arrow}")

    def parse(self):
        if self.text == "":
            raise RegexError("Empty regular expression")
        tree = self.parse_expr()
        # if we stopped early something is left over
        if self.pos != len(self.text):
            if self.peek() == ")":
                self.error("Unmatched ')'")
            self.error(f"Unexpected character '{self.peek()}'")
        return tree

    def parse_expr(self):
        node = self.parse_concat()
        while self.peek() == "|":
            self.pos += 1
            node = ("alt", node, self.parse_concat())
        return node

    def parse_concat(self):
        if self.peek() is None or self.peek() in "|)":
            self.error("Missing operand (empty alternative or empty group)")
        node = self.parse_repeat()
        while self.peek() is not None and self.peek() not in "|)":
            node = ("cat", node, self.parse_repeat())
        return node

    def parse_repeat(self):
        node = self.parse_atom()
        names = {"*": "star", "+": "plus", "?": "opt"}
        # a** is allowed, it just means (a*)*
        while self.peek() is not None and self.peek() in names:
            node = (names[self.peek()], node)
            self.pos += 1
        return node

    def parse_atom(self):
        ch = self.peek()
        if ch is None:
            self.error("Unexpected end of expression")

        if is_literal(ch) or ch == ".":
            self.pos += 1
            return ("sym", ch)

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
        # returns the class text as is, e.g. "[A-Za-z]"
        start = self.pos
        self.pos += 1   # skip [
        if self.peek() == "]":
            self.error("Empty character class '[]'")

        while self.peek() != "]":
            lo = self.peek()
            if lo is None:
                self.pos = start   # point at the [ that was never closed
                self.error("Missing ']' for character class")
            if not is_literal(lo):
                self.error(f"Invalid character '{lo}' inside character class")
            self.pos += 1

            if self.peek() == "-":
                self.pos += 1
                hi = self.peek()
                if hi is None or not is_literal(hi):
                    self.error("Invalid range end in character class")
                if char_type(lo) != char_type(hi) or lo > hi:
                    self.error(f"Invalid range '{lo}-{hi}'")
                self.pos += 1

        self.pos += 1   # skip ]
        return self.text[start:self.pos]


def parse_regex(text):
    return Parser(text).parse()


def label_chars(label):
    """All the characters a label matches: "a", "." or "[a-c5]"."""
    if label == ".":
        return set(ALPHANUMERIC)
    if len(label) == 1:
        return {label}

    chars = set()
    inside = label[1:-1]   # remove the brackets
    i = 0
    while i < len(inside):
        if i + 2 < len(inside) and inside[i + 1] == "-":
            for c in range(ord(inside[i]), ord(inside[i + 2]) + 1):
                chars.add(chr(c))
            i += 3
        else:
            chars.add(inside[i])
            i += 1
    return chars


# ===================== Part 1b: Thompson's construction =====================
#
# States are just numbers and trans[state] is a list of (label, next_state).
# Every fragment has one start and one accept state.
# For concatenation I used the Dragon Book version: the accept state of the
# first part and the start state of the second part become the same state
# (instead of joining them with an extra ε edge).

class NFABuilder:
    def __init__(self):
        self.trans = []

    def new_state(self):
        self.trans.append([])
        return len(self.trans) - 1

    def add(self, src, label, dst):
        self.trans[src].append((label, dst))

    def build(self, node):
        """Builds the fragment for this node and returns (start, accept)."""
        kind = node[0]

        if kind == "sym":
            start = self.new_state()
            accept = self.new_state()
            self.add(start, node[1], accept)
            return start, accept

        if kind == "cat":
            s_start, s_accept = self.build(node[1])
            t_start, t_accept = self.build(node[2])
            # merge s_accept with t_start: s_accept takes t_start's edges and
            # t_start is not used anymore. Nothing points into a start state
            # in Thompson's construction so no edges need to be redirected.
            self.trans[s_accept] = self.trans[t_start]
            self.trans[t_start] = []
            return s_start, t_accept

        if kind == "alt":
            start = self.new_state()
            s_start, s_accept = self.build(node[1])
            t_start, t_accept = self.build(node[2])
            accept = self.new_state()
            self.add(start, EPSILON, s_start)
            self.add(start, EPSILON, t_start)
            self.add(s_accept, EPSILON, accept)
            self.add(t_accept, EPSILON, accept)
            return start, accept

        # star, plus and opt use the same shape, only some edges change
        #   star: can skip and can repeat
        #   plus: can only repeat
        #   opt:  can only skip
        start = self.new_state()
        s_start, s_accept = self.build(node[1])
        accept = self.new_state()
        self.add(start, EPSILON, s_start)
        if kind == "star" or kind == "opt":
            self.add(start, EPSILON, accept)
        if kind == "star" or kind == "plus":
            self.add(s_accept, EPSILON, s_start)
        self.add(s_accept, EPSILON, accept)
        return start, accept


def to_json(start, trans, accepting):
    """
    Turns an automaton into the JSON format of the assignment.
    States get renamed S0, S1, ... in BFS order so the start is always S0.
    trans[state] is a list of (label, next_state).
    """
    # BFS to get the order of the states
    order = [start]
    i = 0
    while i < len(order):
        for label, dst in trans[order[i]]:
            if dst not in order:
                order.append(dst)
        i += 1

    names = {}
    for k in range(len(order)):
        names[order[k]] = "S" + str(k)

    result = {"startingState": names[start]}
    for state in order:
        entry = {"isTerminatingState": state in accepting}
        for label, dst in trans[state]:
            if label not in entry:
                entry[label] = names[dst]
            else:
                # a key can't repeat in JSON, so 2 ε targets become a list
                if not isinstance(entry[label], list):
                    entry[label] = [entry[label]]
                entry[label].append(names[dst])
        result[names[state]] = entry
    return result


def regex_to_nfa(regex):
    """Part 1. Returns the NFA as a dict in the JSON format."""
    tree = parse_regex(regex)
    builder = NFABuilder()
    start, accept = builder.build(tree)
    return to_json(start, builder.trans, {accept})


# ===================== Part 2: NFA -> DFA -> minimized DFA =====================

def read_automaton(data):
    """Reads the JSON dict back into (start, accepting, trans)."""
    if "startingState" not in data:
        raise ValueError("NFA JSON has no 'startingState'")
    start = data["startingState"]

    accepting = set()
    trans = {}
    for name, info in data.items():
        if name == "startingState":
            continue
        trans[name] = []
        if info.get("isTerminatingState"):
            accepting.add(name)
        for label, dst in info.items():
            if label == "isTerminatingState":
                continue
            if isinstance(dst, list):
                for d in dst:
                    trans[name].append((label, d))
            else:
                trans[name].append((label, dst))

    # a state that is only used as a target might not have its own entry
    for name in list(trans):
        for label, dst in trans[name]:
            if dst not in trans:
                trans[dst] = []
    if start not in trans:
        trans[start] = []
    return start, accepting, trans


def epsilon_closure(states, trans):
    closure = set(states)
    stack = list(states)
    while stack:
        s = stack.pop()
        for label, dst in trans[s]:
            if label == EPSILON and dst not in closure:
                closure.add(dst)
                stack.append(dst)
    return frozenset(closure)


def make_label(chars, nfa_labels):
    """Gives a set of characters a readable name to use on the DFA edges."""
    if chars == set(ALPHANUMERIC):
        return "."
    # use the same label as the NFA if one matches exactly
    for label in nfa_labels:
        if label_chars(label) == chars:
            return label

    chars = sorted(chars, key=ALPHANUMERIC.index)
    if len(chars) == 1:
        return chars[0]

    # otherwise build something like [0-9A-Zd-z]
    # (runs of 3 or more become a range, shorter ones are written out)
    text = ""
    i = 0
    while i < len(chars):
        j = i
        while (j + 1 < len(chars) and ord(chars[j + 1]) == ord(chars[j]) + 1
               and char_type(chars[j + 1]) == char_type(chars[i])):
            j += 1
        if j - i >= 2:
            text += chars[i] + "-" + chars[j]
        else:
            text += "".join(chars[i:j + 1])
        i = j + 1
    return "[" + text + "]"


def build_alphabet(trans):
    """
    The NFA labels can overlap, for example "a", "[a-c]" and "." all match 'a'.
    If the DFA used them as they are, one character could follow two edges and
    it wouldn't be deterministic anymore.
    So I group the characters by which labels match them. Characters in the same
    group behave the same everywhere, so each group is one DFA symbol.
    Returns {dfa_symbol: set of NFA labels that match it}.
    """
    nfa_labels = []
    for edges in trans.values():
        for label, dst in edges:
            if label != EPSILON and label not in nfa_labels:
                nfa_labels.append(label)

    chars_of = {}
    for label in nfa_labels:
        chars_of[label] = label_chars(label)

    groups = {}   # set of labels -> characters with exactly those labels
    for ch in ALPHANUMERIC:
        matching = []
        for label in nfa_labels:
            if ch in chars_of[label]:
                matching.append(label)
        if matching:
            key = frozenset(matching)
            if key not in groups:
                groups[key] = set()
            groups[key].add(ch)

    alphabet = {}
    for labels, chars in groups.items():
        alphabet[make_label(chars, nfa_labels)] = labels
    return alphabet


def subset_construction(start, accepting, trans):
    alphabet = build_alphabet(trans)
    symbols = list(alphabet)

    first = epsilon_closure({start}, trans)
    dfa_states = [first]
    dfa_trans = {}
    i = 0
    while i < len(dfa_states):   # dfa_states works as a BFS queue
        current = dfa_states[i]
        dfa_trans[current] = {}
        for sym in symbols:
            moved = set()
            for s in current:
                for label, dst in trans[s]:
                    if label in alphabet[sym]:
                        moved.add(dst)
            if not moved:
                continue   # no dead state here, the DFA is allowed to be partial
            target = epsilon_closure(moved, trans)
            if target not in dfa_states:
                dfa_states.append(target)
            dfa_trans[current][sym] = target
        i += 1

    dfa_accepting = set()
    for state in dfa_states:
        if state & accepting:   # has an NFA accept state inside it
            dfa_accepting.add(state)
    return first, dfa_states, dfa_accepting, dfa_trans, symbols


def minimize(start, states, accepting, trans, symbols):
    """
    Moore's algorithm (partition refinement).
    The DFA from subset construction is partial, so I add a dead state first
    to make it complete, then remove the dead group at the end.
    Returns (start, accepting, trans) where the states are group numbers.
    """
    DEAD = "dead"
    all_states = list(states) + [DEAD]

    def move(s, sym):
        if s == DEAD or sym not in trans[s]:
            return DEAD
        return trans[s][sym]

    # start with 2 groups: accepting = 0, the rest = 1
    group = {}
    for s in all_states:
        group[s] = 0 if s in accepting else 1

    while True:
        # two states stay together only if they are in the same group now
        # and go to the same groups on every symbol
        new_ids = {}
        new_group = {}
        for s in all_states:
            key = [group[s]]
            for sym in symbols:
                key.append(group[move(s, sym)])
            key = tuple(key)
            if key not in new_ids:
                new_ids[key] = len(new_ids)
            new_group[s] = new_ids[key]

        # nothing got split -> done
        done = len(new_ids) == len(set(group.values()))
        group = new_group
        if done:
            break

    # one state per group, without the dead group and the edges going to it
    dead = group[DEAD]
    min_trans = {}
    for s in states:
        g = group[s]
        if g == dead or g in min_trans:
            continue
        min_trans[g] = []
        for sym in symbols:
            target = group[move(s, sym)]
            if target != dead:
                min_trans[g].append((sym, target))

    min_accepting = set()
    for s in accepting:
        min_accepting.add(group[s])

    min_start = group[start]
    if min_start == dead:
        # the language is empty, keep just the start state with no edges
        min_trans[min_start] = []
    return min_start, min_accepting, min_trans


def nfa_to_min_dfa(nfa):
    """Part 2. Takes the NFA dict (JSON format) and returns the minimized DFA dict."""
    start, accepting, trans = read_automaton(nfa)
    d_start, d_states, d_accepting, d_trans, symbols = subset_construction(start, accepting, trans)
    m_start, m_accepting, m_trans = minimize(d_start, d_states, d_accepting, d_trans, symbols)
    return to_json(m_start, m_trans, m_accepting)


# ===================== Output: JSON files and graphs =====================

def save_json(automaton, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(automaton, f, indent=2, ensure_ascii=False)
    return path


def draw_automaton(automaton, path_without_ext, title=""):
    """Draws the automaton to a png. Accepting states are double circles."""
    import graphviz   # only used for drawing

    g = graphviz.Digraph(format="png")
    g.attr(rankdir="LR", label=title, labelloc="t", fontsize="16",
           nodesep="0.5", ranksep="0.7", splines="true", overlap="false")
    g.attr("node", fontname="Helvetica", style="filled", fillcolor="#eef2ff")
    g.attr("edge", fontname="Helvetica", fontsize="12")

    # invisible point so the start state gets an arrow into it
    g.node("__start__", shape="point", width="0.12", fillcolor="black")

    states = [name for name in automaton if name != "startingState"]
    for name in states:
        if automaton[name]["isTerminatingState"]:
            g.node(name, shape="doublecircle", fillcolor="#c8f7c5")
        else:
            g.node(name, shape="circle", fillcolor="#eef2ff")
    g.edge("__start__", automaton["startingState"], label="start")

    for name in states:
        # if a state has many edges to the same state draw one arrow "a, b"
        labels_to = {}
        for label, dst in automaton[name].items():
            if label == "isTerminatingState":
                continue
            targets = dst if isinstance(dst, list) else [dst]
            for t in targets:
                if t not in labels_to:
                    labels_to[t] = []
                labels_to[t].append(label)
        for t, labels in labels_to.items():
            g.edge(name, t, label=", ".join(labels))

    return g.render(path_without_ext, cleanup=True)


def run_all(regex, out_dir="output", draw=True):
    """Runs both parts and saves the 4 outputs in out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    nfa = regex_to_nfa(regex)
    dfa = nfa_to_min_dfa(nfa)

    files = []
    files.append(save_json(nfa, os.path.join(out_dir, "nfa.json")))
    files.append(save_json(dfa, os.path.join(out_dir, "min_dfa.json")))
    if draw:
        files.append(draw_automaton(nfa, os.path.join(out_dir, "nfa"), "NFA for " + regex))
        files.append(draw_automaton(dfa, os.path.join(out_dir, "min_dfa"), "Minimized DFA for " + regex))
    return nfa, dfa, files


# ===================== Command line =====================

def main(args):
    if len(args) == 2 and args[0] == "convert":
        nfa = regex_to_nfa(args[1])
        print(json.dumps(nfa, indent=2, ensure_ascii=False))
        save_json(nfa, "nfa.json")
        draw_automaton(nfa, "nfa", "NFA for " + args[1])
        print("Saved nfa.json and nfa.png")

    elif len(args) == 2 and args[0] == "minimize":
        with open(args[1], encoding="utf-8") as f:
            nfa = json.load(f)
        dfa = nfa_to_min_dfa(nfa)
        print(json.dumps(dfa, indent=2, ensure_ascii=False))
        save_json(dfa, "min_dfa.json")
        draw_automaton(dfa, "min_dfa", "Minimized DFA")
        print("Saved min_dfa.json and min_dfa.png")

    elif len(args) == 1:
        nfa, dfa, files = run_all(args[0])
        print("Saved:", ", ".join(files))

    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except RegexError as e:
        print("Invalid regular expression:", e)
        sys.exit(1)
