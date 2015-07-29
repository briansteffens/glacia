
def preprocess(code):
    """
    Preprocess glacia source code. Currently this just removes comments.

    Arguments:
        code (string): The raw source code to process

    Returns:
        The preprocessed code as a string.

    """

    ret = ''

    in_singleline_comment = False
    in_multiline_comment = False

    i = 0
    while i + 1 < len(code):
        next_two = code[i:i + 2]

        # Start a multi-line comment.
        if next_two == '/*':
            in_multiline_comment = True

        if not in_multiline_comment:
            # Start a single-line comment.
            if next_two == '//':
                in_singleline_comment = True

            # End a single-line comment.
            if in_singleline_comment and code[i] in ['\n','\r']:
                in_singleline_comment = False

            # Not in any kind of comment, allow the character to pass through.
            if not in_singleline_comment:
                ret += code[i]

        # End a multi-line comment.
        if next_two == '*/':
            in_multiline_comment = False

            # Skip the "*/" just detected.
            i += 1

        i += 1

    return ret
