from glacia import Argument, Expression


def parameterize(program):
    """
    In call instructions, divide tokens into arguments by separating them on
    commas.

    """
    for function in program.functions:
        parameterize_block(function.body)


def parameterize_block(instructions):
    for instruction in instructions:
        if hasattr(instruction, 'kind') and instruction.kind == 'call':
            parameterize_instruction(instruction)

        # Recursion
        if hasattr(instruction, 'body'):
            parameterize_block(instruction.body)


def parameterize_instruction(instruction):
    ret = []
    buf = []

    while len(instruction.params) > 0:
        param = instruction.params.pop(0)

        # Commas separate parameters. Consume the buffer and reset.
        if param.kind in ['operator', 'char'] and param.val == ',':
            ret.append(buf)
            buf = []
            continue

        buf.append(param)

    # Consume any leftover tokens
    if len(buf) > 0:
        ret.append(buf)

    instruction.params = [Argument(Expression(r, process_calls=False))
                          for r in ret]
