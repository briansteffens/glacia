from glacia import Argument, Expression


def parameterize(program, state):
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

        if hasattr(instruction, 'kind') and instruction.kind == 'assignment':
            try:
                if instruction.expression.tokens[0].kind == 'call':
                    parameterize_instruction(instruction.expression.tokens[0])
            except IndexError:
                pass

        # Recursion
        if hasattr(instruction, 'body'):
            parameterize_block(instruction.body)


def parameterize_assignment(instruction):
    print(instruction.expression.tokens)


def parameterize_instruction(call):
    ret = []
    buf = []

    while len(call.params) > 0:
        param = call.params.pop(0)

        # Commas separate parameters. Consume the buffer and reset.
        if param.kind in ['operator', 'char'] and param.val == ',':
            ret.append(buf)
            buf = []
            continue

        buf.append(param)

    # Consume any leftover tokens
    if len(buf) > 0:
        ret.append(buf)

    call.params = [Argument(Expression(r, process_calls=False)) for r in ret]
