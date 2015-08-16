from random import choice, randint
from time import time
import unittest

from otto.lib.decorators import wait_until
from otto.lib.otypes import ReturnCode

choices = [True, False, False, False]


@wait_until()
def wait_something():
    ret = ReturnCode(choice([True, False, False, False]))
    ret.message = "%s: looking for True" % ret.status
    return ret


@wait_until(case=False)
def wait_something_false(val):
    return ReturnCode(val)


@wait_until(sleeptime=1)
def wait_something_sleep():
    global choices
    return choices.pop()


@wait_until(sleeptime=1)
def wait_something_sleeptime_param(para):
    ret = ReturnCode(True)
    ret.message = para
    return ret


@wait_until(timeout=5)
def wait_something_timeout_param(para):
    ret = ReturnCode(False)
    ret.message = "looking for timeout param passed to inner func = %s" % para
    print("waiting for timeout")
    return ret


@wait_until(timeout=5)
def wait_something_timeout():
    ret = ReturnCode(False)
    ret.message = "set to False"
    print("sleeping")
    return ret


@wait_until(case=False)
def wait_something_case():
    ret = ReturnCode(choice([True, True, True, False]))
    ret.message = "looking for False"
    print("sleeping")
    return ret


class rogue(object):
    def __init__(self):
        print('inited')

    def call_wait_something(self):
        print("\tcalling dosomething")
        return wait_something()

    def call_wait_something_timeout_param(self):
        print("\tcalling something_timeout_param of self")
        wait_something_timeout_param(self)
        return 'OK'


def now():
    """
    Return current epoch time
    """
    return time()


def since(start):
    """
    Return the number of seconds since input time
    """
    return now() - start


class TestWaitUntil(unittest.TestCase):
    def test_basic_wait(self):
        self.assertTrue(wait_something())

    def test_wait_something_case(self):
        self.assertFalse(wait_something_false(val=False))

    def test_wait_something_sleep(self):
        t = now()
        self.assertTrue(wait_something_sleep())
        self.assertGreater(since(t), 1)
        global choices
        choices = [True, False, False, False]

    def test_wait_something_sleeptime_param(self):
        """
        we can still pass a parameter through to wrapped function

        """
        para = randint(0, 4096)
        self.assertNotEqual(wait_something_sleeptime_param(para).message, 4097)
        self.assertEqual(wait_something_sleeptime_param(para).message, para)

# print("no params with a class:")
# c = rogue()
# print c.call_wait_something()
#
# print("pass through params with a class as param:")
# print c.call_wait_something_timeout_param()

if __name__ == '__main__':
    unittest.main()

    print "running tests"
