#!/usr/bin/env python
# encoding: utf-8


import re
import os
import logging

from otto.connections.telnet import Telnet
from otto.lib.otypes import ReturnCode, ApplianceError

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class Netbooter(Telnet):
    """
    A class for interacting with the apc pdu's using telnet.
    """

    def __init__(self, user, hostname, password, prompt=None):
        self.username = user
        self.hostname = hostname
        self.password = password
        self.skip_login = True
        if prompt is None:
            self.prompt = ">"

    def connect(self, timeout=60, skip_login=True):
        super(Netbooter, self).connect(timeout, skip_login)
        return True

    def run_and_check(self, cmd, expectation=True):
        """
        Run a command check the result.  If the caller cares about failure
        and the command fails we raise a generic exception.
        """
        result = ReturnCode(True)
        logger.info(cmd + " called")
        result.message = self.run(cmd)

        if result.message.find('Invalid command or parameters.') > -1:
            # this will never work since the error is after the
            # prompt added except KeyError: to catch problems
            # below I suspect "expectation" might have a problem too.
            logger.error(result.message)
            result.status = False

        if not expectation:
            return result
        elif not result.status:
            raise ApplianceError(cmd + " failed")
        return result

    @property
    def state(self):
        cmd = 'pshow'
        temp_prompt = self.prompt
        self.prompt = "Power reboot duration"
        results = dict()
        r = self.run(cmd)
        self.prompt = temp_prompt
        rs = r.split('\r')
        for line in rs:
            m = re.search("\\b(\\d+)\\s+\\|\\s+\\S+\\s+\\|\\s+(\\S+)\\s+", line)
            if m:
                (outlet) = m.group(1)
                (state) = m.group(2)
                p = dict()
                p['state'] = state
                results[str(outlet)] = p
        return results

    def down(self, outlet, expectation=True, wait=True):
        outlet = str(outlet)
        cmd = 'pset %s 0' % outlet
        logger.info(cmd)
        result = self.run_and_check(cmd, expectation)
        if wait:
            up = True
            while up:
                try:
                    stat = self.state[outlet]['state']
                except KeyError:
                    raise ApplianceError("Either %s or %s are not present" % (outlet, "state"))
                if stat == 'Off':
                    up = False
        return result

    def up(self, outlet, expectation=True, wait=True):
        outlet = str(outlet)
        cmd = 'pset %s 1' % outlet
        logger.info(cmd)
        result = self.run_and_check(cmd, expectation)
        if wait:
            down = True
            while down:
                try:
                    stat = self.state[outlet]['state']
                except KeyError:
                    raise ApplianceError("Either %s or %s are not present" % (outlet, "state"))
                if stat == 'On':
                    down = False
        return result

    @property
    def version(self):
        cmd = 'ver'
        logger.info(cmd)
        result = self.run_and_check('ver')
        return result

    def __del__(self):
        self.closed = True
