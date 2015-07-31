#!/bin/bash
#
# Creates a development/testing tmux session.
#

cd /vagrant

tmux new-session -d -s glacia -n console
tmux send-keys -t glacia "vagrant ssh -c \"bash -c 'cd /vagrant; exec bash'\"" ^m "glacia -f examples/primes.glacia"
sleep 1

tmux new-window -n "db"
tmux send-keys -t glacia "vagrant ssh -c \"exec bash\"" ^m "mysql -u root -D glacia" ^m
sleep 1

tmux new-window -n "tests"
tmux send-keys -t glacia "vagrant ssh -c \"bash -c 'cd /vagrant; exec bash'\"" ^m "python3 test/code_tests.py" ^m
sleep 1

tmux attach -t glacia
