#!/usr/bin/env python2.7
# encoding: utf-8

import os
import re
import logging

from otto.lib.otypes import ApplianceUsage
from otto.connections.ssh_pexpect import Ssh, TIMEOUT, EOF

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class Switch(Ssh):
    """
    A class for interacting with Arista or Dell switches.
    Arista ports are just a port value.
    Dell ports have the form: <unit>/<port-type><port>
        ex: 1/g45   

    To use this module, ssh must be enabled on Dell switches

    Basic Usage:
        from otto.appliance import switch

        s = switch.Switch(uname, host, passwd, swtype='auto', prompt='>')
        s.connect()

    """

    def __init__(self, user, host, password, swtype='auto', prompt='>'):
        self.user = user
        self.host = host
        self.password = password
        self.swtype = swtype.lower()
        self.prompt = prompt
        self.reg = re.compile('(\\d+)(/)(g|xg)(\\d+)')

    def connect(self):
        """
        Overloaded to handle auto-detection
        """
        super(Switch, self).connect()
        if self.swtype == 'auto':
            self.__autotype()

    def disconnect(self):
        """
        Dell disconnects in an odd fashion
        Handles disconnecting appropriately
        """
        if self.swtype == 'arista':
            super(Switch, self).disconnect()
        elif self.swtype == 'dell':
            try:
                self.run('quit')
            except EOF:
                super(Switch, self).disconnect()

    def __autotype(self):
        """
        Determines the type of switch the module is connected to
        """
        # Dell
        try:
            ret = self.run('show system\n')
        except TIMEOUT:
            ret = self.before
        if 'Dell' in ret:
            self.swtype = 'dell'
        else:
            # Arista
            ret = self.run('show version')
            if 'Arista' in ret:
                self.swtype = 'arista'
            else:
                logger.error("__autotype: Incorrect type of switch")

    def up(self, port):
        """
        Brings up the port specified
        Correctly formats the port number specified depending on switch type
        """
        temp = self.prompt
        if self.swtype == 'dell':
            m = self.reg.match(port)
            if not m:
                n = re.match('(\\d+)', port)
                if n:
                    port = '1/g%s' % port  # assuming you wanted a gigabit interface
                else:
                    logger.error("up: Incorrect port format")
                    return False
        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        self.run('interface ethernet %s' % port)
        self.run('no shutdown')
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def down(self, port):
        """
        Shuts down the port specified
        Correctly formats the port number specified depending on switch type
        """
        temp = self.prompt
        if self.swtype == 'dell':
            m = self.reg.match(port)
            if not m:
                n = re.match('(\\d+)', port)
                if n:
                    port = '1/g%s' % port  # assuming you wanted a gigabit interface
                else:
                    logger.error("down: Incorrect port format")
                    return False
        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        self.run('interface ethernet %s' % port)
        self.run('shutdown')
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def chifmode(self, port, mode):
        """
        Changes the mode of the port
        Mode takes 3 options: access, general, trunk
        """
        temp = self.prompt
        if self.swtype == 'dell':
            m = self.reg.match(port)
            if not m:
                n = re.match('(\\d+)', port)
                if n:
                    port = '1/g%s' % port  # assuming you wanted a gigabit interface
                else:
                    logger.error("chifmode: Incorrect port format")
                    return False
        try:
            m = [x for x in ['access', 'general', 'trunk'] if mode == x][0]
        except IndexError:
            logger.error("chifmode: Incorrect Mode '%s'" % mode)
            return False

        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        self.run('interface ethernet %s' % port)
        self.run('switchport mode %s' % m)
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def mkvlan(self, segid):
        """
        Creates vlan of the given name
        """
        temp = self.prompt
        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        if self.swtype == 'dell':
            self.run('vlan database')
        self.run('vlan %s' % segid)
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def delvlan(self, segid):
        """
        Deletes vlan of the given name
        """
        temp = self.prompt
        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        if self.swtype == 'dell':
            self.run('vlan database')
        self.run('no vlan %s' % segid)
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def setvlan(self, port, segid):
        """
        Sets a port to specified, already created vlan
        """
        temp = self.prompt
        if self.swtype == 'dell':
            m = self.reg.match(port)
            if not m:
                n = re.match('(\\d+)', port)
                if n:
                    port = '1/g%s' % port  # assuming you wanted a gigabit interface
                else:
                    logger.error("setvlan: Incorrect port format")
                    return False
        self.prompt = '#'
        self.run('enable')
        self.run('configure')
        self.run('interface ethernet %s' % port)
        ret = self.run('switchport access vlan %s' % segid)
        if 'Interface not in Access Mode' in ret:
            logger.error('setvlan: Interface not in Access Mode')
        self.run('end')
        self.prompt = temp
        if self.swtype == 'dell':
            self.run('end')
        else:
            self.run('disable')

    def __filtermac(self, mac):
        """
        Filter all non-hex characters from mac
        All alphas returned lowercase
        """
        mac = mac.lower()
        s = ''
        for c in mac:
            try:
                s += '%x' % int(c, 16)
            except ValueError:
                pass
        if len(s) != 12:
            raise ApplianceUsage("Invalid MAC length: \"%s\"" % s)
        return s

    def __formatmac(self, swtype, mac):
        """
        Return an arista/dell delimited mac address
        Most stupidly, valid mac addresses in the arista/dell cli require dot delimiters.
        Neither recognize 00100401336b as a mac. Arista does recognize 0010.0401.336b.
        Dell does recognize 0010.0401.336B.
        """
        if self.swtype == 'arista':
            return mac[0:4].lower() + '.' + mac[4:8].lower() + '.' + mac[8:12].lower()
        else:
            return mac[0:4].upper() + '.' + mac[4:8].upper() + '.' + mac[8:12].upper()

    def mac2port(self, mac):
        """
        Return the port associated with mac from the address table, or None
        All non-hex delimiter characters in the mac are ignored
        """
        mac = self.__filtermac(mac)
        fmac = self.__formatmac(self.swtype, mac)
        if self.swtype == 'arista':
            cmd = 'show mac address-table address %s' % fmac
            # log.debug cmd here
            r = self.run(cmd)
            for l in r.split('\r\n'):
                ls = l.split()
                if len(ls) > 5 and ls[1] == fmac:
                    port = ls[3]
                    return port[2:]
        elif self.swtype == 'dell':
            cont = True
            temp = self.prompt
            self.prompt = '#'
            self.run('enable')
            try:
                self.run('show bridge address-table', timeout=0.1)
            except TIMEOUT:
                while cont:
                    try:
                        self.run('\r', timeout=0.1)
                    except (EOF, TIMEOUT):
                        pass
                    else:
                        cont = False
                        ret = self.before
                        self.prompt = temp
                        self.run('exit')
            for l in ret.split('\r\n'):
                ls = l.split()
                if len(ls) == 4 and ls[1] == fmac:
                    port = ls[2]
                    if 'xg' in port:
                        return port[4:]
                    else:
                        return port[3:]
