#!/usr/bin/env python
#
# Copyright (c) 2014 Coraid, Inc.
# All rights reserved.
#
# $Coraid$
#
"""
Interface to read, digest and display information regarding
AoE Targets and their corresponding system information.
"""

from os import stat, listdir, path
from stat import S_ISBLK

from pprint import pformat
import re
from time import time
from json import dumps

ETHDRV_DEVICES_FILE = "/proc/ethdrv/devices"
ETHDRV_TARGETS_FILE = "/proc/ethdrv/targets"
ETHDRV_DEV_DIR = "/dev/ethdrv"


def int2bitmask(integer):
    """
    given a integer return a string that
    represents the bits::

        >>> int2bitmask(15903)
        >>> '11111000011111'

    """
    return integer >= 0 and str(bin(integer))[2:] or "-" + str(bin(integer))[3:]


def bitmask2index(bitmask):
    """
    given a string representing a bitmask
    return a list of positions that are not
    zero::

        >>> bitmask2index('11111000011111')
        >>> [0, 1, 2, 3, 4, 9, 10, 11, 12, 13]

    """
    rmask = reversed(str(bitmask))
    return [bitmask.start() for bitmask in re.finditer('1', ''.join(rmask))]


def mk_portlist(intval):
    """
    Take an integer representation of a bitmask and return a list form::

        > mk_portlist(3)
        [0,1]

    :type intval: int
    :return: a list of ports in bitmask
    :rtype: list
    """
    return bitmask2index(int2bitmask(intval))


def is_block(fpath):
    """
    given an absolute path determine if it's
    a block device
    """
    return path.exists(fpath) and S_ISBLK(stat(fpath).st_mode)


def mk_map(name):
    """
    make a map of block devices to targets using listdir
    by looking for softlinks and following the reference
    to determine if it's a block device.
    """
    device_map = dict()

    if path.exists(name):
        for fname in listdir(name):
            pname = path.join(name, fname)
            if path.islink(pname):
                realpath = path.realpath(pname)
                if is_block(realpath):
                    device_map[fname] = path.basename(realpath)
    return device_map


class AoETarget(object):
    """
    A class representing an AoE Target from the perspective of
    an initiator.
    """

    def __init__(self, bussaddress, aoeaddress, size, serial, naa):
        self.scsiaddress = bussaddress
        self.target = aoeaddress
        self.file = "init"
        self.size = size
        self.ports = set()
        self.macs = list()
        self.targpath = dict()
        self.serial = serial
        self.naa = naa

    def add_mac(self, mac):
        """
        add a mac address to this target
        """
        self.macs.append(mac)

    def add_ports(self, ports):
        """
        read a line that looked like::

            185.0 002590c7671e 3 1

        we convert 3 into [0,1] and extend self.ports with it
        """
        portlist = mk_portlist(ports)
        self.ports.update(portlist)

    def add_path(self, port, mac):
        """
        We read a line that looked like::

            185.0 002590c7671e 3 1

        we converted 3 into [0,1] and then sent

            {0: '00259096645f'}

        to this method, add_path, which adds

            00259096645f

        to self.targpath[0]['address']
        """
        if not self.targpath.get(port):
            self.targpath[port] = [mac]
        else:
            self.targpath[port].append(mac)

    def __repr__(self):
        state = self.file if self.file is not 'init' else "init"
        return pformat({'target': self.target,
                        'file': self.file,
                        'devpath': "/dev/%s" % state,
                        'size': self.size,
                        'port': self.ports,
                        'macs': self.macs,
                        'targpath': self.targpath})


