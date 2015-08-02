import random
from contextlib import contextmanager

import pymysql

from glacia.debug import color


# Read config file
import configparser
config = configparser.RawConfigParser()
config.read('/etc/glacia.conf')


class CompilerState(object):
    """
    Keeps track of generated temp variables in a glacia compilation.

    """

    def __init__(self):
        self.__temp_var_index = -1

    def next_id(self):
        self.__temp_var_index += 1
        return 'temp_var_' + str(self.__temp_var_index)

    def next_id_binding(self):
        return Binding([Token('identifier', self.next_id())])


@contextmanager
def close_after(ret):
    try:
        yield ret
    finally:
        ret.close()


class Database(object):
    def __init__(self):
        self.__conn = None

    def conn(self):
        if self.__conn is None:
            def rq(s):
                if s.startswith('"') and s.endswith('"'):
                    s = s[1:-1]
                return s

            self.__conn = pymysql.connect(host=rq(config.get('db', 'host')),
                                          port=int(config.get('db', 'port')),
                                          user=rq(config.get('db', 'user')),
                                          passwd=rq(config.get('db', 'passwd')),
                                          db=rq(config.get('db', 'db')))

        return self.__conn

    def close(self):
        if self.__conn is not None:
            self.__conn.close()

    def commit(self):
        self.__conn.commit()

    def cur(self):
        return close_after(self.conn().cursor(pymysql.cursors.DictCursor))

    def cmd(self, *args):
        with self.cur() as cur:
            cur.execute(*args)
            return cur.rowcount

    def autoid(self, *args):
        for i in range(10):
            # Randomly generate an ID
            new = ""
            for j in range(3):
                c = 48 + random.randrange(0, 36)
                if c > 57: c += 39
                new += chr(c)

            temp_args = []
            for arg in args:
                temp_args.append(arg)

            try:
                temp_args[0] = args[0].replace('{$id}', "'" + new + "'")
                self.cmd(*temp_args)
                return new
            except pymysql.err.IntegrityError as e:
                print("id collision")
                if i == 9:
                    raise e

    def res(self, *args):
        with self.cur() as cursor:
            cursor.execute(*args)
            for row in cursor:
                yield row

    def all(self, *args):
        return [row for row in self.res(*args)]

    def first(self, *args):
        for row in self.res(*args):
            return row

    def scalar(self, *args):
        ret = self.first(*args)

        if ret is not None:
            for k,v in ret.items():
                return v


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


class Labelable(object):

    def __init__(self):
        self.label = None

    def str_label(self):
        return '' if self.label == None else self.label + ': '


class Instruction(Labelable):

    def __init__(self, kind):
        super().__init__()

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

    def copy(self):
        return Binding(self.tokens[:])


class Expression(object):

    def __init__(self, tokens, process_calls=True):
        self.kind = 'expression'
        self.tokens = tokens

        if process_calls:
            identify_calls(self)

    def __str__(self):
        return color.print('expr<', 'green')+ \
               ''.join([str(t) for t in self.tokens])+ \
               color.print('>', 'green')


class Parameter(object):

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return 'param<'+self.name+'>'


class Argument(object):

    def __init__(self, expression):
        self.kind = 'argument'
        self.expression = expression

    def __str__(self):
        return 'arg<'+str(self.expression)+'>'


class Call(Labelable):

    def __init__(self, binding, params):
        super().__init__()

        self.kind = 'call'
        self.binding = binding
        self.params = params

    def __str__(self):
        return self.str_label()+\
               color.print('call<', 'red')+str(self.binding)+ \
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
                           ",".join([str(a) for a in self.params]) + ")",
                           "purple") + \
               color.print('>', 'red') + "\n" + super().__str__()


class If(Block):

    def __init__(self, expression):
        super().__init__('if')

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)
        return tabs+self.str_label()+"if (" + str(self.expression) + ")\n" + \
               super().block_str(indent=indent)


class Else(Block):

    def __init__(self, expression=None):
        super().__init__('else')

        if expression is None:
            expression = Expression([Token('keyword', 'true')])

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)

        expr = ''
        if self.expression is not None:
            expr = ' if (' + str(self.expression) + ')'

        return tabs+self.str_label()+\
               "else" + expr + "\n" + super().block_str(indent=indent)


class While(Block):

    def __init__(self, expression):
        super().__init__('while')

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)
        return tabs + self.str_label() + \
               'while (' + str(self.expression) + ')\n' + \
               super().block_str(indent=indent)


class Foreach(Block):

    def __init__(self, expression):
        super().__init__('foreach')

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)
        return tabs + self.str_label() + \
               'foreach (' + str(self.expression) + ')\n' + \
               super().block_str(indent=indent)


class For(Block):

    def __init__(self, expression):
        super().__init__('for')

        self.expression = expression

    def block_str(self, indent=0):
        tabs = Block.indent(indent - 1)
        return tabs + self.str_label() + \
               'for (' + str(self.expression) + ')\n' + \
               super().block_str(indent=indent)


class Break(Instruction):

    def __init__(self, expression):
        super().__init__('break')

        self.expression = expression

    def __str__(self):
        return self.str_label() + 'break' + \
               ('' if self.expression is None else ' ' + str(self.expression))


class Continue(Instruction):

    def __init__(self, expression):
        super().__init__('continue')

        self.expression = expression

    def __str__(self):
        return self.str_label() + 'continue' + \
               ('' if self.expression is None else ' ' + str(self.expression))


class Return(Instruction):

    def __init__(self, expression):
        super().__init__('return')

        self.expression = expression

    def __str__(self):
        return self.str_label() + 'return ' + str(self.expression)


class Yield(Instruction):

    def __init__(self, expression):
        super().__init__('yield')

        self.expression = expression

    def __str__(self):
        return self.str_label() + 'yield ' + str(self.expression)


class YieldBreak(Instruction):

    def __init__(self):
        super().__init__('yield break')

    def __str__(self):
        return self.str_label() + 'yield break'


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

        return self.str_label() + \
               'assignment<'+mods+str(self.binding)+' = '+str(self.expression)+\
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
