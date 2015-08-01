
def generate(program):
    """
    Generate DBIL (Database Intermediate Language) JSON code.

    :param program: An instance of Program
    :return: DBIL code in dict format
    """

    return [{
        'cls': 'function',
        'name': f.name,
        'return_type': f.return_type,
        'params': [{
            'cls': 'param',
            'type': p.type,
            'name': p.name,
        } for p in f.params],
        'body': generate_block(f.body),
    } for f in program.functions]


def generate_block(instructions):
    """
    Recursively generate DBIL for a list of instructions.

    :param instructions: A list of Instruction instances
    :return: DBIL code in dict format
    """

    ret = []

    for instruction in instructions:
        r = {
            'cls': 'instruction',
            'kind': instruction.kind,
        }

        if hasattr(instruction, 'label') and instruction.label is not None:
            r['label'] = instruction.label

        if hasattr(instruction, 'expression') and \
           instruction.expression is not None:
            r['expression'] = generate_any(instruction.expression)

            # call instruction
            if len(instruction.expression.tokens) == 1 and \
               instruction.expression.tokens[0].kind == 'call':
                call = instruction.expression.tokens[0]
                r['target'] = generate_any(call.binding)
                r['params'] = [generate_any(p) for p in call.params]

        if hasattr(instruction, 'binding'):
            r['binding'] = generate_any(instruction.binding)

        if hasattr(instruction, 'modifiers'):
            r['modifiers'] = [m.val for m in instruction.modifiers]

        # Recursion
        if hasattr(instruction, 'body'):
            r['body'] = generate_block(instruction.body)

        if hasattr(instruction, 'params'):
            r['params'] = [generate_any(p) for p in instruction.params]

        ret.append(r)

    return ret


def generate_any(obj):
    """
    Generate a DBIL representation of a binding, literal, expression, or token.

    :param obj: An instance of Token, Binding, Expression, etc
    :return: A representation in dict format
    """
    ret = {
        'cls': obj.kind
    }

    # Recursion
    if hasattr(obj, 'tokens'):
        ret['tokens'] = [generate_any(t) for t in obj.tokens]

    if hasattr(obj, 'val'):
        ret['val'] = obj.val

        # Trim string double-quotes
        if ret['cls'] == 'string':
            ret['val'] = ret['val'][1:-1]

    if hasattr(obj, 'expression'):
        ret['expression'] = generate_any(obj.expression)

    return ret
