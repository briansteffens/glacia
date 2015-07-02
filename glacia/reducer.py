
from glacia.lexer import Token
from glacia.semantics import Assignment, Call, Binding, Expression


class CallFound(object):
    """
    Represents a Call instance found in an array of tokens.

    """

    def __init__(self, ar, ar_index, call, depth):
        self.ar = ar
        self.ar_index = ar_index
        self.call = call
        self.depth = depth


class ReduceState(object):
    """
    Context details for a reduce call.

    """

    def __init__(self):
        self.__temp_var_index = -1

    def next_id(self):
        self.__temp_var_index += 1
        return 'temp_var_' + str(self.__temp_var_index)


def reduce(program):
    """
    Break nested function calls out into multiple lines with temp variables.

    :param program: A Program instance
    :return: None
    """
    for function in program.functions:
        reduce_block(function.body, ReduceState())


def reduce_block(instructions, state):
    """
    Process a list of Instruction instances.

    :param instructions: A list of Instruction instances
    :param state: An instance of ReduceState
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
        if hasattr(instruction, 'nodes'):
            reduce_block(instruction.nodes, state)

        # If all that's left of the instruction after the above is an expression
        # with a binding in it, it no longer does anything and can be deleted.
        if isinstance(instruction, Expression) and \
           len(instruction.tokens) == 1 and \
           isinstance(instruction.tokens[0], Binding):
            del instructions[i]
        else:
            i += 1


def extract_calls(instruction, state):
    """
    Depth-first, replace calls with temporary variables set by previous lines.

    :param instruction: An Instruction instance
    :param state: A ReduceState instance
    :return: A generator which returns Assignment instances
    """

    # Inner function
    def __extract_calls(tokens):
        while True:
            deepest = None

            for found in find_calls(tokens, 1):
                if deepest is None or deepest.depth < found.depth:
                    deepest = found

            # No more nested calls
            if deepest is None:
                raise StopIteration

            # Replace the call with a temporary variable and yield the call
            # as a separate assignment instruction.
            binding = Binding([Token('identifier', state.next_id())])
            del deepest.ar[deepest.ar_index]
            deepest.ar.insert(deepest.ar_index, binding)
            yield Assignment([Token('keyword', 'var')], binding,
                             Expression([deepest.call], process_calls=False))

    if hasattr(instruction, 'expression'):
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