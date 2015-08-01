import json


loop_keywords = ['while', 'foreach', 'for']


def interpret(db, stdout_func=None):
    Interpreter(db, stdout_func=stdout_func).run()


class Interpreter(object):

    def __init__(self, db, stdout_func=None):
        self.db = db
        self.stdout_func = stdout_func


    def start(self):
        """
        Start a loaded program by creating a thread and calling the main()
        function.

        Returns:
            The newly-created thread ID.

        """

        thread_id = self.db.autoid("insert into threads (id) values ({$id});")

        self.call(thread_id, {'tokens': [{'val': 'main'}]}, [])

        self.db.commit()

        return thread_id


    def run(self, thread_id=None):
        """
        Run the loaded program to completion.

        """

        if thread_id is None:
            thread_id = self.get_main_thread_id()

        try:
            while self.run_one_line(thread_id=thread_id):
                pass
        finally:
            self.db.commit()


    def run_one_line(self, thread_id=None):
        """
        Run one line of the loaded program.

        Arguments:
            thread_id (str): The thread to run. If None, the main thread will
                             be used.

        Returns:
            True if there are more lines to be run, False if the program has
            finished.

        """

        if thread_id is None:
            thread_id = self.get_main_thread_id()

        ret = self.exec(thread_id)
        self.gc()
        self.db.commit()

        return ret


    def get_main_thread_id(self):
        """
        Get the main thread ID.

        """

        return self.db.scalar("select id from threads limit 1;")


    def call(self, thread_id, binding, arguments, caller_id=None):
        """
        Perform a function call in glacia.

        Arguments:
            thread_id (int) - The thread to make the call within.
            binding (str) - The binding of the function to call.
            arguments (list) - The positional arguments to pass.
            caller_id (int) - The instruction ID that made the call (or None in
                              the case of the initial main() call).

        Returns:
            For built-ins, returns the result of the call. For generator
            functions, returns a generator. Otherwise, returns None.

        """

        current_call = self.current_call(thread_id)

        def eval_arg(index):
            return self.eval_expression(current_call, arguments[index])

        func_name = binding['tokens'][-1]['val']

        evaled = [eval_arg(i) for i in range(len(arguments))]
        if len(binding['tokens']) == 3:
            if binding['tokens'][0]['cls'] == 'identifier' and \
               binding['tokens'][1]['cls'] == 'operator' and \
               binding['tokens'][1]['val'] == '.':
                evaled.insert(0, self.eval_expression(current_call, {
                    'cls': 'argument',
                    'expression': {
                        'tokens': [{
                            'cls': 'binding',
                            'tokens': [binding['tokens'][0]],
                        }],
                    },
                }))

        # Process built-ins
        if func_name == 'print':
            arg = eval_arg(0)

            if 'address_id' in arg:
                arg = self.mem_read(arg['address_id'])

            if isinstance(arg['val'], bool):
                out = 'true' if arg['val'] else 'false'
            else:
                out = str(arg['val'])

            if callable(self.stdout_func):
                self.stdout_func(out)
            else:
                print(out)

            return None

        elif func_name == 'len':
            return {
                'type': 'int',
                'val': self.get_list_length(current_call, evaled[0])
            }

        elif func_name == 'push':
            self.list_push(current_call, evaled[0], evaled[1])
            return

        elif func_name == 'pop':
            return self.list_pop(current_call, evaled[0])

        elif func_name == 'next':
            self.generator_next(current_call, evaled[0], caller_id)
            return

        elif func_name == 'finished':
            return self.generator_finished(current_call, evaled[0])

        # Look up the function in the database
        function = self.db.first("select * from functions where label = %s;",
                                 (func_name,))
        function['arguments'] = json.loads(function['arguments'])

        # Find the first instruction in the function
        inst_id = self.db.scalar("select id from instructions " +
                                 "where function_id = %s and " +
                                 "parent_id is null and previous_id is null;",
                                 (function['id'],))

        if function['return_type'] == 'generator':
            depth = None
        else:
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
            call = {'id': call_id}
            expr = self.eval_expression(call, arguments[i])

            # Some types automatically pass by reference. Detect that here.
            ref = None
            val = None
            try:
                mem = self.mem_read(expr['address_id'])
                if mem['type'] in ['list']:
                    ref = mem['id']
                else:
                    raise KeyError
            except KeyError:
                pass
            finally:
                val = self.eval_expression_token(call, expr)

            self.create_local(call_id, function['arguments'][i]['name'],
                              function['arguments'][i]['type'], val, ref=ref)

        if function['return_type'] == 'generator':
            return {
                'type': 'generator',
                'val': call_id,
            }


    def generator_next(self, call, generator, caller_id):
        """
        Restore a generator's call stack frame.

        """

        mem = self.mem_read(generator['address_id'])
        generator_call = self.get_call(mem['val'])

        depth = self.db.scalar("select max(depth) from calls " +
                               "where thread_id = %s;",
                               (generator_call['thread_id'],))

        self.db.cmd("update calls set depth = %s, calling_instruction_id = %s "+
                    "where id = %s;",
                    (depth + 1, caller_id, generator_call['id']))


    def generator_finished(self, call, generator):
        """
        Check if a generator is finished or not.

        """

        mem = self.mem_read(generator['address_id'])

        # If the generator points to a call stack frame which does not exist,
        # it is considered to be finished as there is nothing to restore.
        return {
            'type': 'bool',
            'val': (self.get_call(mem['val']) is None),
        }


    def set_call_instruction(self, call_id, instruction_id):
        self.db.cmd("update calls set instruction_id = %s where id = %s;",
                    (instruction_id, call_id,))


    def step_over(self, instruction_id):
        """
        Look up the next instruction without changing hierarchical depth.

        """
        ret = self.db.first("select * from instructions where previous_id=%s;",
                            (instruction_id,))

        if ret is not None:
            ret['code'] = json.loads(ret['code'])

        return ret


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
        ret = self.db.first("select * from instructions where previous_id = ("+
                            "select parent_id from instructions " +
                            "where id = %s);",
                            (instruction_id,))

        if ret is not None:
            ret['code'] = json.loads(ret['code'])

        return ret


    def step_out_greedy(self, call, inst):
        """
        Step out of the given instruction to the next executable line, taking
        conditionals and loops into account.

        """

        self.exit_conditional(call, inst)

        for parent in self.step_up(call, inst):
            # If the next level above this one is a loop, then loop.
            if parent['code']['kind'] in loop_keywords:
                return parent

            self.exit_conditional(parent, inst)

            # If the parent is not a loop, find the next line after it.
            next_inst = self.step_over(parent['id'])

            if next_inst is not None:
                return next_inst


    def step_over_or_out_greedy(self, call, inst):
        """
        Advance the instruction pointer to the next executable instruction.

        """

        next_inst = self.step_over(inst['id'])

        if next_inst is None:
            next_inst = self.step_out_greedy(call, inst)
        else:
            self.exit_conditional(call, inst)

        self.call_advance(call, next_inst)


    def get_instruction_by_label(self, function_id, label):
        """
        Look up an instruction in a function by label.

        Arguments:
            function_id (str): The ID of the function to search.
            label (str): The label name to find.

        Returns:
            The instruction in dict-format.

        """
        id = self.db.scalar("select id from instructions " +
                            "where function_id = %s and label = %s limit 1;",
                            (function_id, label,))

        return self.get_instruction(id)


    def conditional_depth(self, call):
        """
        Get current depth of the conditional stack.

        """
        ret = self.db.scalar("select max(depth) from conditionals where " +
                             "call_id = %s;",
                             (call['id'],))

        return -1 if ret is None else ret


    def push_conditional(self, call, satisfied):
        """
        Push a new frame onto the conditional stack (entering an if block).

        Arguments:
            call (dict): The call stack frame to execute within.
            satisfied (bool): Whether any conditional in this frame has been
                              true.

        """
        self.db.cmd("insert into conditionals (call_id, depth, satisfied) " +
                    "values (%s, %s, %s);",
                    (call['id'], self.conditional_depth(call) + 1, satisfied,))


    def pop_conditional(self, call):
        """
        Pop a frame off the conditional stack (exiting a complex conditional).

        """
        self.db.cmd("delete from conditionals where call_id=%s and depth=%s;",
                    (call['id'], self.conditional_depth(call),))


    def read_conditional(self, call):
        """
        Read the satisfied value from the frame on top of the conditional stack.

        """
        return self.db.scalar("select satisfied from conditionals where " +
                              "call_id = %s order by depth desc limit 1;",
                              (call['id'],))


    def set_conditional(self, call, satisfied):
        """
        Set the satisfied value on the frame on top of the conditional stack.

        """
        self.db.cmd("update conditionals set satisfied = %s where " +
                    "call_id = %s and depth = %s;",
                    (satisfied, call['id'], self.conditional_depth(call),))


    def current_call(self, thread_id):
        """
        Get the frame at the top of the call stack for the given thread.

        :param thread_id: The thread to look up
        :return: The call stack frame in dict form
        """
        return self.db.first("select * from calls where thread_id = %s " +
                             "and depth is not null " +
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


    def call_delete(self, call):
        """
        Delete a call stack frame.

        """
        # Make sure the conditional stack is clear before leaving the call.
        if self.db.scalar("select count(1) from conditionals where call_id=%s;",
                          (call['id'],)) > 0:
            raise Exception("Conditional stack not cleared.")

        self.db.cmd("delete from calls where id = %s;", (call['id'],))


    def call_advance(self, call, next_inst):
        """
        Advance a call frame's instruction pointer to the given instruction or
        delete the call frame if there is no next instruction.

        Arguments:
            call (dict): The call stack frame to modify or delete.
            next_inst (dict): The next instruction to point to or None.

        """

        # If end of function, delete the call frame.
        if next_inst is None:
            self.call_delete(call)

        # Otherwise, update the call frame's instruction pointer.
        else:
            self.set_call_instruction(call['id'], None if next_inst is None
                                                       else next_inst['id'])


    def get_instruction(self, instruction_id):
        """
        Get an instruction from the database by ID.

        """
        ret = self.db.first("select * from instructions where id = %s;",
                            (instruction_id,))

        ret['code'] = json.loads(ret['code'])

        return ret


    def mem_read(self, addr):
        """
        Read virtual database memory directly.

        Arguments:
            addr (str): The memory address to read.

        Returns:
            The address in memory in dict format.

        """

        ret = self.db.first("select * from addresses where id = %s;", (addr,))

        return self.type_check(ret)


    def mem_write(self, addr, val):
        """
        Write to virtual database memory directly.

        Arguments:
            addr (str): The memory address to write.
            val (dict): The value to write.

        """

        # If val is a local/item/etc, look up the underlying memory.
        try:
            if 'address_id' in val:
                val = self.mem_read(val['address_id'])
        except KeyError:
            pass

        self.db.cmd("update addresses set val = %s, type = %s where id = %s;",
                    (val['val'], val['type'], addr,))

        return addr


    def mem_alloc(self):
        """
        Allocate a new address in virtual database memory.

        Returns:
            The new memory address in dict format.

        """
        return self.db.autoid("insert into addresses (id) values ({$id});")


    def mem_free(self, addr):
        """
        Free an address of virtual database memory.

        Arguments:
            addr (str): The address to free.

        """
        self.db.cmd("delete from addresses where id = %s;", (addr,))


    def create_local(self, call_id, label, type_, val, ref=None):
        """
        Create and set a local variable.

        Arguments:
            call_id (str): The call stack frame to create the variable inside.
            label (str): The name of the variable.
            type_ (str): The type of the variable.
            val (any): The initial value to assign to the variable.
            ref (str): If present, refers to an existing memory address ID to
                       make the local refer to instead of allocating new
                       memory. val is ignored if ref is present.

        """

        # No existing reference to point to.
        if ref is None:
            addr = self.mem_write(self.mem_alloc(), {'type': type_,'val': val})

        # Existing reference. Make a pointer.
        else:
            addr = ref

        # Check for an existing local to update.
        existing = self.get_local(call_id, label)
        if existing is not None:
            self.db.cmd("update locals set address_id = %s where id = %s;",
                        (addr, existing['id'],))
            return

        self.db.autoid("insert into locals (id, call_id, label, address_id) " +
                       "values ({$id}, %s, %s, %s);",
                       (call_id, label, addr))


    def get_local(self, call_id, label):
        """
        Get a local by label name within the scope of a call stack frame.

        Arguments:
            call_id (str): The call stack frame to search in.
            label (str): The name of the local to search for.

        Returns:
            The local in dict format.

        """

        # Unpack the label if it's not a primitive.
        try:
            if 'label' in label:
                label = label['label']
            elif 'val' in label:
                label = label['val']
        except TypeError:
            pass

        ret = self.db.first("select * from locals where call_id = %s and " +
                            "label = %s;",
                            (call_id, label,))

        if ret is not None:
            ret['cls'] = 'local'

        return ret


    def set_local(self, call_id, label, val):
        """
        Change the value of an existing local.

        Arguments:
            call_id (str): The call stack frame to search in.
            label (str): The name of the local to search for.
            val (any): The new value to assign to the local.

        """
        local = self.get_local(call_id, label)
        mem = self.mem_read(local['address_id'])
        self.mem_write(local['address_id'], {'val': val, 'type': mem['type']})


    def step_up(self, call, inst):
        current = inst

        # Perform any needed cleanup on the conditional stack.
        self.exit_conditional(call, current)

        while current['parent_id'] is not None:
            # Look up the parent instruction if there is one.
            parent_inst = self.get_instruction(current['parent_id'])

            if parent_inst is None:
                raise StopIteration

            # Perform any needed cleanup on the conditional stack.
            self.exit_conditional(call, parent_inst)

            yield parent_inst

            current = parent_inst


    def step_up_loops(self, call, inst):
        """
        Step up from the given instruction, yielding any loops encountered.

        """

        for parent in self.step_up(call, inst):
            if parent['code']['kind'] in loop_keywords:
                yield parent


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

        # If the instruction stepped into a block, don't advance the
        # instruction pointer.
        if not self.eval(call, inst):
            return True

        # Advance instruction pointer to the next line.
        self.step_over_or_out_greedy(call, inst)

        # Execution can continue
        return True


    def exit_conditional(self, call, parent_inst):
        """
        Check if execution is leaving a conditional and pop off the conditional
        stack if so.

        Arguments:
            call (dict): The call stack frame to execute within.
            parent_inst (dict): The instruction whose block we are exiting from.

        """

        # Look up the next instruction
        next_inst = None
        if parent_inst is not None:
            next_inst = self.step_over(parent_inst['id'])

        if (parent_inst is not None and
            parent_inst['code']['kind'] in ['if', 'else']) and \
           (next_inst is None or
            next_inst['code']['kind'] != 'else'):
            self.pop_conditional(call)


    def eval_break(self, call, break_inst):
        """
        Break and/or continue out of one or more loops.

        Arguments:
            call (dict): The call stack frame to execute within.
            break_inst (dict): The break/continue instruction being evaluated.

        """

        is_break = (break_inst['code']['kind'] == 'break')

        target_label = None
        break_count = 1

        # If it has an expression, it's either a number of loops to break out
        # of or a label name.
        if 'expression' in break_inst['code']:
            tokens = break_inst['code']['expression']['tokens']

            # Try to get a label name.
            try:
                identifier = tokens[0]['tokens'][0]
                if identifier['cls'] == 'identifier':
                    target_label = identifier['val']
            except KeyError:
                pass
            except IndexError:
                pass

            # If it wasn't a label name, it should be a number of loops.
            if target_label is None:
                break_count = int(self.eval_expression_token(call, tokens))

        found = None

        for loop in self.step_up_loops(call, break_inst):
            # If no target_label, break out of the specified number of loops.
            if target_label is None:
                break_count -= 1
                if break_count == 0:
                    found = loop
                    break
            # Otherwise, break out of loops up to and including the given label.
            else:
                if loop['label'] == target_label:
                    found = loop
                    break

        if found is not None:
            # Break the target loop and continue execution after.
            if is_break:
                self.step_over_or_out_greedy(call, found)
            # Continue execution at the start of the target loop.
            else:
                self.call_advance(call, found)


    def type_check(self, token):
        """
        Ensure values are the right types.

        """

        if token['type'] == 'int':
            token['val'] = int(token['val'])

        elif token['type'] == 'bool':
            token['val'] = bool(int(token['val']))

        return token


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
                ret = self.mem_read(lit['address_id'])
                if lit['cls'] in ['local', 'item']:
                    pass
                elif lit['cls'] == 'numeric':
                    ret['type'] = 'int'
                elif lit['cls'] == 'boolean':
                    ret['type'] = 'bool'
                elif lit['cls'] == 'string':
                    ret['type'] = 'string'
                else:
                    print("Unknown literal: " + str(lit))
                    raise NotImplemented
                return ret
            else:
                return lit

        # Get the operands ready to evaluate.
        left = self.type_check(coax_literal(left))
        right = self.type_check(coax_literal(right))

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
            elif oper['val'] == '%':
                ret['val'] = left['val'] % right['val']
            elif oper['val'] == '^':
                ret['val'] = left['val'] ** right['val']
            elif oper['val'] == '==':
                ret['val'] = left['val'] == right['val']
            elif oper['val'] == '!=':
                ret['val'] = left['val'] != right['val']
            elif oper['val'] == '<':
                ret['val'] = left['val'] < right['val']
            elif oper['val'] == '<=':
                ret['val'] = left['val'] <= right['val']
            elif oper['val'] == '>':
                ret['val'] = left['val'] > right['val']
            elif oper['val'] == '>=':
                ret['val'] = left['val'] >= right['val']
            elif oper['val'] == '&&':
                ret['val'] = left['val'] and right['val']
            elif oper['val'] == '||':
                ret['val'] = left['val'] or right['val']
            else:
                raise NotImplemented

            return ret

        # No evaluation logic found.
        print("TYPES: " + str(left['type']) + ", " + str(right['type']))
        raise NotImplemented


    def get_item(self, call, target, index):
        """
        Get the value of a list item.

        Arguments:
            call (dict): The call stack frame to search within.
            target (dict): The identifier of the list local.
            index (dict): The list item ordinal.

        """

        # Look up te list whose item is being retrieved.
        local = self.get_local(call['id'], target)
        mem = self.mem_read(local['address_id'])

        # Get the raw index value if this is a token.
        try:
            index = index['val']
        except KeyError:
            pass
        except TypeError:
            pass

        ret = self.db.first("select * from items where list_id = %s and " +
                            "ordinal = %s limit 1;",
                            (mem['id'], index,))

        if ret is None:
            raise Exception('Failed to get index '+str(index)+' '+
                            'from list '+str(target)+'.')

        ret['cls'] = 'item'

        return ret


    def set_item(self, call, target, index, val):
        """
        Set the value of a list item.

        Arguments:
            call (dict): The call stack frame to search within.
            target (dict): The identifier of the list local.
            index (int): The list item ordinal.
            val (dict): The value to assign to the item.

        """

        # Look up the list whose item is being assigned.
        local = self.get_local(call['id'], target)
        mem = self.mem_read(local['address_id'])

        # Get the raw index value if this is a token.
        try:
            index = index['val']
        except TypeError:
            pass

        # An "upsert" would still take 2 queries: a select to see if it exists
        # already and then an insert or update depending on the select. Might as
        # well just delete and insert.
        self.db.cmd("delete from items where list_id = %s and ordinal = %s;",
                    (mem['id'], index))

        addr = self.mem_write(self.mem_alloc(), val)

        self.db.cmd("insert into items (list_id, ordinal, address_id) " +
                    "values (%s, %s, %s);",
                    (mem['id'], index, addr,))


    def get_list(self, call, target):
        """
        Get a list local from the database.

        Arguments:
            call (dict): The call stack frame to search in.
            target (dict): The identifier of the list to search for.

        """

        # Lookup the list.
        local = self.get_local(call['id'], target['label'])
        mem = self.mem_read(local['address_id'])

        # Make sure the local found is a list.
        if mem['type'] != 'list':
            raise Exception('Expected a list but found a '+mem['type']+'.')

        if mem['val'] is None:
            mem['val'] = 0

        return local


    def get_list_length(self, call, target):
        """
        Get the number of items in a list.

        Arguments:
            call (dict): The call stack frame to search in.
            target (dict): The identifier of the list to count items in.

        """
        local = self.get_list(call, target)
        mem = self.mem_read(local['address_id'])

        return 0 if mem['val'] is None else mem['val']


    def list_resize(self, lst, new_size):
        """
        Resize a list.

        Arguments:
            lst (dict): The list local to resize.
            new_size (int): The new list size in elements.

        """
        mem = self.mem_read(lst['address_id'])

        size_diff = new_size - int(mem['val'])

        # If there is no size difference, do nothing.
        if size_diff == 0:
            return

        # Update the bounds of the local in the database.
        self.mem_write(mem['id'], {'type': 'list','val': new_size})

        # If the list is being shrunk, delete any newly out-of-bounds items.
        if size_diff < 0:
            self.db.cmd("delete from items where list_id=%s and ordinal>=%s;",
                        (lst['id'], new_size))


    def list_push(self, call, target, val):
        """
        Append an item to the end of a list.

        Arguments:
            call (dict): The call stack frame to search in.
            target (dict): The identifier of the list to append to.
            val (dict): The value to append to the list.

        """
        local = self.get_list(call, target)
        mem = self.mem_read(local['address_id'])

        ordinal = int(mem['val'])

        self.list_resize(local, ordinal + 1)

        self.set_item(call, target, ordinal, val)


    def list_pop(self, call, target):
        """
        Pop an item off the top of the list.

        Arguments:
            call (dict): The call stack frame to search in.
            target (dict): The identifier of the list to remove from.

        """
        local = self.get_list(call, target)
        mem = self.mem_read(local['address_id'])

        if int(mem['val']) < 1:
            raise Exception('The list is already empty.')

        # Get the index of the last item in the list.
        ordinal = int(mem['val']) - 1

        ret = self.get_item(call, target, ordinal)

        # Delete the last item from the list.
        self.list_resize(local, ordinal)

        return ret


    def eval_expression(self, call, expr, assignment_target=False):
        """
        Evaluate an expression.

        Arguments:
            call (dict): The call stack frame to evaluate within.
            expr (dict,list): The token or list of tokens to evaluate.
            assignment_target (bool): Whether the expression is the target of an
                                      assignment instruction.

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
            for opers in [['^'],['*','/','%'],['+','-'],
                          ['==','!=','<','<=','>','>='],['&&'],['||']]:
                i = 0
                while i < len(tokens):
                    token = tokens[i]

                    # Look for operators.
                    if isinstance(token, dict) and 'cls' in token and \
                       token['cls'] == 'operator':

                        # Special handling for not operator (!).
                        if token['val'] == '!':
                            # Delete the not operator and reverse the operand.
                            del tokens[i]
                            tokens[i]['val'] = not tokens[i]['val']

                        # Standard operator evaluation.
                        elif token['val'] in opers:
                            # Evaluate the operator and replace this token, the
                            # previous one, and the next one (all part of the
                            # evaluation) with the result of the evaluation.
                            tokens[i-1] = self.eval_operator(call, tokens[i-1],
                                                             tokens[i],
                                                             tokens[i+1])
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
            # Copy the token array
            parts = expr['tokens'][:]
            last = None

            while len(parts) > 0:
                if parts[0]['cls'] == 'identifier':
                    if last is not None:
                        raise Exception('Two identifiers in a row is invalid.')

                    last = parts[0]

                if parts[0]['cls'] == 'square':
                    if last is None:
                        raise Exception('Indexer not preceded by an identifer.')

                    # Recur
                    index = self.eval_expression(call, parts[0]['tokens'])

                    # Evaluate the indexer operation (as long as this is a get).
                    if not assignment_target:
                        index = self.eval_expression_token(call, index)
                        last = self.get_item(call, last, index)

                    # If this is a set, pack this up as an unevaluated indexer.
                    else:
                        return {
                            'cls': 'unevaluated_indexer',
                            'identifier': last,
                            'index': index,
                        }

                del parts[0]

            binding = ''.join([t['val'] for t in expr['tokens']])

            if 'cls' in last and last['cls'] == 'identifier':
                return self.get_local(call['id'], last['val'])

            return last

        # If the expression is parenthesis, recur.
        if expr['cls'] == 'parenthesis':
            return self.eval_expression(call, expr['tokens'])

        # If the expression is an argument, recur.
        if expr['cls'] == 'argument':
            return self.eval_expression(call, expr['expression']['tokens'])

        # If the expression is a local, return it.
        if expr['cls'] in ['local', 'item']:
            return expr

        # If the expression is a boolean literal, return it.
        if expr['cls'] == 'keyword' and expr['val'] in ['true', 'false']:
            return {
                'type': 'bool',
                'val': expr['val'] == 'true',
            }

        # No evaluation possible.
        print('Unrecognized token class: ' + expr['cls'])
        raise NotImplemented


    def eval_expression_token(self, call, token):
        """
        Evaluates an expression and returns the literal value if possible.

        """

        # Perform standard expression evaluation.
        ret = self.eval_expression(call, token)

        try:
            if 'address_id' in ret:
                ret = self.mem_read(ret['address_id'])
        finally:
            pass

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
        binding = self.eval_expression(call, inst['code']['binding'],
                                       assignment_target=True)

        # If there are modifiers (like int, string, static), create a local.
        if len(inst['code']['modifiers']) > 0:
            if len(inst['code']['modifiers']) > 1:
                raise NotImplemented

            type_ = inst['code']['modifiers'][0]

            if type_ == 'var':
                if 'address_id' in val:
                    type_ = self.mem_read(val['address_id'])['type']
                else:
                    type_ = val['type']

            self.create_local(call['id'], bind, type_, val_stripped)

        # If there are no modifiers, change the value of an existing local.
        else:
            # If this is setting a list item, use special array handling.
            if 'cls' in binding and binding['cls'] == 'unevaluated_indexer':
                self.set_item(call,binding['identifier'],binding['index'],val)

            # Otherwise treat it as a standard local.
            else:
                self.set_local(call['id'], bind, val_stripped)


    def is_true(self, token):
        """
        Check whether a value is considered boolean true in glacia.

        Arguments:
            token (dict): A value in dict format.

        """

        if token['type'] == 'bool' and token['val'] == True:
            return True

        if token['type'] == 'int' and int(token['val']) == 1:
            return True

        return False


    def eval(self, call, inst):
        """
        Evaluate an instruction.

        Arguments:
            call (dict): The call stack frame to execute within.
            inst (dict): The instruction to evaluate.

        """

        def make_call(funcbind):
            return self.call(call['thread_id'], funcbind,
                             [self.eval_expression(call, p)
                              for p in inst['code']['params']],
                             caller_id=inst['id'])

        def process_conditional_block():
            # If this is the start of a conditional, push a new frame onto the
            # conditional stack.
            if inst['code']['kind'] == 'if':
                self.push_conditional(call, False)

            # Evaluate the conditional expression.
            if 'expression' in inst['code']:
                r = self.eval_expression(call,
                                         inst['code']['expression']['tokens'])

                # If this is a pointer, resolve it.
                if 'address_id' in r:
                    r = self.mem_read(r['address_id'])

            # Default to true if no conditional is present.
            else:
                r = {'val': True,'type': 'bool'}

            # If the conditional does not pass, skip the block.
            if not self.is_true(r):
                return True

            # Mark the conditional as satisfied.
            self.set_conditional(call, True)

            # Step into the if/else block.
            self.set_call_instruction(call['id'],
                                      self.step_into(inst['id'])['id'])

            # Make sure exec() doesn't advanced the instruction pointer,
            # which would overwrite the step into above.
            return False

        # Evaluate call instruction
        if inst['code']['kind'] == 'call':
            make_call(inst['code']['binding'])

        # Evaluate assignment instruction
        elif inst['code']['kind'] == 'assignment':
            # Make a call if this assignment has a call target.
            if 'target' in inst['code']:
                assign = make_call(inst['code']['target'])

            # Otherwise evaluate the expression directly.
            else:
                assign = self.eval_expression(call,
                                           inst['code']['expression']['tokens'])

            if assign is not None:
                self.eval_assignment(call, inst, assign)

        # Evaluate return instruction
        elif inst['code']['kind'] in ['return', 'yield', 'yield break']:
            # Look up the call stack frame we're returning to.
            parent = self.parent_call(call)

            # Get the instruction we'll be returning to.
            parent_inst = self.call_instruction(parent['id'])

            # Map the return value to the variable in the call instruction.
            try:
                v = self.eval_expression(call,
                                         inst['code']['expression']['tokens'])
            except KeyError:
                # In the case of yield break, return null.
                v = {
                    'type': 'special',
                    'val': 'null'
                }

            # Get the call instruction that invoked the now-returning function.
            caller_inst = self.get_instruction(call['calling_instruction_id'])

            self.eval_assignment(parent, caller_inst, v)

            # For returns, delete the call stack frame.
            if inst['code']['kind'] == 'return':
                self.db.cmd("delete from calls where id = %s", (call['id'],))
            # For yields, stash the call stack frame.
            elif inst['code']['kind'] == 'yield':
                self.db.cmd("update calls set depth = null where id = %s",
                            (call['id'],))

        # Execute if statement
        elif inst['code']['kind'] == 'if':
            return process_conditional_block()

        # Execute else statement
        elif inst['code']['kind'] == 'else':
            if not self.read_conditional(call):
                return process_conditional_block()

        # Execute loops
        elif inst['code']['kind'] in loop_keywords:
            return process_conditional_block()

        # Execute break statement
        elif inst['code']['kind'] in ['break', 'continue']:
            self.eval_break(call, inst)
            # Do not advance the instruction pointer, it has been moved by
            # break.
            return False

        # Unrecognized instruction
        else:
            raise NotImplemented

        # Signal to exec() to advance the instruction pointer.
        return True


    def gc(self):
        """
        Run the garbage collector against all virtual database memory.

        """

        # Delete any memory addresses which are no longer referenced.
        self.db.cmd("delete from addresses where 0 = " +
                    "(select count(1) from locals " +
                     "where address_id = addresses.id) + " +
                    "(select count(1) from items " +
                     "where address_id = addresses.id);")
