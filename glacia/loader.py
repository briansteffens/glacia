import json


def load(db, generated):
    """
    Load DBIL code in dict format into the database for interpretation.

    :param db: A Database instance
    :param generated: DBIL code (from glacia.generator.generate())
    :return: None
    """

    # Clear existing program
    db.cmd('set foreign_key_checks = 0;')
    for table in ['locals','calls','threads','instructions','functions']:
        db.cmd('delete from ' + table + ';')
    db.cmd('set foreign_key_checks = 1;')

    # Load new program
    for function in generated:
        func_id = db.autoid("insert into functions "+
                            "(id, label, return_type, arguments) " +
                            "values ({$id}, %s, %s, %s);",
                            (function['name'], function['return_type'],
                             json.dumps(function['params']),))

        load_block(db, func_id, None, function['body'])

    db.commit()


def load_block(db, func_id, parent_id, instructions):
    """
    Recursively load a block of instructions into the database.

    :param db: A Database instance
    :param func_id: The ID of the function to which the block belongs
    :param parent_id: The parent block if nested
    :param instructions: A list of instructions in dict format
    :return: None
    """

    previous_id = None

    for instruction in instructions:
        previous_id = db.autoid(
            "insert into instructions " +
            "(id, function_id, parent_id, previous_id, code) " +
            "values ({$id}, %s, %s, %s, %s);",
            (func_id, parent_id, previous_id, json.dumps(instruction),))

        # Recursion
        if 'body' in instruction:
            load_block(db, func_id, previous_id, instruction['body'])