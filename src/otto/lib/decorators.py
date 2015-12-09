import functools
from time import sleep

from otto.lib.otypes import ReturnCode
from otto.utils import now


def wait_until(case=True, timeout=None, sleeptime=.5):
    """
    A decorator for functions that need a wait version. If the function doesn't
    yeild a result where::

        result.__eq__(case) is True

    this decorator waits sleeptime seconds then runs it again exiting
    only when above case is met or timeout is exceeded.

    This will not work for a generator function.
    """

    def waiter(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            result = ReturnCode(not case)

            if timeout is None:
                while bool(result) != bool(case):
                    result = function(*args, **kwargs)
                    if bool(result) != case:  # no need to sleep if case is met
                        sleep(wrapper.sleeptime)
            else:
                starttime = now()
                while now() - starttime < float(wrapper.timeout):
                    result = function(*args, **kwargs)
                    if bool(result) == case:
                        break
                    sleep(wrapper.sleeptime)

            if bool(result) != case:
                result = ReturnCode(False)
                result.message = "Timed out : {0} seconds".format(timeout)
            return result

        wrapper.case = case
        wrapper.timeout = timeout
        wrapper.sleeptime = sleeptime
        return wrapper

    return waiter


def filter_for(function):
    """
    A decorator for extracting data from a list of dictionaries.
    If the wrapped function is called with::

        field=<some key>

    extract data from a list of dicts if field is specified
    given a structure like::

        [{'bw': 2029.6, 'io': 458152.0, 'iops': 16236.0, 'runt': 226039.0},
        {'bw': 2046.8, 'io': 458252.0, 'iops': 16374.0, 'runt': 224134.0},
        {'bw': 2019.5, 'io': 458352.0, 'iops': 16155.0, 'runt': 227173.0},
        {'bw': 2005.4, 'io': 458452.0, 'iops': 16042.0, 'runt': 228762.0}]

    and field='bw' this will present [2029.6, 2046.8, 2019.5, 2005.4] to
    the wrapped function
    """

    @functools.wraps(function)
    def wrapper(values, field=None):
        if field:
            v = list()
            for l in values:
                v.append(l.get(field))
        else:
            v = values
        return function(v)

    return wrapper
