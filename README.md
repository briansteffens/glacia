glacia
======

`glacia` is an experimental programming language. Its primary distinguishing
characteristic is that glacia programs are loaded into and then run out of
databases. All program state is stored in a database. This makes glacia
extremely slow but also allows glacia programs to be resumed, even after a
power failure or similar event.


Downloading and prerequisites
=============================

* __git__ - For downloading the source code.
* __Vagrant__ - For provisioning the development VM.

On Debian-based systems, the following should handle all dependencies:

```
$ sudo apt-get install git vagrant
```

To download glacia, navigate to the desired folder and then clone the
repository:

```
git clone https://github.com/briansteffens/glacia
cd glacia
```

Building the VM
===============

From the root of the git repository, bring up the virtual machine with the
following:

```
vagrant/up
```

*Note:* The standard `vagrant up` also works. The difference is `vagrant/up`
also remotes into the VM over SSH, builds a testing session in tmux, and runs
the testing suite.
