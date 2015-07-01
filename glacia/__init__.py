import json
import random
from contextlib import contextmanager

import pymysql

from glacia.debug import divider, print_tokens, print_nodes, print_program
from glacia.lexer import lex
from glacia.parser import parse
from glacia.semantics import analyze


# Read config file
import configparser
config = configparser.RawConfigParser()
config.read('/etc/glacia.conf')


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
        for k,v in self.first(*args).items():
            return v


def load(db, srctree):
    # Clear existing program
    db.cmd('set foreign_key_checks = 0;')
    for table in ['locals','calls','threads','parameters','parameters',
                  'instructions','functions','arguments']:
        db.cmd('delete from ' + table + ';')
    db.cmd('set foreign_key_checks = 1;')

    def loadinstructions(arr, function_id, inst_id):
        prev = None
        for el in arr:
            prev = loadinstruction(el, function_id, inst_id, prev)

    def loadinstruction(inst, function_id, parent_id, previous_id):
        inst_id = db.autoid("insert into instructions (" +
                                "id, function_id, parent_id, previous_id, " +
                                "instruction" +
                            ") values (" +
                                "{$id}, %s, %s, %s, %s" +
                            ");",
                            (function_id, parent_id, previous_id, inst[0],))

        ordinal = 0
        for arg in inst[1:]:
            if isinstance(arg, list) and not isinstance(arg, str):
                continue

            db.autoid("insert into parameters (" +
                        "id, instruction_id, ordinal, val" +
                      ") values (" +
                        "{$id}, %s, %s, %s" +
                      ");",
                      (inst_id, ordinal, arg,))
            ordinal += 1

        if isinstance(inst[-1], list) and not isinstance(inst[-1], str):
            loadinstructions(inst[-1], function_id, inst_id)

        return inst_id

    # Load new program
    for function in srctree:
        func_id = db.autoid("insert into functions (id, label) " +
                            "values ({$id}, %s);",
                            function[1])

        ordinal = 0
        for arg in function[2:-1]:
            parts = arg.split(' ')

            if len(parts) != 2:
                raise Exception('Invalid argument syntax.')

            db.autoid("insert into arguments (id, function_id, " +
                      "label, ordinal, type) " +
                      "values ({$id}, %s, %s, %s, %s);",
                      (func_id, parts[1], ordinal, parts[0],))

            ordinal += 1

        loadinstructions(function[-1], func_id, None)

    db.commit()


