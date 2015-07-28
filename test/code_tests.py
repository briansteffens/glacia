"""
This is a high level testing interface for glacia. Each test is a file located
in /test/code_tests with the .glaciatest extension. The format expected of these
files is as follows:

    Expected output
    ---
    int main()
    {
        print('Expected output');
    }

The content below the separator (---) is executed by the glacia interpreter and
the output is compared against the content above the separator. If the expected
output matches the actual output, the test is considered to have passed.

"""

import glob

from glacia import color
from glacia.run import run

print('')

successful = 0
total = 0

for fn in glob.glob('test/code_tests/*.glaciatest'):
    total += 1

    with open(fn, 'rb') as f:
        parts = f.read().decode('utf-8').split('---')

        expected = parts[0].strip()

        try:
            # Run the test program and collect the standard output.
            actual = run(parts[1].strip(), collect_stdout=True)
        except:
            print(color.print('Error running '+fn+':', 'red'))
            raise

        # If the expected output matches the actual output, the test passed.
        if expected == '\n'.join(actual):
            print(color.print('Test passed', 'green') + ': ' + fn)
            successful += 1
            continue

        # Helper function to add tabs to multi-line strings.
        def output(s):
            if isinstance(s, str):
                return output(s.split('\n'))
            else:
                return '\n'.join(['\t\t' + l for l in s])

        # Print test failure notification.
        print(color.print('Test failed','red')+': '+fn+'\n\tExpected:\n'+
              output(expected)+'\n\tActual:\n'+output(actual))

final = '\n' + str(successful) + '/' + str(total) + ' tests successful.'
print(color.print(final, 'green' if successful == total else 'red'))
