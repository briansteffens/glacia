import json

from glacia.debug import divider, print_tokens, print_nodes, print_program, \
                         print_db
from glacia import Database, close_after
from glacia.lexer import lex
from glacia.parser import parse
from glacia.semantics import analyze
from glacia.reducer import reduce
from glacia.parameterizer import parameterize
from glacia.generator import generate
from glacia.loader import load
from glacia.interpreter import interpret


if __name__ == '__main__':
    with open('/vagrant/temp/first.glacia', 'rb') as f:
        raw = f.read().decode('utf-8')

    divider('Source code')
    print(raw)

    divider('Partially lexed (still with whitespace)')
    tokens = lex(raw, preserve_whitespace=True)
    print(print_tokens(tokens))

    divider('Lexed')
    tokens = lex(raw)
    print(print_tokens(tokens, identifier_color='switch', line_width=60))

    nodes = parse(tokens)
    divider('Parsed')
    print(print_nodes(nodes).strip())

    program = analyze(nodes)
    divider('Analyzed')
    print(print_program(program))

    reduce(program)
    divider('Reduced')
    print(print_program(program))

    parameterize(program)
    divider('Parameterized')
    print(print_program(program))
    #import sys
    #sys.exit()
    generated = generate(program)
    divider('Generated DBIL')
    print(json.dumps(generated, indent=4, sort_keys=True))

    with close_after(Database()) as conn:
        load(conn, generated)
        divider('Loaded DBIL')
        print(print_db(conn))

        divider('Program output')
        interpret(conn)
