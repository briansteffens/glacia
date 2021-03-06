from glacia import (Program, Function, Expression, Binding, Assignment, If,
                    Return, Parameter, Else, While, Break, Foreach, Continue,
                    Yield, YieldBreak, For)
from glacia.parser import Node


# The state of semantic analysis of a program.
class AnalysisState(object):

    def __init__(self):
        # Stores a list of tokens already processed by identify_bindings() so
        # they don't get double-processed.
        self.processed_bindings = []


def analyze(root):
    """
    Perform semantic analysis on a program.

    Arguments:
        root (Node): A parsed Node instance representing the root of a program.

    Returns:
        An analyzed Program instance.

    """

    ret = Program()
    state = AnalysisState()

    # Analyze each function.
    for node in root.nodes:
        ret.functions.append(analyze_function(state, node))

    return ret


def analyze_function(state, node):
    """
    Perform semantic analysis on a function.

    Arguments:
        state (AnalysisState): The analyzer state.
        node (Node): A parsed Node instance representing a function.

    Returns:
        A Function instance.

    """

    func = Function()
    func.return_type = node.tokens.pop(0).val
    func.name = node.tokens.pop(0).val
    func.body = analyze_block_contents(state, node)

    params = node.tokens.pop(0)

    if params.kind != 'parenthesis':
        raise Exception('Expected argument list.')

    params = params.tokens

    buffer = []

    # Parse function arguments
    while len(params) > 0:
        tk = params.pop(0)

        if tk.val != ',':
            buffer.append(tk)

        # End of argument in buffer
        if tk.val == ',' or (len(buffer) > 0 and len(params) == 0):
            if len(buffer) != 1:
                raise Exception('Invalid argument definition.')

            func.params.append(Parameter(buffer[0].val))

            buffer = []
            continue

    if len(node.tokens) > 0:
        raise Exception('Unexpected tokens after function def.')

    if func.return_type == 'generator' and len(func.body) > 0 and \
       func.body[-1].kind != 'yield break':
        func.body.append(YieldBreak())

    return func


def analyze_block_contents(state, node, identify=True):
    """
    Analyze code within a block (function, if, loop, etc)

    Arguments:
        state (AnalysisState): The state of the analysis.
        node (Node): The node to analyze.
        identify (bool): Whether to run identify_keywords and identify_bindings.

    Returns:
        A list of Instruction instances.

    """

    ret = []

    i = 0
    while i < len(node.nodes):
        n = node.nodes[i]

        def consume_partial(inst, token_count):
            pass_identify = True

            # If there is another command in the same instruction instead of
            # a block, create a block and add the instruction to it.
            #      EX: if (x == 3) print("a");
            # BECOMES: if (x == 3) { print("a"); }
            if len(n.tokens) > token_count:
                original_nodes = n.nodes
                n.nodes = [Node()]
                n.nodes[0].tokens = n.tokens[token_count:]
                n.nodes[0].nodes = original_nodes
                n.tokens = n.tokens[0:token_count]
                pass_identify = False

                # Pull any trailing else/else ifs up with us.
                if hasattr(n.nodes[0].tokens[0], 'val') and \
                   n.nodes[0].tokens[0].val == 'if':
                    while len(node.nodes) > i + 1 and \
                          hasattr(node.nodes[i + 1].tokens[0], 'val') and \
                          node.nodes[i + 1].tokens[0].val == 'else':
                         n.nodes.append(node.nodes[i + 1])
                         del node.nodes[i + 1]

            # Recur
            if len(n.nodes) > 0:
                inst.body = analyze_block_contents(state, n,
                                                   identify=pass_identify)

            ret.append(inst)

        # Check to see if this instruction is labeled.
        label = None
        try:
            if n.tokens[0].kind == 'identifier' and n.tokens[1].val == ':':
                label = n.tokens[0].val
                del n.tokens[0:2]
        except KeyError:
            pass
        except IndexError:
            pass

        identify_keywords(n.tokens)
        identify_bindings(state, n.tokens)

        if hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'if':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected if comparison expression.')

            instruction = If(Expression(n.tokens[1].tokens))
            consume_partial(instruction, 2)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'else':
            expr = None
            consume = 1

            # If this is an "else if", set the conditional expression.
            if len(n.tokens) >= 2 and \
               hasattr(n.tokens[1], 'val') and n.tokens[1].val == 'if' and \
               n.tokens[2].kind == 'parenthesis':
                expr = n.tokens[2]
                consume = 3

            instruction = Else(expression=expr)
            consume_partial(instruction, consume)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'while':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected while comparison expression.')

            instruction = While(Expression(n.tokens[1].tokens))
            consume_partial(instruction, 2)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'foreach':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected foreach expression.')

            instruction = Foreach(Expression(n.tokens[1].tokens))
            consume_partial(instruction, 2)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'for':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected for expression.')

            instruction = For(Expression(n.tokens[1].tokens))
            consume_partial(instruction, 2)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'return':
            ret.append(Return(Expression(n.tokens[1:])))

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'yield':
            # Check for yield break.
            if len(n.tokens) == 2 and n.tokens[1].kind == 'keyword' and \
               n.tokens[1].val == 'break':
                ret.append(YieldBreak())
            # Otherwise assume yield.
            else:
                ret.append(Yield(Expression(n.tokens[1:])))

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'break':
            ret.append(Break(None if len(n.tokens) < 2
                                  else Expression(n.tokens[1:])))

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'continue':
            ret.append(Continue(None if len(n.tokens) < 2
                                     else Expression(n.tokens[1:])))

        else:
            assignment = identify_assignment(n.tokens)
            if assignment:
                ret.append(assignment)
            else:
                ret.append(Expression(n.tokens))

        # If the instruction was labeled, apply it here.
        ret[-1].label = label

        i += 1

    return ret


