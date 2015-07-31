#!/usr/bin/env python3
#
# Command-line interface for the glacia interpreter.
#

import sys
import argparse

from glacia.run import run

p = argparse.ArgumentParser()
p.add_argument("-v", "--verbose", action='store_true')
p.add_argument("-r", "--runlines", type=int, default=-1)
p.add_argument("-f", "--file")
args = p.parse_args(sys.argv[1:])

run(**{
    'verbose': args.verbose,
    'exec_lines': args.runlines,
    'fn': args.file,
})
