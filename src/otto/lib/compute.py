# -*- coding: utf-8 -*-
"""
Basic numerical tools for use without requiring numpy, et. al.
Uses filter_for decorator from lib.decorators to facilitate direct
access to data in dictionaries
"""

from __future__ import print_function
import math

from otto.lib.decorators import filter_for


@filter_for
def getfrom(values):
    """
    pass through function for using the
    filter_for decorator directly
    """
    return values


@filter_for
def median(values):
    """
    :param values: a list of numerical values
    :return: statistical median for a list of values expressed as a float
    """
    values.sort()
    m = len(values) / 2

    if not len(values) % 2:  # not even
        return (values[m - 1] + values[m]) / 2.0  # average the middle two
    else:
        return values[m]


@filter_for
def average(values):
    """
    :param values: a list of numerical values
    :return:  average for a list of values expressed as a float
    """
    return sum(values) * 1.0 / len(values)


@filter_for
def variance(values):
    """
    :param values: a list of numerical values
    :return: the variance of a list of values expressed as a float
    """
    return average(map(lambda x: (x - average(values)) ** 2, values))


@filter_for
def standard_dev(values):
    """
    :param values: a list of numerical values
    :return: the variance of a list of values expressed as a float
    """
    return math.sqrt(variance(values))
