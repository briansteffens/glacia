import json

from glacia.debug import divider, print_tokens, print_nodes, print_program, \
                         print_db
from glacia import Database, close_after
from glacia.lexer import lex
from glacia.parser import parse
from glacia.semantics import analyze
from glacia.reducer import reduce
from glacia.parameterizer import parameterize
from glacia.sweetener import sweeten
from glacia.generator import generate
from glacia.loader import load
from glacia.interpreter import interpret


def run(src, verbose=False, collect_stdout=False):
    if verbose:
        divider('Source code')
        print(src)

        divider('Partially lexed (still with whitespace)')
    tokens = lex(src, preserve_whitespace=True)
    if verbose:
        print(print_tokens(tokens))

        divider('Lexed')
    tokens = lex(src)
    if verbose:
        print(print_tokens(tokens, identifier_color='switch', line_width=60))

    nodes = parse(tokens)
    if verbose:
        divider('Parsed')
        print(print_nodes(nodes).strip())

    program = analyze(nodes)
    if verbose:
        divider('Analyzed')
        print(print_program(program))

    reduce(program)
    if verbose:
        divider('Reduced')
        print(print_program(program))

    parameterize(program)
    if verbose:
        divider('Parameterized')
        print(print_program(program))

    sweeten(program)
    if verbose:
        divider('Sweetened')
        print(print_program(program))

    generated = generate(program)
    #if verbose:
    #    divider('Generated DBIL')
    #    print(json.dumps(generated, indent=4, sort_keys=True))

    with close_after(Database()) as conn:
        load(conn, generated)
        if verbose:
            divider('Loaded DBIL')
            print(print_db(conn))

            divider('Program output')

        collected = []
        def collect_func(obj):
            collected.append(obj)

        stdout_func = None
        if collect_stdout:
            stdout_func = collect_func

        interpret(conn, stdout_func=stdout_func)

        if collect_stdout:
            return collected


if __name__ == '__main__':
    with open('/vagrant/temp/first.glacia', 'rb') as f:
        run(f.read().decode('utf-8'), verbose=True)
