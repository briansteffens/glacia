
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
    r.nodes = [p for p in __parse(ts)]
    return r


def __parse(ts):
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