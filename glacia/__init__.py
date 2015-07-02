
from glacia.debug import color


class Token(object):
    """
    Represents a character or token in source code.

    """

    def __init__(self, kind, val):
        self.kind = kind
        self.val = val

    def __str__(self):
        v = self.val if self.val else ''

        if hasattr(self, 'tokens'):
            v = ','.join([str(t) for t in self.tokens])

        return self.kind+'<'+v+'>'


class Program(object):

    def __init__(self):
        self.functions = []


class Instruction(object):

    def __init__(self, kind):
        self.kind = kind

    def __str__(self):
        return 'instruction ' + self.kind


class Binding(object):

    def __init__(self, tokens):
        self.kind = 'binding'
        self.tokens = tokens

    def __str__(self):
        return color.print('binding<', 'yellow')+ \
               ''.join([str(t) for t in self.tokens])+ \
               color.print('>', 'yellow')


class Expression(object):

    def __init__(self, tokens, process_calls=True):
        self.tokens = tokens

        if process_calls:
            identify_calls(self)

    def __str__(self):
        return color.print('expr<', 'green')+ \
               ''.join([str(t) for t in self.tokens])+ \
               color.print('>', 'green')


class Parameter(object):

    def __init__(self, type_, name):
        self.type = type_
        self.name = name

    def __str__(self):
        return 'arg<'+self.type+" "+self.name+'>'


class Call(object):

    def __init__(self, binding, params):
        self.binding = binding
        self.params = params

    def __str__(self):
        return color.print('call<', 'red')+str(self.binding)+ \
               color.print('('+','.join([str(p) for p in self.params])+')',
                           'purple')+ \
               color.print('>', 'red')


class Block(Instruction):

    def __init__(self, kind):
        super().__init__(kind)

        self.body = []

    def __str__(self):
        return self.block_str()

    @staticmethod
    def indent(count):
        return ''.join(['\t' for i in range(count)])

    def block_str(self, indent=1):
        ret = []

        for b in self.body:
            if hasattr(b, 'block_str'):
                ret.append(b.block_str(indent + 1))
            else:
                ret.append(Block.indent(indent) + str(b))

        return '\n'.join(ret)



class Function(Block):

    def __init__(self):
        super().__init__('function')

        self.name = None
        self.return_type = None
        self.params = []

    def __str__(self):
        return color.print('func<'+self.return_type+" "+self.name, "red") + \
               color.print("(" + \
                           ",".join([str(a) for a in self.params]) + ")", "purple") + \
               color.print('>', 'red') + "\n" + super().__str__()


class If(Block):

    def __init__(self, expression):
        super().__init__('if')

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)
        return tabs+"if (" + str(self.expression) + ")\n" + \
               super().block_str(indent=indent)


class Return(Instruction):

    def __init__(self, expression):
        super().__init__('return')

        self.expression = expression

    def __str__(self):
        return 'return ' + str(self.expression)


class Assignment(Instruction):

    def __init__(self, modifiers, binding, expression):
        super().__init__('assignment')

        self.modifiers = modifiers
        self.binding = binding
        self.expression = expression

    def __str__(self):
        mods = ''
        if len(self.modifiers) > 0:
            mods = '['+','.join([str(m) for m in self.modifiers])+'] '

        return 'assignment<'+mods+str(self.binding)+' = '+str(self.expression)+ \
               '>'


def identify_calls(expr):
    """
    Recursively identify function calls in an expression and replace them with
    Call instances.

    :param expr: The Expression instance to analyze
    :return: None
    """

    # Recursive call
    for t in expr.tokens:
        if hasattr(t, 'tokens'):
            identify_calls(t)

    parenthesis = None

    for i in reversed(range(len(expr.tokens))):
        token = expr.tokens[i]

        # Not currently in a possible function call
        if parenthesis is None:
            # Look for parenthesis to indicate a possible function call
            if token.kind == 'parenthesis':
                parenthesis = token

            continue

        # A call requires a binding followed by a parenthesis. Anything other
        # than a binding here means the parenthesis was not part of a call.
        if not hasattr(token, 'kind') or token.kind != 'binding':
            parenthesis = None
            continue

        # Found a call, perform replacement
        del expr.tokens[i]
        del expr.tokens[i]

        expr.tokens.insert(i, Call(token, parenthesis.tokens))

        parenthesis = None