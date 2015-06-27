from glacia.common import divider, color


class Token(object):
    """
    Represents a character or token in source code.

    """

    def __init__(self, kind, val):
        self.kind = kind
        self.val = val
        self.stream = []

    def print(self, identifier_color='purple'):
        if self.kind == 'char':
            return self.val

        ret = ''

        if self.kind == 'identifier':
            return color.print(self.val, identifier_color)

        if self.kind == 'semicolon':
            return color.print(self.val, 'yellow')

        if self.kind == 'operator':
            return color.print(self.val, 'red')

        if self.kind == 'string':
            return color.print('"' + self.val + '"', 'green')

        if self.kind == 'numeric':
            return color.print(self.val, 'cyan')

        ret += ''.join([c.print(identifier_color=identifier_color)
                        for c in self.stream])

        if self.kind == 'block':
            ret = color.print('{', 'blue') + ret + color.print('}', 'blue')

        if self.kind == 'parenthesis':
            ret = color.print('(', 'blue') + ret + color.print(')', 'blue')

        if self.kind == 'square':
            ret = color.print('[', 'blue') + ret + color.print(']', 'blue')

        return ret

    def is_char(self):
        return self.kind == 'char'


class TokenStream(object):
    """
    A stream made up of Token instances, which can be text characters or tokens.
    This allows tokenizing to be done gradually in multiple passes.

    """

    def __init__(self, input_string):
        self.stream = []

        for input_char in input_string:
            self.stream.append(Token('char', input_char))

    def print(self, identifier_color='purple'):
        return ''.join([t.print(identifier_color=identifier_color)
                        for t in self.stream])


class Range(object):
    def __init__(self, start, stop):
        self.start = start
        self.stop = stop

    def each(self):
        for i in range(self.start, stop=self.stop):
            yield i


def tokenize_string_literals(ts):
    ranges = []

    quote_start = None
    for i in range(len(ts.stream)):
        t = ts.stream[i]

        if not t.is_char() or t.val != '"':
            continue

        if quote_start is None:
            # String start quote
            quote_start = i
        else:
            # Escaped quote, not the end of the string yet
            if ts.stream[i - 1].is_char() and ts.stream[i - 1].val == '\\':
                continue

            # Not escaped, end of string
            ranges.insert(0, Range(quote_start, i))

            quote_start = None

    # Tokenize any string literals found
    for r in ranges:
        val = ''.join([c.val for c in ts.stream[r.start+1:r.stop]])
        del ts.stream[r.start:r.stop+1]
        ts.stream.insert(r.start, Token('string', val))


def tokenize_structure(ts):
    kinds = {
        '{': 'block',
        '}': 'block',
        '[': 'square',
        ']': 'square',
        '(': 'parenthesis',
        ')': 'parenthesis',
    }

    opens = ['{', '[', '(']
    closes = ['}', ']', ')']

    # Tokenize one (depth-first) structure block at a time.
    while True:
        start = None
        kind = None

        for i in range(len(ts.stream)):
            t = ts.stream[i]

            if not t.is_char():
                continue

            # Mark the most recent open bracket of any kind.
            if t.val in opens:
                start = i
                kind = kinds[t.val]

            # Tokenize the content from the most recent open bracket to the
            # first close bracket encountered.
            if t.val in closes:
                if kind != kinds[t.val]:
                    raise Exception(kinds[t.val]+' where '+kind+' expected.')

                token = Token(kinds[t.val], '')
                token.stream = [ts.stream[i] for i in range(start+1, i)]
                del ts.stream[start:i+1]
                ts.stream.insert(start, token)

                break

        # All structure parsed
        if kind is None:
            break


def tokenize_operators(ts):
    # Recursive inner function tokenizes one Token.stream
    def tokenize_level(cur):
        ranges = []

        for i in range(len(cur.stream)):
            token = cur.stream[i]

            if not token.is_char():
                # Recur
                if len(token.stream) > 0:
                    tokenize_level(token)

                continue

            if token.val in ['=','>','<','!','+','-','*','^','/','.',':',';']:
                stop = i + 1

                # Check for 2-character operators like <=, !=, etc
                try:
                    next = cur.stream[i + 1]

                    if next.is_char() and next.val == '=':
                        stop += 1
                except IndexError:
                    pass

                ranges.append(Range(i, stop))

        # Tokenize any operators found
        for r in reversed(ranges):
            val = ''.join([t.val for t in cur.stream[r.start:r.stop]])
            op = Token('semicolon' if val == ';' else 'operator', val)
            del cur.stream[r.start:r.stop]
            cur.stream.insert(r.start, op)

    # Bootstrap recursion
    tokenize_level(ts)


def tokenize_identifiers(ts):
    # Recursive inner function tokenizes one Token.stream
    def tokenize_level(cur):
        start = None

        ranges = []

        for i in range(len(cur.stream)):
            token = cur.stream[i]

            if not token.is_char():
                # Recur
                if len(token.stream) > 0:
                    tokenize_level(token)

                continue

            # Identifiers can be alphanumeric and underscores
            def valid_chars(s):
                return s.isalnum() or s == ''

            # Start tracking an identifier
            if start is None and valid_chars(token.val):
                start = i

            # Detect the last character in an identifier
            if start is not None:
                if i < len(cur.stream) - 1:
                    next = cur.stream[i + 1]

                    # Next character is still part of the identifier
                    if next.is_char() and valid_chars(next.val):
                        continue

                # Identifier detected, mark its bounds
                ranges.append(Range(start, i + 1))
                start = None

        # Tokenize any identifiers found
        for r in reversed(ranges):
            val = ''.join([t.val for t in cur.stream[r.start:r.stop]])

            kind = 'identifier'

            # If the first char is a digit, it must be a numeric literal
            if val[0].isdigit():
                kind = 'numeric'
                decimal_points = 0
                for c in val:
                    if c == '.':
                        decimal_points += 1
                        if decimal_points > 1:
                            raise Exception('Too many decimal points in '+
                                            '[' + val + '].')
                    elif not c.isdigit():
                        raise Exception('Expected numeric: [' + val + '].')

            op = Token(kind, val)
            del cur.stream[r.start:r.stop]
            cur.stream.insert(r.start, op)

    # Bootstrap recursion
    tokenize_level(ts)


def remove_whitespace(ts):
    # Recursive inner function processes one Token.stream
    def process_level(cur):
        for i in reversed(range(len(cur.stream))):
            token = cur.stream[i]

            if not token.is_char():
                # Recur
                if len(token.stream) > 0:
                    process_level(token)

                continue

            if token.val in [' ','\t','\r','\n']:
                del cur.stream[i]

    # Bootstrap recursion
    process_level(ts)


def tokenize(code, stdout_debug=False):
    """
    Convert glacia source code to TokenStream format for further processing.

    :param code: The glacia source code to tokenize.
    :param stdout_debug: Whether to output debug information. Default False.
    :return: A TokenStream instance
    """

    ts = TokenStream(code)

    tokenize_string_literals(ts)
    tokenize_structure(ts)
    tokenize_operators(ts)
    tokenize_identifiers(ts)

    if stdout_debug:
        divider('Partially tokenized (still with whitespace)')
        print(ts.print())

    remove_whitespace(ts)

    if stdout_debug:
        divider('Tokenized')
        print(ts.print(identifier_color='switch'))

    return ts