def identify_assignment(tokens):
    """
    Find and identify assignment instructions (x = 5, int x = 5, etc)

    :param tokens: A list of Token instances to analyze
    :return: An Assignment instance if successful, None if the tokens could not
             be interpreted as an assignment.
    """
    for i in range(len(tokens)):
        token = tokens[i]

        # Scan token list for an assignment operator (=).
        if token.kind == 'operator' and token.val == '=':
            modifiers = []

            # If there are multiple tokens before the assignment operator, they
            # must be type information (int, string, static, etc).
            if i > 1:
                modifiers = tokens[0:i-1]

            # The token immediately before the assignment operator must be a
            # binding.
            binding = tokens[i-1]
            if binding.kind != 'binding':
                return

            return Assignment(modifiers, tokens[i-1], Expression(tokens[i+1:]))

        # Only these token kinds are valid before an assignment '=' symbol.
        if token.kind not in ['binding', 'keyword', 'identifier']:
            return


def identify_keywords(tokens):
    """
    Find and identify reserved keyword tokens.

    :param tokens: A list of Token instances
    :return: None
    """

    # Recursive call
    for t in tokens:
        if hasattr(t, 'tokens'):
            identify_keywords(t.tokens)

    for i in range(len(tokens)):
        token = tokens[i]

        if token.kind == 'keyword':
            continue

        # Also: push, pop, len
        keywords = ['if', 'return', 'int', 'static', 'else', 'while',
                    'break', 'foreach', 'in', 'bool', 'true', 'false',
                    'continue', 'generator', 'yield', 'for']

        if token.kind == 'identifier' and token.val in keywords:
            token.kind = 'keyword'


def identify_bindings(state, tokens):
    """
    Recursively identify bindings in a list of Token instances.

    :param tokens: A list of Token instances
    :return: None
    """

    # Recursive call
    for t in tokens:
        if hasattr(t, 'tokens'):
            identify_bindings(state, t.tokens)

    buffer = None

    # Helper function for checking that bindings alternate between identifiers
    # and either dot-accessors or indexers (square brackets).
    def check_alt(t1, t2):
        return ((t1.kind == 'identifier' or t1.kind == 'square') and (
            (t2.kind == 'operator' and t2.val == '.') or
            (t2.kind == 'square')
        ))

    for i in reversed(range(len(tokens))):
        token = tokens[i]

        if token in state.processed_bindings:
            continue
        else:
            state.processed_bindings.append(token)

        if token.kind == 'binding':
            continue

        found_end = False

        # Not currently in a possible binding
        if buffer is None:
            # Look for identifier or indexer to indicate a possible binding
            if token.kind in ['identifier', 'square']:
                buffer = [token]
        else:
            # As long as alternation between identifiers and dot-accessors/
            # square brackets continues, consider tokens part of the binding.
            if check_alt(token, buffer[0]) or check_alt(buffer[0], token):
                buffer.insert(0, token)
            else:
                found_end = True

        # Haven't found the end by checking token types, but hit the beginning
        # of the current indent level with a non-empty buffer, so we must
        # consider the binding ended.
        if not found_end and i == 0 and buffer:
            found_end = True
            i -= 1

        # Otherwise, consider the binding ended and consume the buffer.
        if found_end:
            end = i + 1

            for j in range(len(buffer)):
                del tokens[end]

            tokens.insert(end, Binding(buffer))
            buffer = None
