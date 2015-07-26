
from glacia import (Program, Function, Expression, Binding, Assignment, If,
                    Return, Parameter, Else, While)


def analyze(root):
    """
    Perform semantic analysis on a program.

    :param root: A parsed Node instance
    :return: A Program instance
    """

    ret = Program()

    for node in root.nodes:
        ret.functions.append(analyze_function(node))

    return ret


def analyze_function(node):
    """
    Perform semantic analysis on a function.

    :param node: A parsed Node instance
    :return: A Function instance
    """

    func = Function()
    func.return_type = node.tokens.pop(0).val
    func.name = node.tokens.pop(0).val
    func.body = analyze_block_contents(node)

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
            if len(buffer) != 2:
                raise Exception('Invalid argument definition.')

            func.params.append(Parameter(buffer[0].val, buffer[1].val))

            buffer = []
            continue

    if len(node.tokens) > 0:
        raise Exception('Unexpected tokens after function def.')

    return func


def analyze_block_contents(node):
    """
    Analyze code within a block (function, if, loop, etc)

    :param node: A parsed Node instance
    :return: A list of Instruction instances
    """

    ret = []

    for n in node.nodes:
        identify_keywords(n.tokens)
        identify_bindings(n.tokens)

        if hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'if':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected if comparison expression.')

            instruction = If(Expression(n.tokens[1].tokens))
            instruction.body = analyze_block_contents(n) # Recur
            ret.append(instruction)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'else':
            expr = None

            # If this is an "else if", set the grab the conditional expression.
            if len(n.tokens) >= 2 and \
               hasattr(n.tokens[1], 'val') and n.tokens[1].val == 'if' and \
               n.tokens[2].kind == 'parenthesis':
                expr = n.tokens[2]

            instruction = Else(expression=expr)
            instruction.body = analyze_block_contents(n) # Recur
            ret.append(instruction)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'while':
            if n.tokens[1].kind != 'parenthesis':
                raise Exception('Expected while comparison expression.')

            instruction = While(Expression(n.tokens[1].tokens))
            instruction.body = analyze_block_contents(n) # Recur
            ret.append(instruction)

        elif hasattr(n.tokens[0], 'val') and n.tokens[0].val == 'return':
            ret.append(Return(Expression(n.tokens[1:])))

        else:
            assignment = identify_assignment(n.tokens)
            if assignment:
                ret.append(assignment)
            else:
                ret.append(Expression(n.tokens))


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

        if token.kind == 'identifier' and token.val in ['if', 'return', 'int',
                                                        'static', 'else',
                                                        'while']:
            token.kind = 'keyword'


def identify_bindings(tokens):
    """
    Recursively identify bindings in a list of Token instances.

    :param tokens: A list of Token instances
    :return: None
    """

    # Recursive call
    for t in tokens:
        if hasattr(t, 'tokens'):
            identify_bindings(t.tokens)

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
