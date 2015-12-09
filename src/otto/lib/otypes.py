#!/usr/bin/env python
# encoding: utf-8
# Created by Michaelian Ennis on 2011-02-01.
# Copyright (c) 2011 Coraid Inc. All rights reserved.
"""
    otypes is a collection of utility classes/types used by otto and scripts.
"""
from collections import namedtuple
from pprint import pformat


class ResultType(dict):
    """
    A generic return type for use in scripts.  This is the type expected to
    be returned by TestCase instances.  See also ReturnCode.ResultType
    """

    def __init__(self, status=None, value=None):
        obj = {'status': status, 'value': value}
        if obj['value'] is None:
            obj['value'] = "value was not set"

        super(ResultType, self).__init__(obj)

    def __str__(self):
        return '{0:>s}: {1:>s}'.format(self['status'], self['value'])


Data = namedtuple('Data', ['status', 'stdout', 'stderr'], verbose=False)


class ReturnCode(object):
    """
    A ReturnCode is an type otto uses with dual personalities.
    Calling a ReturnCode returns a Boolean or String depending
    on the context.  Generally when an error is returned by an
    appliance otto will store the string and set itself to False.
    When used as a string it returns a string.  When it is ambiguous
    which is required use obj.message for string and obj.status
    for boolean.

    This allows the user to do things like::

        r = m.mkpv(pool,target)
        if not r:
            print(r)

    Also supports the string functions startswith and endswith.
    """

    def __init__(self, status, message=""):
        self.status = status
        self.message = message
        self.raw = Data(int(), str(), str())

    def __str__(self):
        return str(self.message)

    def __nonzero__(self):
        return self.status

    def __cmp__(self, other):
        if self.message == other:
            return True
        else:
            return False

    def startswith(self, other):
        msg = str(self)
        result = msg.startswith(other)
        return result

    def endswith(self, other):
        return str(self).endswith(other)

    def __eq__(self, other):
        if type(other) == bool:
            return self.status == other
        if type(other) == str:
            return self.message == other

    def __repr__(self):
        return "status: %s, message: '%s'" % (self.status, self.message)

    def find(self, *args):
        return self.message.find(*args)

    def split(self, *args):
        return self.message.split(*args)

    @property
    def ResultType(self):
        """
        return self as a ResultType as used in scripts
        """
        return ResultType(status=('fail', 'pass')[bool(self)], value=self.message)


class AoEAddress(object):
    """
    AoEAddress is dynamic type that stores both a dictionary
    and a string.  If called with only one parameter the
    constructor will try to find a period and extract the
    major and minor from that.
    """
    # pylint: disable=R0912
    def __init__(self, major, minor=None):
        if minor is None:
            if type(major) == dict:
                try:
                    if major.get('slot'):
                        minor = major['slot']
                        major = major['shelf']
                    elif major.get('major'):
                        minor = major['major']
                        major = major['minor']
                except KeyError:
                    raise AoEError("When instantiating with a dict we need either\n"
                                   " 'major' and'minor or 'shelf' and'slot' keys")
            else:
                try:
                    major, minor = major.strip().split('.')
                except (ValueError, AttributeError):
                    raise AoEError("%s: if not set major should contain '.'" % __file__)
        major = int(major)
        if major > 65535:
            raise AoEError("major > 65535")
        elif major < 0:
            raise AoEError("major < 0")
        else:
            self._major = major

        minor = int(minor)
        if minor > 255:
            raise AoEError("minor > 255")
        elif minor < 0:
            raise AoEError("minor < 0")
        else:
            self._minor = minor

    def __str__(self):
        return '{0:>s}.{1:>s}'.format(str(self.major), str(self.minor))

    def __iadd__(self, other):
        current = self.minor
        self.slot = current + other
        return self

    def __add__(self, other):  # not sure this is the correct behavior
        return AoEAddress(self.major, self.minor + other)

    @property
    def major(self):
        return self._major

    @major.setter
    def major(self, major):
        if type(major) is not int:
            major = int(major)
        if major > 65535:
            raise AoEError("major > 65535")
        if major < 0:
            raise AoEError("major < 0")
        self._major = major

    @property
    def shelf(self):
        return self.major

    @shelf.setter
    def shelf(self, major):
        self.major = major

    @property
    def minor(self):
        return self._minor

    @minor.setter
    def minor(self, minor):
        if type(minor) is not int:
            minor = int(minor)
        if minor > 255:
            raise AoEError("minor > 255")
        elif minor < 0:
            raise AoEError("minor < 0")

        self._minor = minor

    @property
    def slot(self):
        return self.minor

    @slot.setter
    def slot(self, minor):
        self.minor = minor

    def __eq__(self, other):
        if isinstance(other, str):
            if self.__str__() == other:
                return True
            else:
                return False
        elif isinstance(other, AoEAddress):
            return self.major == other.major and self.minor == other.minor
        else:
            raise TypeError("AoEAddress __eq__ only supports comparison with str and AoEAddress types")


class ApplianceUsage(Exception):
    """
    An exception type used for usage errors returned by
    an appliance. Used in the appliance classes.
    """
    pass


class ApplianceError(Exception):
    """
    An exception type used for usage errors returned by
    an appliance. Used in the appliance classes. If srx.disks
    or srx.release have been called those will be available
    in the exception.
    """

    def __init__(self, message=None, appliance=None):
        self.appliance = appliance
        self.data = {'message': message}
        super(ApplianceError, self).__init__(message)
        self.message = message

        if hasattr(self.appliance, 'cache'):
            for attr in ['disks', 'release']:  # add new things here
                val = self.appliance.cache.get(attr)
                if val:
                    self.data[attr] = val

    def __str__(self):
        return pformat(self.data)


class InitiatorUsage(Exception):
    pass


class InitiatorError(Exception):
    pass


class ConnectionError(Exception):
    pass


class LibraryError(Exception):
    pass


class AoEError(Exception):
    def __init__(self, message):
        super(AoEError, self).__init__(message)
        self.message = message


class Namespace(dict):
    """
    A subclass of a dict that allows dotted lookups::

        config.srx1.shelf

    """

    def __init__(self, obj=None):
        if obj is None:
            obj = {}
        super(Namespace, self).__init__(obj)
        for k, v in obj.items():
            if type(v) == dict:
                self.__setattr__(k, Namespace(v))
            else:
                self.__setattr__(k, v)


class Drive(dict):
    def __init__(self, shelf, slot, runner):
        assert isinstance(slot, int)
        self.shelf = shelf
        self.slot = slot
        self.runner = runner
        super(Drive, self).__init__()

    def __iter__(self):
        return iter(self._get_data())

    def __repr__(self):
        return str(self._get_data())

    def keys(self):
        return self._get_data().keys()

    def values(self):
        return self._get_data().values()

    def __getitem__(self, item):
        vals = self._get_data()

        if item in vals:
            return vals[item]
        else:
            return None

    def __getattr__(self, item):
        vals = self._get_data()

        if item in vals:
            return vals[item]
        else:
            return None

    def get(self, item):
        return self._get_data().get(item)

    def _get_data(self):
        ddict = dict()
        cmd = 'drives -j %s.%s' % (self.shelf, self.slot)
        ret = self.runner(cmd)
        if ret:
            drives_j = ret.message.splitlines()
        else:
            return {}

        for line in drives_j:

            key, value = line.split(':', 1)
            if value.strip().startswith("'"):
                value = value.lstrip("'").rstrip("'").strip()
            ddict[key] = value
        return ddict
