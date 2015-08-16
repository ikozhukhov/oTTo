#!/usr/bin/env python
# encoding: utf-8
"""

These are classes for interacting with the Eaton Switched ePDU.
Logging has to be configured from the script that instantiates
the class.

Basic Usage:
        from eaton import *

        pdu = Eaton(username, hostname, password, port=5001)
        pdu.connect()
        print pdu.state
        pdu.down(outlet)
        print pdu.state
        pdu.up(outlet)
        print pdu.state
"""

import re
import os
import logging

from otto.lib.pexpect import spawn
from otto.lib.otypes import ReturnCode, ApplianceError

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class Telnet(spawn, object):
    """
    Connect via telnet.
    """

    def __init__(self, username, hostname, password, prompt, port=None):
        self.username = username
        self.hostname = hostname
        self.password = password
        self.prompt = prompt
        self.port = port

    def connect(self, timeout=60):
        """
        Connect to and authenticate with the pdu.
        This telnet interface for the Eaton pdu is pretty specialized.
        Also, it depends sometimes on where a previous user left off.
        When trying to connect, you can be at the login screen or already 
        logged in and on either the main menu or a sub-menu.
        This method doesn't return until on the main menu ( which is
        what the methods in the Eaton class expect ).
        """
        cmd = "telnet"
        args = list()
        args.append(self.hostname)
        if self.port:
            args.append(self.port)
        logger.debug(args)

        main_menu = False
        spawn.__init__(self, cmd, args, timeout)
        while True:
            # continues until on the main menu
            m = self.expect(["Main Menu", "UserName", "Password", "\[\+none", "<ESC> = Back"])
            if m == 0:
                break
            elif m == 1:
                self.sendline(self.username)
                continue
            elif m == 2:
                self.sendline(self.password)
                continue
            elif m == 3:
                # for [+none, bootes], need to hit enter
                self.send("\r")
                continue
            elif m == 4:
                # hit escape until out of each sub-menu
                self.send('\x1b')
                continue
        return True


class Eaton(Telnet):
    """
    A class for interacting with the Eaton pdu's using telnet.
    """

    def __init__(self, username, hostname, password, prompt=None, port=None):
        self.connected = False
        self.username = username
        self.hostname = hostname
        self.password = password
        self.port = port
        self.skip_login = True
        if prompt is None:
            self.prompt = ">"

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
        results = dict()
        self.send("1")
        self.expect("Control Sub Menu")
        self.send("1")
        self.expect("Outlet State Sub Menu")
        self.send("1")
        self.expect("Next outlet section")
        output = self.before
        self.sendline("n")
        self.expect("Next outlet section")
        output = output + self.before
        self.sendline("n")
        self.expect("Next outlet section")
        output = output + self.before
        rs = output.split('\r')
        for line in rs:
            m = re.search("(\d+)\s+(\S.*)\s+(On|Off|REB)", line)
            if m:
                (outlet) = m.group(1)
                (name) = m.group(2)
                (state) = m.group(3)
                p = dict()
                p['state'] = state
                p['name'] = name.strip()
                p['outlet'] = outlet
                results[str(outlet)] = p
                # get back to main menu
        for i in range(0, 4):
            self.send('\x1b')
            self.expect("Select Item Number")
        return results

    def down(self, outlet, expectation=True, wait=True):
        """
        Turns off a particular port in the PDU specified by the outlet number.
        """
        outlet_state = self.state
        result = ReturnCode(True)
        outlet = str(outlet)
        logger.info("down %s" % outlet)
        self.send("1")
        self.expect("Control Sub Menu")
        self.send("1")
        self.expect("Outlet State Sub Menu")
        if int(outlet) in range(1, 9):
            self.send("1")
        elif int(outlet) in range(9, 17):
            self.send("2")
        elif int(outlet) in range(17, 25):
            self.send("3")
        self.expect("Outlet Control Sub Menu")
        self.send(outlet)
        self.expect("%s Command Choices" % outlet_state[outlet]['name'])
        self.send("2")
        self.expect("%s Requested Command is Immediate Off" % outlet_state[outlet]['name'])
        self.send("\r")
        self.expect("Outlet State Sub Menu")
        if not expectation:
            return result
        elif re.search("error|fail", self.before, re.MULTILINE | re.I):
            raise ApplianceError("powering off outlet failed")
            # get back to main menu
        for i in range(0, 3):
            self.send('\x1b')
            self.expect("Select Item Number")
        if wait:
            up = True
            while up:
                stat = outlet_state[outlet]['state']
                if stat == 'Off':
                    up = False
        return result

    def up(self, outlet, expectation=True, wait=True):
        """
        Turns on a particular port in the PDU specified by the outlet number.
        """
        outlet_state = self.state
        result = ReturnCode(True)
        outlet = str(outlet)
        logger.info("up %s" % outlet)
        self.send("1")
        self.expect("Control Sub Menu")
        self.send("1")
        self.expect("Outlet State Sub Menu")
        if int(outlet) in range(1, 9):
            self.send("1")
        elif int(outlet) in range(9, 17):
            self.send("2")
        elif int(outlet) in range(17, 25):
            self.send("3")
        self.expect("Outlet Control Sub Menu")
        self.send(outlet)
        self.expect("%s Command Choices" % outlet_state[outlet]['name'])
        self.send("1")
        self.expect("%s Requested Command is Immediate On" % outlet_state[outlet]['name'])
        self.send("\r")
        self.expect("Outlet State Sub Menu")
        if not expectation:
            return result
        elif re.search("error|fail", self.before, re.MULTILINE | re.I):
            raise ApplianceError("powering on outlet failed")
            # get back to main menu
        for i in range(0, 3):
            self.send('\x1b')
            self.expect("Select Item Number")
        if wait:
            down = True
            while down:
                stat = outlet_state[outlet]['state']
                if stat == 'On':
                    down = False
        return result

    def cycle(self, outlet, expectation=True):
        """
        Power cycle a particular port in the PDU specified by the outlet number.
        """
        outlet_state = self.state
        result = ReturnCode(True)
        outlet = str(outlet)
        logger.info("cycle %s" % outlet)
        self.send("1")
        self.expect("Control Sub Menu")
        self.send("1")
        self.expect("Outlet State Sub Menu")
        if int(outlet) in range(1, 9):
            self.send("1")
        elif int(outlet) in range(9, 17):
            self.send("2")
        elif int(outlet) in range(17, 25):
            self.send("3")
        self.expect("Outlet Control Sub Menu")
        self.send(outlet)
        self.expect("%s Command Choices" % outlet_state[outlet]['name'])
        self.send("3")
        self.expect("%s Requested Command is Reboot" % outlet_state[outlet]['name'])
        self.send("\r")
        self.expect("Outlet State Sub Menu")
        if not expectation:
            return result
        elif re.search("error|fail", self.before, re.MULTILINE | re.I):
            raise ApplianceError("pdu cycle failed")
            # get back to main menu
        for i in range(0, 2):
            self.send('\x1b')
            self.expect("Select Item Number")

    def disconnect(self):
        """
        Disconnect from host.
        """
        self.terminate(force=True)
        return True

    def __del__(self):
        self.closed = True
