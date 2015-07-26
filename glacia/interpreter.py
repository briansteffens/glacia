import json


def interpret(db):
    Interpreter(db).run()


class Interpreter(object):

    def __init__(self, db):
        self.db = db


    def run(self):
        thread_id = self.db.autoid("insert into threads (id) values ({$id});")

        self.call(thread_id, 'main', [])

        try:
            while self.exec(thread_id):
                pass
        finally:
            self.db.commit()


    def call(self, thread_id, func_name, arguments, caller_id=None):
        """
        Perform a function call in glacia.

        Arguments:
            thread_id (int) - The thread to make the call within.
            func_name (str) - The name of the function to call.
            arguments (list) - The positional arguments to pass.
            caller_id (int) - The instruction ID that made the call (or None in
                              the case of the initial main() call).

        Returns:
            The call_id referencing the newly created frame on the call stack
            or None if no frame was created (in the case of built-ins).

        """

        # Process built-ins
        if func_name == 'print':
            print(self.eval_expression_token(self.current_call(thread_id),
                                             arguments[0]))
            return None

        # Look up the function in the database
        function = self.db.first("select * from functions where label = %s;",
                                 (func_name,))
        function['arguments'] = json.loads(function['arguments'])

        # Find the first instruction in the function
        inst_id = self.db.scalar("select id from instructions " +
                                 "where function_id = %s and " +
                                 "parent_id is null and previous_id is null;",
                                 (function['id'],))

        # Get the size of the call stack
        depth = self.db.scalar("select max(depth) + 1 from calls " +
                               "where thread_id = %s",
                               (thread_id,))

        if depth is None:
            depth = 0

        # Push this call onto the call stack
        call_id = self.db.autoid("insert into calls (id, thread_id, depth, " +
                                 "instruction_id, calling_instruction_id) " +
                                 "values ({$id}, %s, %s, %s, %s);",
                                 (thread_id, depth, inst_id, caller_id))

        # Validate argument count
        if len(arguments) != len(function['arguments']):
            raise Exception('Invalid number of arguments.')

        # Create all arguments as locals in the new call scope
        for i in range(len(arguments)):
            self.create_local(call_id, function['arguments'][i]['name'],
                              function['arguments'][i]['type'],
                              self.eval_expression_token({'id': call_id},
                                                   arguments[i]))

        return call_id


    def set_call_instruction(self, call_id, instruction_id):
        self.db.cmd("update calls set instruction_id = %s where id = %s;",
                    (instruction_id, call_id,))


    def step_over(self, instruction_id):
        """
        Look up the next instruction without changing hierarchical depth.

        """
        return self.db.first("select * from instructions where previous_id=%s;",
                             (instruction_id,))


    def step_into(self, instruction_id):
        """
        Look up the first instruction inside an instruction block.

        """
        return self.db.first("select * from instructions where parent_id = %s "+
                             "and previous_id is null;",
                             (instruction_id,))


    def step_out(self, instruction_id):
        """
        Look up the next instruction outside the current block.

        """
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
        return self.get_instruction(self.get_call(call_id)['instruction_id'])


    def get_call(self, call_id):
        """
        Get a call from the database by ID.

        """
        return self.db.first("select * from calls where id = %s;", (call_id,))


    def get_instruction(self, instruction_id):
        """
        Get an instruction from the database by ID.

        """
        ret = self.db.first("select * from instructions where id = %s;",
                            (instruction_id,))

        ret['code'] = json.loads(ret['code'])

        return ret


    def create_local(self, call_id, label, type_, val):
        """
        Create and set a local variable.

        Arguments:
            call_id (str): The call stack frame to create the variable inside.
            label (str): The name of the variable.
            type_ (str): The type of the variable.
            val (any): The initial value to assign to the variable.

        """
        self.db.autoid("insert into locals (id, call_id, label, type, val) " +
                       "values ({$id}, %s, %s, %s, %s);",
                       (call_id, label, type_, val,))


    def get_local(self, call_id, label):
        """
        Get a local by label name within the scope of a call stack frame.

        Arguments:
            call_id (str): The call stack frame to search in.
            label (str): The name of the local to search for.

        Returns:
            The local in dict format.

        """
        return self.db.first("select * from locals where call_id = %s and " +
                             "label = %s;",
                             (call_id, label,))


    def set_local(self, call_id, label, val):
        """
        Change the value of an existing local.

        Arguments:
            call_id (str): The call stack frame to search in.
            label (str): The name of the local to search for.
            val (any): The new value to assign to the local.

        """
        self.db.cmd("update locals set val = %s where call_id = %s and " +
                    "label = %s;",
                    (val, call_id, label,))


    def exec(self, thread_id):
        """
        Execute an instruction in the given thread.

        Arguments:
            thread_id (str): The thread to execute.

        Returns:
            True if the thread is still running, False if it has stopped.

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
        """
        Evaluate a simple expression such as (x * y) or ("hello " + "world").

        Arguments:
            call (dict): The call stack frame to execute within.
            left (dict): The left-side operand.
            oper (dict): The operator to use.
            right (dict): The right-side operand.

        Returns:
            A token in dict-format with the result of the expression.

        """

        def coax_literal(lit):
            """
            Fill out type information in a literal.

            """
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
            """
            Ensure values are the right types.

            """
            if token['type'] == 'int':
                token['val'] = int(token['val'])

            return token

        # Get the operands ready to evaluate.
        left = type_check(coax_literal(left))
        right = type_check(coax_literal(right))

        ret = {}

        # Evaluation logic for when both operands are ints.
        if left['type'] == 'int' and right['type'] == 'int':
            ret['type'] = 'int'

            if oper['val'] == '+':
                ret['val'] = left['val'] + right['val']
            elif oper['val'] == '-':
                ret['val'] = left['val'] - right['val']
            elif oper['val'] == '*':
                ret['val'] = left['val'] * right['val']
            elif oper['val'] == '/':
                ret['val'] = left['val'] / right['val']
            elif oper['val'] == '^':
                ret['val'] = left['val'] ** right['val']
            else:
                raise NotImplemented

            return ret

        # No evaluation logic found.
        print("TYPES: " + str(left['type']) + ", " + str(right['type']))
        raise NotImplemented


    def eval_expression(self, call, expr):
        """
        Evaluate an expression.

        Arguments:
            call (dict): The call stack frame to evaluate within.
            expr (dict,list): The token or list of tokens to evaluate.

        Returns:
            A dict-format token which is the result of the expression being
            evaluated.

        """

        # If the expression is a list of tokens, perform operator evaluation.
        if isinstance(expr, list) and not isinstance(expr, str):
            # Recur, evaluating all elements (this needs to be depth-first).
            tokens = [self.eval_expression(call, t) for t in expr]

            # Perform multiple passes over the evaluated tokens in order to
            # evaluate operators in the correct order (the order of operations).
            for opers in [['^'],['*','/'],['+','-']]:
                i = 0
                while i < len(tokens):
                    token = tokens[i]

                    # If the token is an operator, perform operator evaluation.
                    if isinstance(token, dict) and 'cls' in token and \
                       token['cls'] == 'operator' and token['val'] in opers:
                        # Evaluate the operator and replace this token, the
                        # previous one, and the next one (all part of the
                        # evaluation) with the result of the evaluation.
                        tokens[i-1] = self.eval_operator(call, tokens[i-1],
                                                         tokens[i], tokens[i+1])
                        del tokens[i]
                        del tokens[i]
                        continue

                    i += 1

            # There should only be one token left after all operator passes.
            if len(tokens) > 1:
                raise Exception("Expression could not be completely evaluated.")

            # Return the final evaluated result.
            return self.eval_expression(call, tokens[0])

        # If the expression is already a value, return it.
        if 'type' in expr:
            return expr

        # If the expression is an operator, just return it.
        if expr['cls'] == 'operator':
            return expr

        # If the expression is a numeric literal, turn it into a typed value.
        if expr['cls'] == 'numeric':
            return {
                'type': 'int',
                'val': expr['val'],
            }

        # If the expression is a string literal, turn it into a typed value.
        if expr['cls'] == 'string':
            return {
                'type': 'string',
                'val': expr['val'],
            }

        # If the expression is a binding, evaluate it and return its value.
        if expr['cls'] == 'binding':
            binding = ''.join([t['val'] for t in expr['tokens']])
            return self.get_local(call['id'], binding)

        # If the expression is parenthesis, recur.
        if expr['cls'] == 'parenthesis':
            return self.eval_expression(call, expr['tokens'])

        # If the expression is an argument, recur.
        if expr['cls'] == 'argument':
            return self.eval_expression(call, expr['expression']['tokens'])

        # No evaluation possible.
        print('Unrecognized token class: ' + expr['cls'])
        raise NotImplemented


    def eval_expression_token(self, call, token):
        """
        Evaluates an expression and returns the literal value if possible.

        """

        # Perform standard expression evaluation.
        ret = self.eval_expression(call, token)

        # Unpack the literal value of the result if present.
        if isinstance(ret, dict) and 'val' in ret:
            return ret['val']
        else:
            return ret


    def binding(self, b):
        """
        Converts a binding in token form to a string representation.

        """
        return ''.join([t['val'] for t in b['tokens']])


    def eval_assignment(self, call, inst, val):
        """
        Evaluate assignment as part of a call or assignment instruction,
        creating a local or setting an existing local as needed.

        Arguments:
            call (dict): The call stack frame to execute within.
            inst (dict): The instruction being executed.
            val (dict): The value to assign.

        """

        val_stripped = self.eval_expression_token(call, val)
        bind = self.binding(inst['code']['binding'])

        # If there are modifiers (like int, string, static), create a local.
        if len(inst['code']['modifiers']) > 0:
            if len(inst['code']['modifiers']) > 1:
                raise NotImplemented

            self.create_local(call['id'], bind, val['type'], val_stripped)

        # If there are no modifiers, change the value of an existing local.
        else:
            self.set_local(call['id'], bind, val_stripped)


    def eval(self, call, inst):
        """
        Evaluate an instruction.

        Arguments:
            call (dict): The call stack frame to execute within.
            inst (dict): The instruction to evaluate.

        """

        def make_call(funcbind):
            self.call(call['thread_id'], self.binding(funcbind),
                      [self.eval_expression(call, p)
                       for p in inst['code']['params']],
                      caller_id=inst['id'])

        # Evaluate call instruction
        if inst['code']['kind'] == 'call':
            make_call(inst['code']['binding'])

        # Evaluate assignment instruction
        elif inst['code']['kind'] == 'assignment':
            # Make a call if this assignment has a call target.
            if 'target' in inst['code']:
                make_call(inst['code']['target'])

            # Otherwise evaluate the expression directly.
            else:
                self.eval_assignment(call, inst, self.eval_expression(call,
                                     inst['code']['expression']['tokens']))

        # Evaluate return instruction
        elif inst['code']['kind'] == 'return':
            # Look up the call stack frame we're returning to.
            parent = self.parent_call(call)

            # Get the instruction we'll be returning to.
            parent_inst = self.call_instruction(parent['id'])

            # Map the return value to the variable in the call instruction.
            retval = self.eval_expression(call,
                                          inst['code']['expression']['tokens'])

            # Get the call instruction that invoked the now-returning function.
            caller_inst = self.get_instruction(call['calling_instruction_id'])

            self.eval_assignment(parent, caller_inst, retval)

        # Unrecognized instruction
        else:
            raise NotImplemented
