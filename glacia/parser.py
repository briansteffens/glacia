
from glacia.lexer import Token


class StructureToken(Token):

    def __init__(self, kind, tokens):
        super().__init__(kind, '')

        self.tokens = tokens


class Node(object):
    """
    A node of a syntax tree is a series of tokens, optionally with a block
    of child nodes.

    Nodes are separated by semicolons and structure is determined by curly
    brackets.

    So for a function like:

        int f(int x)
        {
            return x * 5;
        }

    The tokens would be: int, f, (, int, x, )
    And child nodes would be one sub-node with tokens of: return, x, *, 5

    """

    def __init__(self):
        self.tokens = []
        self.nodes = []


def parse(ts):
    """
    Convert a flat stream of tokens into a syntax tree.

    :param ts: A list of Token instances
    :return: A Node instance representing the root of the syntax tree
    """

    r = Node()
    __structure_tokens(ts)
    r.nodes = [p for p in __parse(ts)]
    return r



def __structure_tokens(ts):
    """
    Parse parenthesis and square brackets into StructureToken instances.

    """

    class Open(object):
        def __init__(self, start, kind):
            self.start = start
            self.kind = kind

    kinds = {
        '(': 'parenthesis',
        ')': 'parenthesis',
        '[': 'square',
        ']': 'square',
    }

    opens = []
    i = -1

    # Manual looping so the loop position (i) can seek around as needed
    while i + 1 < len(ts):
        i += 1
        token = ts[i]

        if not (token.kind == 'structure' and token.val in ('(',')','[',']')):
            continue

        # Mark all open parenthesis and square brackets
        if token.val in ['(', '[']:
            opens.append(Open(i, kinds[token.val]))

        # When they close, 'consume' the tokens between here and the last open
        if token.val in [')', ']']:
            if len(opens) < 1:
                raise Exception('Unexpected character: ' + token.val)

            o = opens.pop()

            if o.kind != kinds[token.val]:
                raise Exception('Unexpected character: ' + token.val)

            replacement = StructureToken(kinds[token.val], ts[o.start+1:i])

            del ts[o.start:i+1]
            ts.insert(o.start, replacement)

            i = o.start - 1

    if len(opens) > 0:
        raise Exception('Unterminated ' + opens[-1].kind)


# Parses curly brackets into 'nodes' structure
def __parse(ts):
    """
    Parse curly brackets into recursive Node.nodes structure.

    """
    ret = None

    while len(ts) > 0:
        if ret is None:
            ret = Node()

        token = ts.pop(0)

        # Curly brackets control recursion
        if token.kind == 'structure' and token.val in ['{', '}']:
            if token.val == '{':
                # Recur
                ret.nodes = [p for p in __parse(ts)]
                ret = yield ret
            elif token.val == '}':
                if len(ret.nodes) > 0 or len(ret.tokens) > 0:
                    yield ret
                raise StopIteration

        # Semicolons delimit instructions
        elif token.kind == 'semicolon':
            ret = yield ret

        # All other tokens should be considered part of the instruction
        else:
            ret.tokens.append(token)