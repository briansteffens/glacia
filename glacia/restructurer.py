from glacia import If, Break, Token, Expression


def restructure(program):
    """
    Move loop conditionals into the loop body.

    Arguments:
        program (Program): The program to restructure.

    """
    for function in program.functions:
        restructure_block(function.body)


def restructure_block(instructions):
    """
    Process a list of Instruction instances.

    """

    for instruction in instructions:
        # Recursion
        if hasattr(instruction, 'body'):
            restructure_block(instruction.body)

        # Apply restructuring logic to the instruction
        restructure_instruction(instruction)


def restructure_instruction(instruction):
    """
    Process a single instruction.

    """

    if instruction.kind != 'while':
        return

    parenth = Token('parenthesis', None)
    parenth.tokens = instruction.expression.tokens

    expr = If(Expression([Token('operator', '!'), parenth]))
    expr.body.append(Break(None))

    instruction.body.insert(0, expr)
    instruction.expression = None
