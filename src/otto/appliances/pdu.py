#!/usr/bin/env python
# encoding: utf-8
"""

Class for interacting with a PDU.
Currently supports the following types:
  --apc
  --eaton
  --netbooter

The methods in this class are wrappers around the classes in apc.py, eaton.py, netbooter.py

Basic Usage:
        from pdu import Pdu

        pdu = Pdu(username, hostname, password, pdu_type )
        pdu.connect()
        pdu.down(outlet)
        pdu.up(outlet)
        pdu.cycle(outlet)
        print( pdu.state )


"""

import os
import logging

from otto.appliances.apc import Apc
from otto.appliances.eaton import Eaton
from otto.appliances.netbooter import Netbooter

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class Pdu(object):
    """
    A class for interacting with the pdu
    """

    def __init__(self, username, hostname, password, pdu_type, prompt=None, port=None):
        self.pdu_type = pdu_type
        self.username = username
        self.hostname = hostname
        self.password = password
        self.port = port
        self.skip_login = True
        if prompt is None:
            self.prompt = ">"
        if self.pdu_type == 'apc':
            self.pdu = Apc(username, hostname, password, prompt='apc>')
        elif self.pdu_type == 'eaton':
            self.pdu = Eaton(username, hostname, password, port=str(port))
        elif self.pdu_type == 'netbooter':
            self.pdu = Netbooter(username, hostname, password)

    def connect(self):
        if self.pdu_type == 'apc':
            # if apc, you're already connected at __init__
            pass
        else:
            return self.pdu.connect()

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
        return self.pdu.state

    def down(self, outlet, expectation=True, wait=True):
        """
        Turn off a particular port in the PDU specified by the outlet number.
        """
        return self.pdu.down(outlet, expectation=expectation, wait=wait)

    def up(self, outlet, expectation=True, wait=True):
        """
        Turn on a particular port in the PDU specified by the outlet number.
        """
        return self.pdu.up(outlet, expectation=expectation, wait=wait)

    def cycle(self, outlet, delay=None, expectation=True):
        """
        Power cycle a particular port in the PDU specified by the outlet number.
        """
        if self.pdu_type == 'netbooter':
            self.pdu.down(outlet, expectation=expectation)
            return self.pdu.up(outlet, expectation=expectation)
        elif self.pdu_type == 'eaton':
            if delay:
                logger.warning("Eaton cycle doesn't have delay option")
            return self.pdu.cycle(outlet, expectation=expectation)
        else:
            return self.pdu.cycle(outlet, expectation=expectation, delay=delay)

    def __del__(self):
        self.closed = True
