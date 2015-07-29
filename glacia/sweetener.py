from glacia import Assignment, Expression, Token


def sweeten(program, state):
    """
    Apply syntactic sugar.

    """
    for function in program.functions:
        sweeten_block(function.body)


def sweeten_block(instructions):
    for i in range(len(instructions)):
        sweetened = sweeten_instruction(instructions[i])

        if sweetened is not None:
            instructions[i] = sweetened

        # Recursion
        if hasattr(instructions[i], 'body'):
            sweeten_block(instructions[i].body)


def sweeten_instruction(instruction):
    instruction = sweeten_default_values(instruction)

    return instruction


def sweeten_default_values(instruction):
    """
    Add default values to local declarations. Ex: "int c;" becomes "int c = 0;".

    """
    if not hasattr(instruction, 'kind') or instruction.kind != 'expression' \
       or len(instruction.tokens) <= 1:
        return

    # Expecting a series of keyword modifiers followed by a binding.
    mods = instruction.tokens[:-1]
    binding = instruction.tokens[-1]

    # Validate the above expectations.
    for token in mods:
        if token.kind != 'keyword':
            return

    if binding.kind != 'binding':
        return

    # Create the replacement instruction.
    return Assignment(mods, binding, Expression([Token('numeric','0')]))