class Interpreter(object):
    def __init__(self, db):
        self.db = db

    def call(self, thread_id,  func_name, arguments):
        func_id = self.db.scalar("select id from functions where label = %s;",
                                 (func_name,))

        inst_id = self.db.scalar("select id from instructions " +
                                 "where function_id = %s and " +
                                 "parent_id is null and previous_id is null;",
                                 (func_id,))

        depth = self.db.scalar("select max(depth) + 1 from calls " +
                               "where thread_id = %s",
                               (thread_id,))

        if depth is None:
            depth = 0

        call_id = self.db.autoid("insert into calls (id, thread_id, depth, " +
                                 "instruction_id) values ({$id}, %s, %s, %s);",
                                 (thread_id, depth, inst_id,))

        func_args = self.db.all("select * from arguments where function_id=%s "+
                                "order by ordinal;",
                                (func_id,))

        if len(arguments) != len(func_args):
            raise Exception('Invalid number of arguments.')

        for i in range(len(arguments)):
            self.create_local(call_id, '$' + func_args[i]['label'],
                              func_args[i]['type'], arguments[i])

        return call_id

    def set_call_instruction(self, call_id, instruction_id):
        self.db.cmd("update calls set instruction_id = %s where id = %s;",
                    (instruction_id, call_id,))

    def step_over(self, instruction_id):
        return self.db.first("select * from instructions where previous_id=%s;",
                             (instruction_id,))

    def step_into(self, instruction_id):
        return self.db.first("select * from instructions where parent_id = %s;",
                             (instruction_id,))

    def step_out(self, instruction_id):
        return self.db.first("select * from instructions where previous_id = ("+
                             "select parent_id from instructions " +
                             "where id = %s);",
                             (instruction_id,))

    def current_call(self, thread_id):
        """
        Get the frame at the top of the call stack for the given thread.

        :param thread_id: The thread to look up
        :return: The call stack frame in dict form
        """
        return self.db.first("select * from calls where thread_id = %s " +
                             "order by depth desc limit 1;",
                             (thread_id,))

    def parent_call(self, call):
        """
        Get the call stack frame directly below the given one.

        :param call: The base frame in dict form to get the parent of
        :return: The call stack frame in dict format
        """
        return self.db.first("select * from calls where thread_id = %s " +
                             "and depth = %s;",
                             (call['thread_id'], call['depth'] - 1))

    def call_instruction(self, call_id):
        """
        Get the instruction being pointed to by the given call stack frame.

        :param call_id: The call stack frame
        :return: The instruction in dict form
        """
        return self.db.first("select * from instructions where id = (" +
                             "select instruction_id from calls where id = %s);",
                             (call_id,))

    def create_local(self, call_id, label, type_, val):
        self.db.autoid("insert into locals (id, call_id, label, type, val) " +
                       "values ({$id}, %s, %s, %s, %s);",
                       (call_id, label, type_, val,))

    def get_local(self, call_id, label):
        """
        Get a local by label name within the scope of a call stack frame.

        :param call_id: The call stack frame to limit the search to
        :param label: The local label/name to search by
        :return: The local in dict format
        """
        return self.db.first("select * from locals where call_id = %s and " +
                             "label = %s;",
                             (call_id, label,))

    def set_local(self, call_id, label, val):
        self.db.cmd("update locals set val = %s where call_id = %s and " +
                    "label = %s;",
                    (val, call_id, label,))

    def exec(self, thread_id):
        """
        Run a line in the given thread.

        :param thread_id: The thread to execute.
        :return: True if the thread is still running, False if it's stopped.
        """
        call = self.current_call(thread_id)

        if call is None:
            return False

        inst = self.call_instruction(call['id'])

        self.eval(call, inst)

        # Advance instruction pointer to the next line.
        next_inst = self.step_over(inst['id'])

        # If this is the end of a block (no more lines), resume the outer block.
        if next_inst is None:
            next_inst = self.step_out(inst['id'])

        # If end of function (no more blocks), delete the call stack frame.
        if next_inst is None:
            self.db.cmd("delete from calls where id = %s;", (call['id'],))

        # A new instruction was found, update the call stack frame.
        else:
            self.set_call_instruction(call['id'], next_inst['id'])

        # Execution can continue
        return True

    def parameters(self, inst):
        """
        Get an instruction's parameters.

        :param inst: The instruction to look up.
        :return: A list of strings, one for each parameter, in order.
        """
        return [r['val'] for r in
                self.db.all("select val from parameters " +
                            "where instruction_id=%s order by ordinal;",
                            (inst['id'],))]

    def eval_expression(self, call, expr):
        if expr.startswith('$'):
            expr = self.get_local(call['id'], expr)['val']

        return expr

    def eval(self, call, inst):
        """
        Evaluate an instruction.

        :param inst: The instruction to evaluate in dict format.
        :return:
        """
        params = self.parameters(inst)

        #print(inst['instruction'] + " " + " ".join(params))

        if inst['instruction'] == 'var':
            self.create_local(call['id'], params[1], params[0], params[2])
        elif inst['instruction'] == 'set':
            self.set_local(call['id'], params[0], params[1])
        elif inst['instruction'] == 'call':
            self.call(call['thread_id'], params[1], params[2:])
        elif inst['instruction'] == 'sub':
            self.call(call['thread_id'], params[0], params[1:])
        elif inst['instruction'] == 'print':
            print('[ glacia ] ' + self.eval_expression(call, params[0]))
        elif inst['instruction'] == 'ret':
            self.eval_ret(call, inst, params[0])

    def eval_ret(self, call, inst, val):
        # Look up the call stack frame we're returning to.
        parent = self.parent_call(call)

        # Get the call instruction that invoked the now-returning function.
        parent_inst = self.call_instruction(parent['id'])
        params = self.parameters(parent_inst)

        # Map the return value to the variable in the call instruction.
        self.set_local(parent['id'], params[0], self.eval_expression(call, val))

    def run(self):
        thread_id = self.db.autoid("insert into threads (id) values ({$id});")

        self.call(thread_id, 'main', [])

        try:
            while self.exec(thread_id):
                pass
        finally:
            self.db.commit()


if __name__ == '__main__':
    with close_after(Database()) as conn:
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

        #with open('/vagrant/temp/first.json', 'rb') as f:
        #    load(conn, json.loads(f.read().decode('utf-8')))

        #Interpreter(conn).run()
