
from glacia import Assignment, Call, Binding, Expression, Token, CompilerState


class CallFound(object):
    """
    Represents a Call instance found in an array of tokens.

    """

    def __init__(self, ar, ar_index, call, depth):
        self.ar = ar
        self.ar_index = ar_index
        self.call = call
        self.depth = depth


def reduce(program, state):
    """
    Break nested function calls out into multiple lines with temp variables.

    :param program: A Program instance
    :return: None
    """
    for function in program.functions:
        reduce_block(function.body, state)


def reduce_block(instructions, state):
    """
    Process a list of Instruction instances.

    :param instructions: A list of Instruction instances
    :param state: An instance of CompilerState
    :return:None
    """

    i = 0
    while i < len(instructions):
        instruction = instructions[i]

        # Separate nested calls into separate lines
        for added in extract_calls(instruction, state):
            instructions.insert(i, added)
            i += 1

        # Recursion
        if hasattr(instruction, 'body'):
            reduce_block(instruction.body, state)

        if isinstance(instruction, Expression) and len(instruction.tokens) == 1:
            # If there's just a binding left it can be deleted.
            if isinstance(instruction.tokens[0], Binding):
                del instructions[i]

            # If there's just a call left it can be broken out of the expr.
            if isinstance(instruction.tokens[0], Call):
                instructions[i] = instruction.tokens[0]
                i += 1
        else:
            i += 1


def extract_calls(instruction, state):
    """
    Depth-first, replace calls with temporary variables set by previous lines.

    :param instruction: An Instruction instance
    :param state: A CompilerState instance
    :return: A generator which returns Assignment instances
    """

    # Inner function
    def __extract_calls(tokens):
        while True:
            deepest = None

            total = 0
            for found in find_calls(tokens, 1):
                total += 1
                if deepest is None or deepest.depth < found.depth:
                    deepest = found

            # No more nested calls
            if deepest is None or \
               (instruction.kind in ['assignment', 'expression']
                and total == 1 and len(tokens) == 1):
                raise StopIteration

            # Replace the call with a temporary variable and yield the call
            # as a separate assignment instruction.
            binding = state.next_id_binding()
            del deepest.ar[deepest.ar_index]
            deepest.ar.insert(deepest.ar_index, binding)
            yield Assignment([], binding,
                             Expression([deepest.call], process_calls=False))

    if hasattr(instruction, 'expression') and \
       instruction.expression is not None:
        for r in __extract_calls(instruction.expression.tokens):
            yield r

    if hasattr(instruction, 'tokens'):
        for r in __extract_calls(instruction.tokens):
            yield r


def find_calls(tokens, depth):
    """
    Find calls recursively in a list of tokens.

    :param tokens: A list of Token instances
    :param depth: Recursion start depth
    :return: A generator that returns CallFound instances
    """

    for i in range(len(tokens)):
        token = tokens[i]

        if isinstance(token, Call):
            yield CallFound(tokens, i, token, depth)

            for found in find_calls(token.params, depth + 1):
                yield found
            for found in find_calls(token.binding.tokens, depth + 1):
                yield found

        if hasattr(token, 'tokens'):
            for found in find_calls(token.tokens, depth + 1):
                yield found
