#!/usr/bin/env python
# encoding: utf-8
"""
appliances
----------

These are classes for interacting with various Appliances.
Logging has to be configured from the script that instantiates
the class.

Basic Usage:
        from apc import *

        a = Apc(username, hostname, password)
        print a.state
        a.down(outlet)
        print a.state
        a.up(outlet)
        print a.state
"""

import re
import os
import logging
import socket

from otto.connections.telnet import Telnet
from otto.connections.ssh_pexpect import Ssh
from otto.lib.otypes import ApplianceError, ApplianceUsage, ReturnCode

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class PDU_telnet(Telnet):
    """
    A class for interacting with the apc pdu's using telnet.
    """

    def __init__(self, username, hostname, password, prompt):
        super(PDU_telnet, self).__init__(username, hostname, password, prompt)

    def disconnect(self):
        self.terminate()


class PDU_ssh(Ssh):
    """
    A class for interacting with the apc pdu's using ssh.
    """

    def __init__(self, username, hostname, password, prompt):
        super(PDU_ssh, self).__init__(username, hostname, password, prompt)


class Apc(object):
    """
    A class for interacting with the apc pdu's.
    """

    def __init__(self, username, hostname, password, prompt=None):
        # test if this is a telnet or ssh connection        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if s.connect_ex((hostname, 23)) == 0:  # the apc is accepting connections using telnet protocol.
            self.pdu = PDU_telnet(username, hostname, password, prompt)
        elif s.connect_ex((hostname, 22)) == 0:  # the apc is accepting connections using ssh protocol.
            self.pdu = PDU_ssh(username, hostname, password, prompt)
        else:
            message = 'We can not determine what protocol is being used by PDU %s' % hostname
            logger.error(message)
            raise ApplianceError(message)

    def run_and_check(self, cmd, expectation=True):
        """
        Run a command check the result.  If the caller cares about failure
        and the command fails we raise a generic exception.
        """
        result = ReturnCode(True)
        logger.info(cmd + " called")
        self.pdu.connect()
        result.message = self.pdu.run(cmd)
        self.pdu.disconnect()
        e = Exception()

        if not result.message.find('E000: Success'):
            if result.message.find('E101: Command Not Found') > -1:
                logger.error(result.message)
                result.status = False
                failmsg = cmd + " failed"
                e = ApplianceError(failmsg)

            elif result.message.startswith('E102: Parameter Error'):
                logger.critical(result.message)
                result.status = False
                failmsg = cmd + " failed"
                e = ApplianceUsage(failmsg)
                result.status = False

        if not expectation:
            return result
        elif not result.status:
            raise e
        return result

    @property
    def state(self):
        """
        Returns a dictionary with the state of each port in the APC.

        Sample output:
            {'1': {'name': 'powerconnect 6248', 'outlet': '1', 'state': 'On'},
             '10': {'name': 'esm-qa1', 'outlet': '10', 'state': 'On'},
             '11': {'name': 'agathon', 'outlet': '11', 'state': 'On'},
             '12': {'name': 'Outlet 12', 'outlet': '12', 'state': 'On'},
             '13': {'name': 'leoben', 'outlet': '13', 'state': 'On'},
             '8': {'name': '?nodeB', 'outlet': '8', 'state': 'On'},
             '9': {'name': 'ARISTA 7124SX', 'outlet': '9', 'state': 'On'}}

        """
        cmd = 'olstatus all'
        logger.info(cmd)
        columns = ['outlet', 'name', 'state']
        st = re.compile(r"E000.*")

        results = dict()
        r = self.run_and_check(cmd)
        rs = r.message.split('\r\n')
        stfound = False
        for line in rs:
            lclean = list()
            if not stfound:
                if st.search(line):
                    stfound = True
                    continue
            line = line.strip()
            ls = line.split(':')
            for j in ls:
                lclean.append(j.strip())
            p = dict(zip(columns, lclean))
            results[p['outlet']] = p
        return results

    def down(self, outlet, expectation=True, wait=True):
        """
        Turns off a particular port in the PDU specified by the outlet number.
        """
        outlet = str(outlet)
        cmd = 'oloff ' + outlet
        logger.info(cmd)
        result = self.run_and_check(cmd, expectation)
        if wait:
            up = True
            while up:
                stat = self.state[outlet]['state']
                if stat == 'Off':
                    up = False
        return result

    def up(self, outlet, expectation=True, wait=True):
        """
        Turns on a particular port in the PDU specified by the outlet number.
        """
        outlet = str(outlet)
        cmd = 'olon ' + outlet
        logger.info(cmd)
        result = self.run_and_check(cmd, expectation)
        if wait:
            down = True
            while down:
                stat = self.state[outlet]['state']
                if stat == 'On':
                    down = False
        return result

    def cycle(self, outlet, delay=5, expectation=True):
        """
        Power cycle a particular port in the PDU specified by the outlet number.

        An optional paramter (delay) can be specified as the time (in seconds) the power
        must remain off before turns the outlet on again.
        """
        outlet = str(outlet)
        cmd = 'olRbootTime ' + str(delay)
        logger.info(cmd)
        result = self.run_and_check(cmd, expectation)
        if result:
            cmd = 'olReboot ' + str(outlet)
            logger.info(cmd)
            result = self.run_and_check(cmd, expectation)
        return result
