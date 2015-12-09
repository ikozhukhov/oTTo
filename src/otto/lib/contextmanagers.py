"""
Context managers for use in libraries
"""
from contextlib import contextmanager


@contextmanager
def ignored(*exceptions):
    """
    given a list of exceptions the code will run ingnoring any
    exceptions listed.
    """
    try:
        yield
    except exceptions:
        pass


@contextmanager
class cd:
    """
    This class changes the directory for calls in its scope

    Ex::
        print "PWD: %s" % l.run_and_check('pwd')
        with cd(l, '/tmp'):
            print "PWD: %s" % l.run_and_check('pwd')
        print "PWD: %s" % l.run_and_check('pwd')

    Output::

            PWD: /root
            PWD: /tmp
            PWD: /root

    """

    def __init__(self, initiator, directory):
        self.temp = initiator.cwd
        self.directory = directory
        self.initiator = initiator

    def __enter__(self):
        self.initiator.cwd = self.directory

    def __exit__(self, type, value, traceback):
        self.initiator.cwd = self.temp


class env:
    """
    This class add an entry the env dict which is used
    to construct an environmental string which is pre-pended
    to a run command.

    """

    def __init__(self, initiator, var, value):
        self.initiator = initiator
        self.var = var
        self.value = value
        self.oldvalue = None

    def __enter__(self):

        if not self.initiator.environmentals:
            self.initiator.environmentals = dict()
        else:
            if self.var in self.initiator.environmentals:
                self.oldvalue = self.initiator.environmentals.get(self.var)

        self.initiator.environmentals[self.var] = self.value

    def __exit__(self, type, value, traceback):
        if self.oldvalue:
            self.initiator.environmentals[self.var] = self.oldvalue
        else:
            self.initiator.environmentals.pop(self.var)
