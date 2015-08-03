import json

from glacia.debug import divider, print_tokens, print_nodes, print_program, \
                         print_db
from glacia import Database, close_after, CompilerState
from glacia.preprocessor import preprocess
from glacia.lexer import lex
from glacia.parser import parse
from glacia.semantics import analyze
from glacia.restructurer import restructure
from glacia.reducer import reduce
from glacia.parameterizer import parameterize
from glacia.sweetener import sweeten
from glacia.generator import generate
from glacia.loader import load
from glacia.interpreter import interpret, Interpreter


def run(fn=None, src=None, exec_lines=-1, verbose=False, collect_stdout=False):
    """
    Helper function for various uses of the glacia interpreter.

    Either fn or src must be specified to load a new program. If neither is
    present, the existing program in the database will be resumed.

    Arguments:
        fn (str): If present, the filename of the source code to load.
        src (str): If present, the source code to load.
        exec_lines (int): The number of lines to execute. -1 runs the program
                          until the end. 0 loads the program but does not run
                          it.
        verbose (bool): Whether to print extra information.
        collect_stdout (bool): Whether to collect and return the output of the
                               program.

    """

    if fn is not None and src is not None:
        raise Exception("fn and src cannot both be present.")

    # Read the file if needed.
    if src is None and fn is not None:
        with open(fn, 'rb') as f:
            src = f.read().decode('utf-8')

    # Compile and load the program if needed.
    if src is not None:
        state = CompilerState()

        if verbose:
            divider('Source code')
            print(src)

        src = preprocess(src)
        if verbose:
            divider('Preprocessed.')
            print(src)

            divider('Partially lexed (still with whitespace)')
        tokens = lex(src, preserve_whitespace=True)
        if verbose:
            print(print_tokens(tokens))

            divider('Lexed')
        tokens = lex(src)
        if verbose:
            print(print_tokens(tokens,identifier_color='switch',line_width=60))

        nodes = parse(tokens)
        if verbose:
            divider('Parsed')
            print(print_nodes(nodes).strip())

        program = analyze(nodes)
        if verbose:
            divider('Analyzed')
            print(print_program(program))

        def run_stage(label, func):
            func(program, state)
            if verbose:
                divider(label)
                print(print_program(program))

        run_stage('Restructured', restructure)
        run_stage('Reduced', reduce)
        run_stage('Parameterized', parameterize)

        generated = generate(program)

        with close_after(Database()) as conn:
            load(conn, generated)
            if verbose:
                divider('Loaded DBIL')
                print(print_db(conn))

            interpreter = Interpreter(conn)
            interpreter.start()

    # Run the program.
    if exec_lines != 0:
        if verbose:
            divider('Program output')

        collected = []
        def collect_func(obj):
            collected.append(obj)

        stdout_func = None
        if collect_stdout:
            stdout_func = collect_func

        with close_after(Database()) as conn:
            interpreter = Interpreter(conn, stdout_func=stdout_func)

            if exec_lines < 0:
                interpreter.run()
            else:
                for i in range(exec_lines):
                    if not interpreter.run_one_line():
                        break

        if collect_stdout:
            return collected


if __name__ == '__main__':
    run(fn='/vagrant/temp/first.glacia', verbose=True)
