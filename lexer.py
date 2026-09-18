"""
UnitLang lexer.

Hand-written, single-pass, maximal-munch scanner. Produces a flat list of
Token objects; whitespace and comments are consumed but never emitted.

Design notes (matches Review 1 spec):
- Identifiers and built-in unit names (m, kg, s, km, ...) are NOT
  distinguished here. They all come out as ID tokens. Unit resolution
  happens later, in the semantic analyzer, against a pre-populated
  symbol table. The lexer doesn't need to know physics.
- Two-character operators are checked before their one-character
  prefixes (==, !=, <=, >=, &&, ||) so the scanner never mis-splits them.
- On an invalid character, the lexer records an error and skips just
  that one character, so a single run can report multiple lexical
  errors instead of stopping at the first one.
"""

from dataclasses import dataclass

KEYWORDS = {
    "qty", "fn", "if", "else", "while", "for",
    "return", "print", "true", "false", "unit",
}

# two-char operators must be matched before their one-char prefix
TWO_CHAR_OPS = {
    "==": "EQ", "!=": "NEQ", "<=": "LE", ">=": "GE",
    "&&": "AND", "||": "OR",
}
ONE_CHAR_OPS = {
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH", "^": "CARET",
    "<": "LT", ">": "GT", "!": "NOT", "=": "ASSIGN",
    ";": "SEMI", ",": "COMMA", "(": "LPAREN", ")": "RPAREN",
    "{": "LBRACE", "}": "RBRACE",
}


@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

    def __repr__(self):
        return f"Token({self.type!r}, {self.value!r}, {self.line}:{self.col})"


class LexError(Exception):
    def __init__(self, message, line, col):
        super().__init__(f"Lexical error at {line}:{col}: {message}")
        self.line, self.col = line, col


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.i = 0
        self.line = 1
        self.col = 1
        self.errors = []

    def _peek(self, offset=0):
        j = self.i + offset
        return self.src[j] if j < len(self.src) else ""

    def _advance(self):
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def tokenize(self):
        tokens = []
        while self.i < len(self.src):
            ch = self._peek()

            if ch in " \t\r\n":
                self._advance()
                continue

            if ch == "/" and self._peek(1) == "/":
                while self.i < len(self.src) and self._peek() != "\n":
                    self._advance()
                continue

            if ch == "/" and self._peek(1) == "*":
                start_line, start_col = self.line, self.col
                self._advance(); self._advance()
                closed = False
                while self.i < len(self.src):
                    if self._peek() == "*" and self._peek(1) == "/":
                        self._advance(); self._advance()
                        closed = True
                        break
                    self._advance()
                if not closed:
                    self.errors.append(
                        LexError("unterminated block comment", start_line, start_col)
                    )
                continue

            if ch.isalpha() or ch == "_":
                tokens.append(self._scan_identifier())
                continue

            if ch.isdigit():
                tokens.append(self._scan_number())
                continue

            two = ch + self._peek(1)
            if two in TWO_CHAR_OPS:
                line, col = self.line, self.col
                self._advance(); self._advance()
                tokens.append(Token(TWO_CHAR_OPS[two], two, line, col))
                continue

            if ch in ONE_CHAR_OPS:
                line, col = self.line, self.col
                self._advance()
                tokens.append(Token(ONE_CHAR_OPS[ch], ch, line, col))
                continue

            # unrecognized character: report and skip, keep scanning
            self.errors.append(LexError(f"unexpected character {ch!r}", self.line, self.col))
            self._advance()

        tokens.append(Token("EOF", "", self.line, self.col))
        return tokens, self.errors

    def _scan_identifier(self):
        line, col = self.line, self.col
        start = self.i
        while self._peek().isalnum() or self._peek() == "_":
            self._advance()
        text = self.src[start:self.i]
        ttype = text if text in KEYWORDS else "ID"
        return Token(ttype.upper() if text in KEYWORDS else "ID", text, line, col)

    def _scan_number(self):
        line, col = self.line, self.col
        start = self.i
        while self._peek().isdigit():
            self._advance()
        if self._peek() == "." and self._peek(1).isdigit():
            self._advance()
            while self._peek().isdigit():
                self._advance()
        return Token("NUM", self.src[start:self.i], line, col)
