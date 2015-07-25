import json


def interpret(db):
    Interpreter(db).run()


class Interpreter(object):
    def __init__(self, db):
        self.db = db

    def call(self, thread_id, func_name, arguments):
        #print(func_name)

        # Process built-ins
        if func_name == 'print':
            print(self.eval_expression_token(self.current_call(thread_id),
                                             arguments[0]))
            return

        function = self.db.first("select * from functions where label = %s;",
                                 (func_name,))
        function['arguments'] = json.loads(function['arguments'])

        inst_id = self.db.scalar("select id from instructions " +
                                 "where function_id = %s and " +
                                 "parent_id is null and previous_id is null;",
                                 (function['id'],))

        depth = self.db.scalar("select max(depth) + 1 from calls " +
                               "where thread_id = %s",
                               (thread_id,))

        if depth is None:
            depth = 0

        call_id = self.db.autoid("insert into calls (id, thread_id, depth, " +
                                 "instruction_id) values ({$id}, %s, %s, %s);",
                                 (thread_id, depth, inst_id,))

        if len(arguments) != len(function['arguments']):
            raise Exception('Invalid number of arguments.')

        for i in range(len(arguments)):
            self.create_local(call_id, function['arguments'][i]['name'],
                              function['arguments'][i]['type'],
                              arguments[i]['val'])

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
        ret = self.db.first("select * from instructions where id = (" +
                            "select instruction_id from calls where id = %s);",
                            (call_id,))

        ret['code'] = json.loads(ret['code'])

        return ret

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


    def eval_operator(self, call, left, oper, right):
        def coax_literal(lit):
            if isinstance(lit, dict) and 'cls' in lit:
                ret = {'val': lit['val']}
                if lit['cls'] == 'numeric':
                    ret['type'] = 'int'
                elif lit['cls'] == 'string':
                    ret['type'] = 'string'
                else:
                    raise NotImplemented
                return ret
            else:
                return lit

        def type_check(token):
            if token['type'] == 'int':
                token['val'] = int(token['val'])

            return token

        left = type_check(coax_literal(left))
        right = type_check(coax_literal(right))

        #print('EVAL_OPERATOR: '+str(left)+' | '+str(oper)+' | '+str(right))

        if left['type'] == 'int' and right['type'] == 'int':
            if oper['val'] == '*':
                return {
                    'type': 'int',
                    'val': left['val'] * right['val'],
                }
            elif oper['val'] == '/':
                return {
                    'type': 'int',
                    'val': left['val'] / right['val'],
                }
            else:
                raise NotImplemented

        raise NotImplemented


    def eval_expression(self, call, expr):
        #print("EVAL: " + str(expr))
        #if isinstance(expr, dict) and 'val' in expr and expr['val'] == '5':
        #    raise NotImplemented
        if isinstance(expr, list) and not isinstance(expr, str):
            tokens = [self.eval_expression(call, t) for t in expr]
            for opers in [['^'],['*','/'],['+','-']]:
                i = 0
                while i < len(tokens):
                    token = tokens[i]
                    if isinstance(token, dict) and 'cls' in token and \
                       token['cls'] == 'operator' and token['val'] in opers:
                        tokens[i-1] = self.eval_operator(call, tokens[i-1],
                                                         tokens[i], tokens[i+1])
                        del tokens[i]
                        del tokens[i]
                        continue

                    i += 1
            #print("TOKENS: " + str(tokens))
            return self.eval_expression(call, tokens[0])

        # TODO: fix hack
        if not isinstance(expr, dict):
            return expr

        if 'type' in expr:
            return expr

        if expr['cls'] in ['string', 'numeric', 'operator']:
            return expr
        elif expr['cls'] == 'binding':
            binding = ''.join([t['val'] for t in expr['tokens']])
            return self.get_local(call['id'], binding)
        elif expr['cls'] == 'parenthesis':
            return self.eval_expression(call, expr['tokens'])
        elif expr['cls'] == 'argument':
            return self.eval_expression(call, expr['expression']['tokens'])
        else:
            print('Unrecognized token class: ' + expr['cls'])
            raise NotImplemented


    def eval_expression_token(self, call, token):
        x = self.eval_expression(call, token)
        if isinstance(x, dict) and 'val' in x:
            return x['val']
        else:
            return x


    def binding(self, b):
        return ''.join([t['val'] for t in b['tokens']])


    def eval(self, call, inst):
        """
        Evaluate an instruction.

        :param inst: The instruction to evaluate in dict format.
        :return:
        """
        #print(inst)
        if inst['code']['kind'] == 'call':
            self.call(call['thread_id'], self.binding(inst['code']['binding']),
                      [self.eval_expression(call, p)
                       for p in inst['code']['params']])
        elif inst['code']['kind'] == 'assignment':
            bind = self.binding(inst['code']['binding'])

            is_call = 'target' in inst['code']

            val = '' if is_call else self.eval_expression_token(call,
                                           inst['code']['expression']['tokens'])

            if len(inst['code']['modifiers']) > 0:
                if len(inst['code']['modifiers']) > 1:
                    raise NotImplemented
                self.create_local(call['id'], bind,
                                  inst['code']['modifiers'][-1], val)
            else:
                if not is_call:
                    self.set_local(call['id'], bind, val)

            if is_call:
                self.call(call['thread_id'],
                          self.binding(inst['code']['target']),
                          inst['code']['params'])
        elif inst['code']['kind'] == 'return':
            # Look up the call stack frame we're returning to.
            parent = self.parent_call(call)

            # Get the call instruction that invoked the now-returning function.
            parent_inst = self.call_instruction(parent['id'])
            #print(parent_inst)
            # Map the return value to the variable in the call instruction.
            self.set_local(parent['id'],
                           self.binding(parent_inst['code']['binding']),
                           self.eval_expression_token(call,
                                        inst['code']['expression']['tokens']))

        else:
            raise NotImplemented

        return

        params = inst['parameters']

        #print(inst['instruction'] + " " + " ".join(params))

        if inst['kind'] == 'var':
            self.create_local(call['id'], params[1], params[0], params[2])
        elif inst['kind'] == 'set':
            self.set_local(call['id'], params[0], params[1])
        elif inst['kind'] == 'call':
            self.call(call['thread_id'], params[1], params[2:])
        elif inst['kind'] == 'sub':
            self.call(call['thread_id'], params[0], params[1:])
        elif inst['kind'] == 'print':
            print('[ glacia ] ' + self.eval_expression_token(call, params[0]))
        elif inst['kind'] == 'ret':
            self.eval_ret(call, inst, params[0])


    def eval_ret(self, call, inst, val):
        # Look up the call stack frame we're returning to.
        parent = self.parent_call(call)

        # Get the call instruction that invoked the now-returning function.
        parent_inst = self.call_instruction(parent['id'])
        params = self.parameters(parent_inst)

        # Map the return value to the variable in the call instruction.
        self.set_local(parent['id'], params[0],
                       self.eval_expression_token(call, val))

    def run(self):
        thread_id = self.db.autoid("insert into threads (id) values ({$id});")

        self.call(thread_id, 'main', [])

        try:
            while self.exec(thread_id):
                pass
        finally:
            self.db.commit()
