import unittest

from otto.lib.otypes import ReturnCode


class TestReturnCode(unittest.TestCase):
    def setUp(self):
        self.cases = (ReturnCode(False, message="test False"),
                      ReturnCode(True, message="test True"))

    def test_yield_ReturnType(self):
        for x in self.cases:
            self.assertIn('status', x.ResultType)
            self.assertIn('value', x.ResultType)
            self.assertIsInstance(x.ResultType['status'], str)
            self.assertIn(x.ResultType['status'], ['fail', 'pass', 'aborted'])


if __name__ == '__main__':
    unittest.main()
