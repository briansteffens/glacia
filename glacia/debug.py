
class ConsoleColor(object):
    def __init__(self):
        self.__seq = 40

    def printn(self, s, num):
        if num is not None:
            s = '\033[' + str(num) + 'm' + s + '\033[0m'

        return s

    def print(self, s, clr):
        if clr == 'switch':
            self.__seq = 40 if self.__seq == 100 else 100
            n = self.__seq
        else:
            n = {
                'white': None,
                'red': 91,
                'green': 92,
                'yellow': 93,
                'blue': 94,
                'purple': 95,
                'cyan': 96
            }[clr]

        return self.printn(s, n)


color = ConsoleColor()


def divider(s):
    print('\n--- '+s+' '+''.join(['-' for d in range(80 - len(s) - 5)])+'\n')


def print_tokens(ts, identifier_color='purple', line_width=None):
    def print_token(token):
        if token.kind == 'char':
            return token.val

        # If the token has sub-tokens
        if hasattr(token, 'tokens'):
            val = ''.join([print_token(t) for t in token.tokens])

            if token.kind == 'parenthesis':
                return '(' + val + ')'
            elif token.kind == 'square':
                return '[' + val + ']'
            else:
                raise Exception('Invalid StructureToken.')

        return color.print(token.val, {
            'identifier': identifier_color,
            'semicolon': 'yellow',
            'operator': 'red',
            'string': 'green',
            'numeric': 'cyan',
            'structure': 'blue',
            'parenthesis': 'blue',
            'square': 'blue',
        }[token.kind])

    ret = ''
    i = 0

    for c in ts:
        if c.val:
            i += len(c.val)

        if line_width and i >= line_width:
            i = len(c.val)
            ret += '\n'

        ret += print_token(c)

    return ret


def print_nodes(node, depth=-1):
    return (''.join(['\t' for t in range(depth)]) +
            print_tokens(node.tokens, identifier_color='switch') + '\n' +
            ''.join([print_nodes(c, depth + 1) for c in node.nodes]))


def print_program(program):
    return '\n'.join([str(f) for f in program.functions]) + '\n'


def print_db(db):
    ret = ''

    for r in db.all('select * from functions;'):
        ret += '\t'.join([r['id'],r['return_type'],r['label'],
                          r['arguments']])+'\n'

    ret += '\n'

    for r in db.all('select * from instructions;'):
        ret += '\t'.join([r[c] if r[c] else 'NUL'
                          for c in ['id','function_id','parent_id',
                                    'previous_id','code']]) + '\n\n'

    return ret
