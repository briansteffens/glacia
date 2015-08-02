from glacia import If, Break, Token, Expression, Assignment, Call, Binding


def restructure(program, state):
    """
    Move loop conditionals into the loop body.

    Arguments:
        program (Program): The program to restructure.

    """
    for function in program.functions:
        restructure_block(function.body, state)


def restructure_block(instructions, state):
    """
    Process a list of Instruction instances.

    """

    for i in reversed(range(len(instructions))):
        instruction = instructions[i]

        # Recursion
        if hasattr(instruction, 'body'):
            restructure_block(instruction.body, state)

        # Apply restructuring logic to the instruction
        for pre in reversed(restructure_instruction(instruction, state)):
            instructions.insert(i, pre)


def restructure_instruction(instruction, state):
    """
    Process a single instruction.

    Returns:
        A list of instructions to insert immediately before the processed
        instruction.

    """

    pre_instructions = []

    def for_call_break_out():
        if instruction.expression.tokens[2].kind == 'call':
            gen_temp = state.next_id_binding()

            pre_instructions.append(
                Assignment([], gen_temp,
                Expression([instruction.expression.tokens[2]])))

            instruction.expression.tokens[2] = gen_temp

    if instruction.kind == 'while':
        parenth = Token('parenthesis', None)
        parenth.tokens = instruction.expression.tokens

        expr = If(Expression([Token('operator', '!'), parenth]))
        expr.body.append(Break(None))

        instruction.body.insert(0, expr)
        instruction.expression = None

    elif instruction.kind == 'for':
        # Initialize the item variable (f in "for (f in items)")
        pre_instructions.append(Assignment([],
                                instruction.expression.tokens[0],
                                Expression([Token('numeric', '0')])))

        # Calls should be broken out before the loop.
        for_call_break_out()

        # Inside the loop, start by calling next() on the generator.
        next_bind = instruction.expression.tokens[2].copy()
        next_bind.tokens.append(Token('operator', '.'))
        next_bind.tokens.append(Token('identifier', 'next'))

        gen_next = Assignment([], instruction.expression.tokens[0],
                              Expression([Call(next_bind, [])]))

        instruction.body.insert(0, gen_next)

        # Then check if the generator is finished and break the loop if so.
        finished_bind = instruction.expression.tokens[2].copy()
        finished_bind.tokens.append(Token('operator', '.'))
        finished_bind.tokens.append(Token('identifier', 'finished'))

        gen_finished = If(Expression([Call(finished_bind, [])]))
        gen_finished.body.append(Break(None))

        instruction.body.insert(1, gen_finished)

        instruction.expression = None

    elif instruction.kind == 'foreach':
        # Generate a temp var to use as the indexer.
        indexer_temp_var = state.next_id_binding()

        # Set the temp var to -1 before the foreach loop.
        pre_instructions.append(Assignment([], indexer_temp_var,
                                Expression([Token('numeric', '-1')])))

        # Initialize the item variable (f in "foreach (f in items)")
        pre_instructions.append(Assignment([],
                                instruction.expression.tokens[0],
                                Expression([Token('numeric', '0')])))

        # Calls should be broken out before the loop.
        for_call_break_out()

        # Inside the loop, start by incrementing the indexer.
        increment = Assignment([], indexer_temp_var,
                               Expression([indexer_temp_var,
                                           Token('operator', '+'),
                                           Token('numeric', '1')]))
        instruction.body.insert(0, increment)

        # Make sure the indexer is still within bounds and break if not.
        len_bind = instruction.expression.tokens[2].copy()
        len_bind.tokens.append(Token('operator', '.'))
        len_bind.tokens.append(Token('identifier', 'len'))

        break_check = If(Expression([indexer_temp_var, Token('operator', '>='),
                         Call(len_bind, [])]))
        break_check.body.append(Break(None))
        instruction.body.insert(1, break_check)

        # Set the item variable to the current list item.
        idx = Token('square', '[')
        idx.tokens = [indexer_temp_var]

        container_bind = instruction.expression.tokens[2].copy()
        container_bind.tokens.append(idx)

        assign = Assignment([], instruction.expression.tokens[0],
                            Expression([container_bind]))

        instruction.body.insert(2, assign)
        instruction.expression = None

    return pre_instructions
