from otto.lib.otypes import ResultType


class Test(object):
    """
    A Base Class for tests
    The return types are specified so that we can detect if the child's
    signature doesn't match the parents
    """

    def __init__(self, config):
        self.testformat = 1
        self.config = config

    def setup(self):
        Result = ResultType(status='aborted', value='entering setup')
        return Result

    def teardown(self):
        Result = ResultType(status='aborted', value='entering teardown')
        return Result