class AoEStat(object):
    """
    A class to manage the AoEStat data.  It is a class to both
    facilitate testing of itself and to be reusable in the automation library.
    """

    def __init__(self, scantime=5):

        self.devices_file = ETHDRV_DEVICES_FILE
        self.targets_file = ETHDRV_TARGETS_FILE
        self.dev_dir = ETHDRV_DEV_DIR
        self.scantime = scantime
        self.lastscan = None
        self._devices = list()
        self.debug = None
        self.mk_map = mk_map

    @staticmethod
    def open_file(name):
        """
        mockable inteface to open
        """
        return open(name)

    @staticmethod
    def mk_map(name):
        """
        mockable interface to listdir related calls
        """
        device_map = dict()

        if path.exists(name):
            for fname in listdir(name):
                pname = path.join(name, fname)
                if path.islink(pname):
                    realpath = path.realpath(pname)
                    if is_block(realpath):
                        device_map[fname] = path.basename(realpath)
        return device_map

    @staticmethod
    def mk_portstr(ports):
        """
        given a list of ports return a string
        if the list is empty return "N/A"
        """
        return ",".join([str(port) for port in ports]) or 'N/A'

    @property
    def devices(self):
        """
        return a list of AoETargets seen and processed
        """
        return self._devices

    def get_devices(self):
        """
        device entries look like::

            3:0:185:0 185.0 480.103GB

        """
        fhandle = self.open_file(self.devices_file)
        lines = fhandle.read().strip()
        for line in lines.splitlines():
            serial, naa = None, None
            busaddress, aoeaddress, size = line.split()[:3]
            if len(line.split()) > 3:
                serial, naa = line.split()[3:5]
            self.devices.append(AoETarget(busaddress, aoeaddress, size, serial, naa))

    def get_targets(self):
        """
        target entries look like this::
            185.0 002590c7671e 3 1

                   185.0 (string) AoE address
            002590c7671e (string) mac address
                       3 (bitmask) of ports that can see that mac address
                       1 (bool) mac is active

        add the 185.0 to self.devices
        add 002590c7671e to self.targpaths[0] and self.targpaths[0]

        we don't currently do anything with the 'active' information
        """

        fhandle = self.open_file(self.targets_file)
        lines = fhandle.read().strip()

        for line in lines.splitlines():

            aoeaddress, mac, ports = line.split()[:3]
            ports = int(ports)

            for device in self.devices:
                if device.target == aoeaddress:
                    device.add_mac(mac)
                    device.add_ports(ports)

                    portlist = mk_portlist(ports)
                    for port in portlist:
                        device.add_path(port, mac)
                    break

    def map_devices(self):
        """
        determine which AoE target backs which scsi device and
        add that to the device as 'file'

        if the device is partitioned we skip everything but the
        base device

        """

        targmap = self.mk_map(self.dev_dir)

        for targ, dev in targmap.iteritems():
            canary = True
            targ = targ[1:]
            if len(targ.split('p')) > 1:
                continue
            for device in self.devices:
                if device.target == targ:
                    device.file = dev
                    canary = False
                    break
            if canary:
                raise Exception("couldn't find target: %s %s" % (targ, dev))

    def update(self):
        """
        read and process information from the filesystem and
        update properties
        """
        self.get_devices()
        self.get_targets()
        self.map_devices()
        self.lastscan = time()

    def output(self, json=False, paths=False):
        """
        format the current state information for output
        """

        if json:
            data = dict()
            for entry in self.devices:
                # can't use __repr__ for some json lib reason
                data[entry.target] = {'target': entry.target,
                                      'file': entry.file,
                                      'devpath': "/dev/%s" % entry.file,
                                      'size': entry.size,
                                      'port': self.mk_portstr(entry.ports),
                                      'macs': ",".join(entry.macs),
                                      'paths': entry.targpath,
                                      'serial': entry.serial,
                                      'naa': entry.naa,
                                      }

            return dumps(data, sort_keys=True, indent=4, separators=(',', ': '))

        else:
            fmtstr = "e%(target)-10s%(file)-8s%(size)+13s    %(port)s\n"
        output = ""
        for entry in self.devices:
            output += fmtstr % {'target': entry.target,
                                'file': entry.file,
                                'path': "/dev/%s" % entry.file,
                                'size': entry.size,
                                'port': self.mk_portstr(entry.ports),
                                'macs': ",".join(entry.macs),
                                }
            if paths:
                for port, macaddrs in entry.targpath.iteritems():
                    macs = ", ".join(macaddrs)
                    output += '{0:>12}        {1:<17}\n'.format(port, macs)
        return output


if __name__ == '__main__':
    from signal import signal, SIGPIPE, SIG_DFL
    from optparse import OptionParser

    signal(SIGPIPE, SIG_DFL)

    parser = OptionParser()
    parser.add_option("-j", "--json",
                      help="Output data as json",
                      action="store_true")
    parser.add_option("-a", "--all",
                      help="Display all target paths",
                      action="store_true")
    (options, args) = parser.parse_args()

    aoestat = AoEStat()
    try:
        aoestat.update()
    except IOError:
        exit(1)
    print aoestat.output(json=options.json, paths=options.all),
