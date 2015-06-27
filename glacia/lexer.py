
class Token(object):
    """
    Represents a character or token in source code.

    """

    def __init__(self, kind, val):
        self.kind = kind
        self.val = val


def lex(code, preserve_whitespace=False):
    """
    Tokenize glacia source code.

    :param code: The raw source code to process
    :param preserve_whitespace: Whether to preserve whitespace for debugging
    :return: A list of Token instances
    """

    def tokenize(stream, start, stop, kind):
        ret = Token(kind, ''.join([t_.val for t_ in stream[start:stop]]))
        del stream[start:stop]
        stream.insert(start, ret)

        return ret

    # Identifiers can be alphanumeric and underscores
    def ident_chars(s):
        return s.isalnum() or s == ''

    ts = []
    for input_char in code:
        ts.append(Token('char', input_char))

    quote_stop = None
    ident_stop = None

    for i in reversed(range(len(ts))):
        token = ts[i]

        if not token.kind == 'char':
            continue

        try:
            prev = ts[i - 1]
        except IndexError:
            prev = None

        # Quote processing
        if token.val == '"':
            if quote_stop is None:
                # String stop quote
                quote_stop = i + 1
            else:
                # Make sure the quote isn't escaped
                if not (prev.kind == 'char' and prev.val == '\\'):
                    tokenize(ts, i, quote_stop, 'string')
                    quote_stop = None

        # Inside of a quote, no other processing is valid until the quote ends.
        if quote_stop:
            continue

        # Start tracking an identifier
        if ident_stop is None and ident_chars(token.val):
            ident_stop = i + 1

        # Detect the first character in an identifier
        if ident_stop is not None:
            if i > 0:
                prev = ts[i - 1]

                # Previous character is still part of the identifier
                if prev.kind == 'char' and ident_chars(prev.val):
                    continue

            # Identifier detected, mark its bounds
            t = tokenize(ts, i, ident_stop, 'identifier')

            # If the first char is a digit, it must be a numeric literal
            if t.val[0].isdigit():
                decimal_points = 0
                for c in t.val:
                    if c == '.':
                        decimal_points += 1
                        if decimal_points > 1:
                            raise Exception('Too many decimal points in '+
                                            '[' + t.val + '].')
                    elif not c.isdigit():
                        raise Exception('Expected numeric: [' + t.val + '].')

                t.kind = 'numeric'

            ident_stop = None

        # Operators
        if token.val in ['=','>','<','!','+','-','*','^','/','.',':']:
            try:
                is_double = prev.kind == 'char' and prev.val in ['=','+','-']
            except AttributeError:
                is_double = False

            tokenize(ts, i - int(is_double), i + 1, 'operator')

        # Structure
        if token.val in ['{','}','[',']','(',')']:
            tokenize(ts, i, i + 1, 'structure').val = token.val

        # Semicolons
        if token.val == ';':
            tokenize(ts, i, i + 1, 'semicolon')

        # Whitespace
        if not preserve_whitespace and token.val in [' ','\t','\r','\n']:
            del ts[i]

    return ts