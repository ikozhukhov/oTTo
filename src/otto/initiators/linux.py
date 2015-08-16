#!/usr/bin/env python2.7
"""
Linux
-----
A paramiko based Linux initiator module.
"""

import os
import re
import time
import logging
from collections import defaultdict
import gzip
import cStringIO

from otto.connections.ssh import Client
from otto.initiators.ethdrv import Ethdrv
from otto.lib.decorators import wait_until
from otto.lib.otypes import InitiatorError, ReturnCode, Namespace, AoEAddress

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.initiators')
logger.addHandler(logging.NullHandler())


def _expand_path(path):
    return '"$(echo %s)"' % path


#  _escape_for_regex is from Fabric there are other ideas from Fabric in here.
# Copyright (c) 2009-2015 Jeffrey E. Forcier
# Copyright (c) 2008-2009 Christian Vest Hansen
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice,
#       this list of conditions and the following disclaimer in the documentation
#       and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


def _escape_for_regex(text):
    """Escape ``text`` to allow literal matching using egrep"""
    regex = re.escape(text)
    # Seems like double escaping is needed for \
    regex = regex.replace('\\\\', '\\\\\\')
    # Triple-escaping seems to be required for $ signs
    regex = regex.replace(r'\$', r'\\\$')
    # Whereas single quotes should not be escaped
    regex = regex.replace(r"\'", "'")
    return regex


class Initiator(object):
    def __init__(self, coraid_module):
        self.coraid_module = coraid_module
        self._aoeversion = None

    def aoediscover(self):
        """
        Call the driver's discover command.  Returns ReturnCode object

        """
        cmd = 'echo discover > /proc/ethdrv/ctl'
        return self.run_and_check(cmd)

    def aoeflush(self, aflag=True):
        """
        Call the driver's flush command. Return a ReturnCode object.
        """
        return self.run_and_check('ethdrv-flush %s' % ('', '-a')[aflag])

    @property
    def aoestat(self):
        """
        Returns a dictionary of either the 'aoe-stat' output, or
        the 'ethdrv-stat' output (based on self.coraid_module) in the
        following format::

                {'1270.0': {'claim': None,
                            'device': None,
                            'file': 'sde',
                            'ifs': [0, 1],
                            'iounit': None,
                            'path': '/dev/sde',
                            'paths': None,
                            'port': [0, 1],
                            'size': '100.030GB',
                            'state': None,
                            'target': '1270.0',
                            'targpath': {0: {'address': ['00259096645f', '00259096645e'],
                                             'port': 0
                                            },
                                         1: {'address': ['00259096645f', '00259096645e'],
                                             'port': 1
                                            }
                                        }
                            }
                }

        """
        stat = defaultdict(lambda: {'file': None, 'device': None, 'path': None, 'port': None, 'ifs': None,
                                    'target': None, 'size': None, 'iounit': None, 'state': None, 'claim': None,
                                    'paths': None, 'targpath': defaultdict(lambda: {'address': None, 'port': None})})
        cmd = '%s-stat -a | gzip' % self.coraid_module

        r = self.run_and_check(cmd)

        r.message = gzip.GzipFile('', 'r', 0, cStringIO.StringIO(r.message)).read()
        if self.coraid_module == "ethdrv":
            if self._aoeversion:
                v = self._aoeversion
            else:
                v = self.aoeversion

            lines = r.message.splitlines()
            for l in lines:
                f = l.split()
                if f[0].startswith('e'):
                    # the target column changed between 5.2.2 and 5.2.3
                    if v['major'] == 5:
                        if v['minor'] > 2 or (v['minor'] == 2 and v['revision'] >= 3):
                            target = f[0][1:]
                            device = f[1]
                        else:
                            target = f[1][1:]
                            device = f[0]
                    elif v['major'] > 5:
                        target = f[0][1:]
                        device = f[1]
                    else:
                        target = f[1][1:]
                        device = f[0]

                    stat[target]['target'] = target
                    stat[target]['file'] = device
                    stat[target]['path'] = "/dev/%s" % device  # deprecated
                    stat[target]['size'] = f[2]

                    if f[3].find('N/A') is -1:
                        f[3] = [int(n) for n in f[3].split(',')]
                    else:
                        f[3] = list()
                    stat[target]['port'] = f[3]
                    stat[target]['ifs'] = stat[target]['port']  # deprecated
                else:
                    p = int(f[0])
                    f[1] = f[1].strip(',')
                    stat[target]['targpath'][p].update({'port': p, 'address': list(f[1:])})
                    continue

        elif self.coraid_module == "aoe":
            lines = str(r).split('\n')
            for l in lines:
                f = l.split()
                if not l or not len(f) > 3:
                    continue
                targ = f[0]
                if targ.startswith('e'):
                    targ = targ[1:]

                stat[targ] = {}
                stat[targ]['target'] = targ
                stat[targ]['file'] = f[0]
                stat[targ]['path'] = "/dev/etherd/%s" % f[0]  # deprecated
                stat[targ]['size'] = f[1]
                stat[targ]['port'] = f[2].split(',')

                for i in range(len(stat[targ]['port'])):
                    if stat[targ]['port'][i].startswith('eth'):
                        stat[targ]['port'][i] = stat[targ]['port'][i][3:]

                stat[targ]['ifs'] = stat[targ]['port']  # deprecated
                if len(f) > 4:
                    stat[targ]['iounit'] = f[3]
                    stat[targ]['state'] = f[4]
                else:
                    # the iounit column is missing as of aoe6-79pre4
                    stat[targ]['iounit'] = ""
                    stat[targ]['state'] = f[3]
                    # logger.debug("aoestat: %s" % str(stat))

        return Namespace(stat)

    @property
    def aoeversion(self):
        """
        Returns the version string output
        of the AoE driver specified by self.coraid_module.
        """
        ret = {}
        if self.coraid_module == 'ethdrv':
            cmd = 'ethdrv-release'
        elif self.coraid_module == 'aoe':
            cmd = 'aoe-version'
        else:
            raise InitiatorError("unknown module type %s" % self.coraid_module)
        vers = str(self.run_and_check(cmd))

        if self.coraid_module == "ethdrv":
            # root@python2 ~# ethdrv-release
            # 5.2.6-R0
            # root@python2 ~#
            mmrr = r"^([0-9]+)\.([0-9]+)\.([0-9]+)\-R([0-9]+)?"
            m = re.match(mmrr, vers)
            if m:
                ret = {'major': int(m.group(1)),
                       'minor': int(m.group(2)),
                       'revision': int(m.group(3)),
                       'release': 0}
                if m.lastindex == 4:
                    ret['release'] = int(m.group(4))
            else:
                # root@python2 ~# ethdrv-release
                # installed ethdrv driver:    6.0.1-R5
                # running ethdrv driver:    6.0.1-R5
                # root@python2 ~#
                for l in vers.split('\n'):
                    if not l:
                        continue
                    m = re.match(r"[ \t]*(installed|running) ethdrv driver:[ \t]+(.*)", l)
                    if m:
                        ret[m.group(1)] = m.group(2)
                        # maj, min, rev, & rel default to running version,
                        # but if not loaded, fall back to installed version
                        m2 = re.match(mmrr, m.group(2))
                        if m2:
                            ret['major'] = int(m2.group(1))
                            ret['minor'] = int(m2.group(2))
                            ret['revision'] = int(m2.group(3))
                            ret['release'] = 0
                            if m2.lastindex == 4:
                                ret['release'] = int(m2.group(4))
        else:
            for l in vers.split('\n'):
                if not l:
                    continue
                ls = l.split(':')
                key = ls[0].strip()
                # keep "aoetools" as a key, but isolate
                # "installed" from "installed aoe driver"
                # and "running" from "running aoe driver"
                flds = key.split()
                if len(flds) > 1:
                    key = flds[0].strip()
                ret[key] = ls[1].strip()
        self._aoeversion = ret
        return ret

    def run_and_check(self, cmd, expectation=True):
        if True:
            raise NotImplementedError("implemented by the child class")
        return ReturnCode(False)


def _stat_device_match(shelf_lun, stat):
    """
    If shelf_lun is  set to "all", then return all device
    names.  If shelf_lun does not contain a '.', then return
    a list of all device names on the specified shelf.  If
    shelf_lun contains a '.', then return the device name
    only for the specified target, as a string.
    """
    devs = []
    shelf_lun = str(shelf_lun)
    hasdot = shelf_lun.find('.') != -1
    if hasdot:
        devs = ""
    for targ in stat:
        if hasdot:
            # specific target
            if stat[targ]['target'] == shelf_lun:
                devs = stat[targ]['path']
                break
        elif shelf_lun == 'all':
            # all targets on all shelves
            devs.append(stat[targ]['path'])
        else:
            # all targets on this shelf only
            shelf = str(AoEAddress(stat[targ]['target']).shelf)
            if shelf_lun == shelf:
                devs.append(stat[targ]['path'])
    logger.debug("_stat_device_match: %s" % str(devs))
    return devs


class LinuxSsh(Client, Initiator):
    """
    LinuxSsh
    --------
    A class for controlling a linux initiator using SSH/SFTP services directly.

    This object can be instantiated with a dictionary::

        lnx = {'user':'root', 'host: 'localhost','password':'passw0rd!'}
        cfg = Namespace({'lnx_host1': lnx})
        # the above simulates the config object
        my_linux = LinuxSsh(cfg.lnx_host1)
        my_linux.connect()

    """

    def __init__(self, *args, **kwargs):
        if isinstance(args[0], dict):  # this allows instantiation with a config dict item
            for k, v in args[0].items():
                if k == 'mount':
                    setattr(self, 'mount_point', v)
                setattr(self, k, v)
        else:
            self.user = args[0]
            self.hostname = args[1]
            self.password = args[2]
            self.mount_point = kwargs.get('mount')

        self.ethdrv = Ethdrv(self.get_ethdrv)
        super(LinuxSsh, self).__init__(self.hostname, self.user, self.password)
        self.os = 'linux'
        self.nsdir = '/proc/ethdrv'

        if not hasattr(self, 'coraid_module'):
            self.coraid_module = "ethdrv"

        Initiator.__init__(self, self.coraid_module)

    def get_ethdrv(self, fname):
        """
        Required function for Ethdrv class
        """
        return self.run_and_check('cat /proc/ethdrv/%s' % fname)

    def run_and_check(self, cmd, expectation=True, force=False, timeout=None, bufsize=-1):
        """
        Run a command check the result.  If the caller cares about failure, indicated by
        not setting expectation to False, and the command fails we raise an exception.
        """
        logger.info("%s called", cmd)
        if force:
            raise NotImplementedError
        else:
            result = self.run(cmd, timeout=timeout, bufsize=bufsize)
            if result is not None:
                result.message = result.message.rstrip()

        if not result and expectation:
            logger.critical(result.message)
            raise InitiatorError(result.message)
        else:
            return result

    def put(self, localpath, remotepath=None):
        """

        :param localpath:
        :param remotepath: If None use pwd and basename
        :return:
        """
        if not remotepath:
            remotepath = os.path.basename(localpath)
        sftpsession = self.open_sftp()

        return sftpsession.put(localpath, remotepath)

    def get(self, remotepath, localpath=None):
        """
        :param remotepath:
        :param localpath: If None use pwd and basename
        :return:
        """
        if not localpath:
            localpath = "%s/%s" % (os.getcwd(), os.path.basename(remotepath))
        sftpsession = self.open_sftp()

        return sftpsession.get(remotepath, localpath)

    @property
    def hba_ports(self):
        """
        Returns a dictionary of the HBA's ports file contents::

            {'0': {'link': {'max': '1000', 'speed': '0'},
                'mac': '00100401103c',
                'port': '0',
                'type': 'EHBA-2-E-RJ45'},
            '1': {'link': {'max': '1000', 'speed': '1000'},
                'mac': '00100401103d',
                'port': '1',
                'type': 'EHBA-2-E-RJ45'}
            }

        """
        ports = dict()
        r = self.run_and_check('ethdrv-ports')
        if not r:
            return ports
        lines = r.message.splitlines()
        for l in lines:  # We skip the header at the top and the prompt at the bottom.
            if not l:
                continue
            flds = l.split()
            p = flds[0]
            ports[p] = dict()
            ports[p]['port'] = p
            ports[p]['type'] = flds[1]
            ports[p]['mac'] = flds[2]
            ports[p]['link'] = dict()
            speed, maxi = flds[3].split('/')
            ports[p]['link']['speed'] = speed
            ports[p]['link']['max'] = maxi
        return ports

    def list_dir(self, absolute_path):
        """
        If a directory, returns a ReturnCode with status=True and a list of directory contents
        If not, status=False, message=list()
        """
        dirlist = list()
        try:
            out = self.run_and_check("ls %s" % absolute_path)
        except InitiatorError:
            return ReturnCode(False, list())

        for file in out.message.splitlines():
            dirlist.append(file)
        return ReturnCode(True, dirlist)

    def lun_exists(self, lun, flush=True):
        """
        If found returns a ReturnCode with status=True and lun's aoestat dict::

            {'device': 'sd379', 'port': ['1'], 'target': '91.1', 'size': '2000.398GB'}

        when not, False and "<lun> not found" in message.
        """
        if flush:
            self.aoeflush()
        n = self.aoestat
        if lun in n:
            return ReturnCode(True, n[lun])
        return ReturnCode(False, '%s not found' % lun)

    def df(self, mount_point):
        """
        Returns the amount of disk space available a given file system containing each
        file name argument.  Disk space is returned in human readable format (--human-readable).
        """

        if not os.path.exists(mount_point):
            raise Exception("Mount point %s does not exist" % mount_point)

        cmd = "df -h %s" % mount_point
        ret = self.run_and_check(cmd)
        output = str(ret)
        logger.debug(output)
        header = re.compile(r"Filesystem[ \t]*Size[ \t]*Used[ \t]*Avail[ \t]*Use%[ \t]*Mounted on")
        lines = output.splitlines()
        info = dict()
        if not header.search(lines[0]):
            logger.critical("df: output not recognized")
        else:

            if len(lines) > 3:
                line = " ".join(lines[1:len(lines)])
            else:
                line = lines[1]
            [filesystem, size, used, avail, percent_used, mounted_on] = line.split()
            percent_used = percent_used.replace('%', '')
            info['filesystem'] = filesystem
            info['size'] = size
            info['used'] = used
            info['avail'] = avail
            info['percent_used'] = int(percent_used)
            info['mounted_on'] = mounted_on
        return info

    @property
    def rdsk(self):
        """
        return a list of all the raw block devices.  (Solaris compatibility).

        :rtype: list of str
        """
        return self.run_and_check(r"ls /dev/sd* | grep -e '\/dev\/sd.*[^0-9]$'").message.splitlines()

    @property
    def uname(self):
        return self.run_and_check('uname').message.strip()

    @property
    def distro(self):
        """
        check what distribrution we are dealing with
        """
        rel = self.run_and_check("cat /etc/redhat-release")
        if "red hat" in rel.message.lower():
            return "redhat"
        elif "centos" in rel.message.lower():
            return "centos"

    def targ2sd(self, targ):
        """
        Return the symbolic sd device name for the AoE Target.
        """
        if not targ:
            return targ
        ret = self.aoestat.get(targ)
        if ret:
            ret = ret['file']
        return ret

    @staticmethod
    def sd2dev(sdname, path='/dev/'):
        """
        Return disk device or character device for a given sd name.
        This is included for script cross compatibility with Solaris

        :param sdname: the sd device name e.g. sd35
        :return: dev path
        """

        return "%s%s" % (sdname, path)

    def sd2targ(self, sd):
        """
        Return the aoe target associated with an sd device. If none found None is returned.
        """
        ret = self.aoestat
        for target, v in ret.iteritems():
            if v.get('file') == sd:
                return AoEAddress(target)
        return None

    def targ2dev(self, targ):
        """
        Return the device path for an aoe Target.

        :param targ: the aoe device e.g. '2.1' or as AoEAddress type
        :return:
        """
        if self.coraid_module == "aoe":
            return '/dev/etherd/e' + str(targ)
        else:
            return '/dev/ethdrv/e' + str(targ)

    @property
    def packages(self):

        ret = self.run_and_check('rpm -qa --qf "%{NAME}\n"')

        return ret.message.splitlines()

    def exists(self, path):
        """
        Return True if given path exists on the current remote host.
        """
        cmd = 'test -e %s' % _expand_path(path)

        return self.run_and_check(cmd, expectation=False)

    def contains(self, filename, text, exact=False, escape=True):
        """
        Return True if ``filename`` contains ``text`` (which may be a regex.)

        By default, this function will consider a partial line match (i.e. where
        ``text`` only makes up part of the line it's on). Specify ``exact=True`` to
        change this behavior so that only a line containing exactly ``text``
        results in a True return value.

        This function leverages ``egrep`` on the remote end (so it may not follow
        Python regular expression syntax perfectly), and skips ``env.shell``
        wrapper by default.

        If ``use_sudo`` is True, will use `sudo` instead of `run`.

        If ``escape`` is False, no extra regular expression related escaping is
        performed (this includes overriding ``exact`` so that no ``^``/``$`` is
        added.)

        """
        if escape:
            text = _escape_for_regex(text)
            if exact:
                text = "^%s$" % text
        egrep_cmd = 'egrep "%s" %s' % (text, _expand_path(filename))
        return self.run_and_check(egrep_cmd, expectation=False)

    def append(self, filename, text, partial=False, escape=True):
        """
        Append string (or list of strings) ``text`` to ``filename``.

        When a list is given, each string inside is handled independently (but in
        the order given.)

        If ``text`` is already found in ``filename``, the append is not run, and
        None is returned immediately. Otherwise, the given text is appended to the
        end of the given ``filename`` via e.g. ``echo '$text' >> $filename``.

        The test for whether ``text`` already exists defaults to a full line match,
        e.g. ``^<text>$``. You may override this and force partial searching
        (e.g. ``^<text>``) by specifying ``partial=True``.

        Because ``text`` is single-quoted, single quotes will be transparently
        backslash-escaped. This can be disabled with ``escape=False``.


        """
        # Normalize non-list input to be a list
        if isinstance(text, basestring):
            text = [text]
        for line in text:
            regex = '^' + _escape_for_regex(line) + ('' if partial else '$')
            if self.exists(filename) and line and self.contains(filename, regex, escape=False):
                continue
            line = line.replace("'", r"'\\''") if escape else line
            return self.run_and_check("echo '%s' >> %s" % (line, _expand_path(filename)))

    def appendUUID(self, UUID, mnt_path, fstype):
        """
         Append with UUID a device entry at the end of /etc/fstab file

        :param UUID: the UUID of a device
        :type UUID: str
        :param mnt_path: where it should be mounted
        :type mnt_path: str
        :param fstype: what kind of filesystem is on thta device
        :type fstype: str
        :return: success status
        :rtype: bool
        """
        return self.append("/etc/fstab", "%s  %s  %s  defaults 1 2\n" % (UUID, mnt_path, fstype))

    def e2fsck(self, device_path):
        """
        Run e2fsck -f on a device.
        """
        return self.run_and_check("e2fsck -f %s" % device_path)

    def findmount(self, blocks):
        """
        Findmount looks through mtab and returns
        a list of all matching mounts.
        """
        cmd = 'cat /etc/mtab'
        ret = self.run_and_check(cmd)
        mtab = str(ret)
        mtabl = mtab.split('\n')
        mnts = []
        if type(blocks) == str:
            blocks = [blocks]
        for b in blocks:
            for m in mtabl:
                f = m.split()
                if len(f) > 1 and f[0] == b:
                    mnts.append(f[1])
        return mnts

    def fsck(self, device_path, repair=False):
        """
        Check and optionally repair a file system.
        """
        if repair:
            cmd = "fsck %s" % device_path
        else:
            cmd = "fsck -n %s" % device_path
        return self.run_and_check(cmd)

    def get_device_size(self, device):
        """
        Returns ReturnCode object

        call linux's 'blockdev' cmd-line tool
        to get the device size in bytes.
        """
        cmd = "blockdev --getsize64 %s" % device
        ret = self.run_and_check(cmd, expectation=False)
        if ret:
            output = str(ret)
            logger.debug(output)
            output = int(output)
            return output
        else:
            return None

    @property
    def ipaddr(self):
        """
        :return: the ip address of the interface we are connected to
        :rtype: str
        """

        return self.get_transport().sock.getpeername()[0]

    def get_ipv4_addr(self, eth=0):
        """
        The Linux way to get an ether's IP address.

        Given this, return the IPv4 address '10.220.70.4':

        [root@pickles smokemonster]# ifconfig
        eth0      Link encap:Ethernet  HWaddr 00:25:90:0A:3C:04
                  inet addr:10.220.70.4  Bcast:10.220.255.255  Mask:255.255.0.0
        """
        r = self.run("ifconfig eth%s" % str(eth))
        if not r:
            return r
        triplet = "[0-9]{1,3}"
        regex = "inet addr:(%s.%s.%s.%s)" % (triplet, triplet, triplet, triplet)
        m = re.search(regex, r.message)
        if m:
            ipv4 = m.group(1)
            return ReturnCode(True, ipv4)
        else:
            return ReturnCode(False, "no IPv4 address found: %s" % r.message)

    def get_mac_addr(self, eth=0):
        """
        The Linux way to get a ether mac addr.
        """
        r = self.run("ifconfig eth%s" % str(eth))
        if not r:
            return r
        h2 = "[0-9a-fA-F]{2}"
        regex = "HWaddr[ \t]+(%s):(%s):(%s):(%s):(%s):(%s)" % (h2, h2, h2, h2, h2, h2)
        m = re.search(regex, r.message)
        if m:
            mac = "%s%s%s%s%s%s" % (m.group(1), m.group(2), m.group(3),
                                    m.group(4), m.group(5), m.group(6))
            return ReturnCode(True, mac)
        else:
            return ReturnCode(False, "no mac addr found: %s" % r.message)

    def get_pids(self, name):
        """
        Getpids returns a list of process IDs matching name.
        """
        r = self.run_and_check("ps -C %s -o pid=" % name)
        if not r:
            return []
        return r.message.split()

    def get_UUID(self, dev_name):
        """
        return UUID for device name

        :param dev_name: device file name under /dev
        :type dev_name: str
        :return: the UUID for device
        :rtype: str
        """
        cmd = 'blkid /dev/%s' % dev_name
        logger.debug("Running command %s", cmd)
        blkid_result = self.run_and_check(cmd, expectation=False)

        if not blkid_result:
            return None
        if blkid_result.find("UUID=") > -1:
            logger.debug(blkid_result)
            blkentry = r'UUID="(?P<uuid>[a-f,0-9,\-]*?)"\s+TYPE="(?P<type>.*?)"'
            m = re.search(blkentry, blkid_result.message)

            if m:
                UUID = m.group('uuid')
                logger.debug("UUID for device name %s is %s", dev_name, UUID)
                return UUID
            else:
                logger.debug("UUID not found for device name %s ", dev_name)
                return False

    def install_rpm(self, package_path, timeout=30, expectation=True):
        """
        This function will install the rpm

        :rtype: boolean
        """
        cmd = "rpm -i %s" % package_path
        ret = self.run_and_check(cmd, timeout=timeout, expectation=expectation)
        if ret.find("Failed dependencies") > -1:
            logger.debug(ret)
            return False
        else:
            return ret

    def is_package_installed(self, package_name):
        """
        This function will find if the package is installed on the host machine
        and return the list of packages installed
        Argument : package_name (eg : 'ethdrv')
        Return : True,installed package list, or
                 False, []

        """
        return package_name in self.packages

    def lsmod(self):
        """
        return loaded modules

        :rtype: list
        """
        cmd = 'lsmod'
        modules = list()
        ret = self.run_and_check(cmd).message.splitlines()
        for module in ret:
            modules.append(module.split()[0])

        return modules

    @property
    def memory(self):
        """
        Returns the total memory of the machine as an integer in KB.
        """
        sz = 0
        cmd = 'cat /proc/meminfo'
        ret = self.run_and_check(cmd)
        o = ret.message
        m = re.search(r"MemTotal: +([0-9]+) ", o)
        if m:
            sz = int(m.group(1))
        else:
            logger.error("memory: %s", o)
        return sz

    def mkfs(self, device, fstype="ext3", force=False, expectation=True):
        """
        Create a file system on device.  By default ext3 is used.
        """
        fflag = ""
        if force:
            if fstype == "xfs":
                fflag = "-f "
            elif fstype == "ext3" or fstype == "ext4":
                fflag = "-F "
        cmd = "mkfs -t %s %s%s 2>&1" % (fstype, fflag, device)
        ret = self.run_and_check(cmd, expectation=expectation, timeout=None)
        return ret

    def mount(self, source, fstype="ext3", target=None, max_attempts=1, expectation=True):
        """
        Mounts a file system of a given type on a directory.
        """
        if self.mount_point:
            base = self.mount_point
        else:
            base = "/mnt"
        if target is None:
            temp_share_name = re.sub(r"\W", "_", source)
            target = os.path.join(base, temp_share_name)
            ret = self.mkdir(target)
            if not ret:
                raise InitiatorError(ret.message)
                # if not os.path.exists(target):
                #                os.makedirs(target)
        mounted = False
        nchecks = 0
        cmd = "mount -t %s %s %s" % (fstype, source, target)
        src_split = source.split('/')
        lvsource = '/dev/mapper/%s-%s' % (src_split[2], src_split[3])
        logger.info(cmd)
        while not mounted:
            nchecks += 1
            r = self.run_and_check('mount')
            current_mounts = str(r)
            self.run_and_check('mount')
            pattern = "^%s on %s" % (source, target)
            lvpattern = "^%s on %s" % (lvsource, target)
            if re.search(pattern, current_mounts, re.MULTILINE) or re.search(lvpattern, current_mounts, re.MULTILINE):
                mounted = True
            else:
                r = self.run_and_check(cmd)
                if nchecks == max_attempts:
                    if not r:
                        if expectation:
                            raise Exception(r.message)
                        else:
                            return None
                if nchecks > 1:
                    time.sleep(2)
        return target

    def load_module(self, module):
        """
        This function will load the module using 'modprobe' linux command

        :rtype: ReturnCode
        """
        cmd = 'modprobe %s' % module
        return self.run_and_check(cmd)

    @staticmethod
    def removeUUID(mnt_path):
        """
        This function remove UUID from /etc/fstab file

        :type: ReturnCode

        TODO:  use sed method
        """
        # self.get('/etc/fstab', '.')
        # logger.debug("/etc/fstab File is copied to current directory")
        # fh_r = open('fstab', 'r')
        # lines = fh_r.readlines()
        # output = []
        # for line in lines:
        # if not mnt_path in line:
        # output.append(line)
        # fh_r.close()
        #
        # fh_w = open('fstab', 'w')
        # fh_w.writelines(output)
        # fh_w.close()
        # self.put('fstab', '/etc')
        # logger.debug("UUID entry for mount path %s is removed from /etc/fstab file", mnt_path)
        # os.system('rm fstab')
        return False

    def sync(self):
        """
        Force changed blocks to disk, and update the super block.
        """
        return self.run_and_check('sync')

    def umount(self, pathname):
        """
        Unmount a file system

        :param pathname: directory to unmount
        :type pathname: str
        :rtype: ReturnCode
        """
        logger.debug("umount %s", pathname)
        mounted = True
        number_of_checks = 1
        ret = ReturnCode('Broken while loop in unmount')
        while mounted:
            number_of_checks += 1
            ret = self.run_and_check('mount')
            output = ret.message
            pattern = " on %s " % pathname
            if re.search(pattern, output, re.MULTILINE):
                ret = self.run_and_check('umount %s' % pathname)
                time.sleep(2)
            else:
                mounted = False
                if number_of_checks > 1:
                    ret = ReturnCode("After %s checks %s not found" % (number_of_checks, pathname))
                    time.sleep(5)

        if self.exists(pathname):
            ret = self.rmdir(pathname)
        return ret

    def uninstall_package(self, package, timeout=30):
        """
        This function will uninstall the package and unload the module
        Return: True for successful
                False for Failure
        """
        cmd = 'rpm -ev %s' % package
        return self.run_and_check(cmd, timeout=timeout)

    def unload_module(self, module):
        """
        This function will unload the module using 'rmmod' linux command
        Return : True or False
        """
        return self.run_and_check("rmmod %s" % module)

    def untar_package(self, src_directory, dest_directory='.'):
        """
        Untar the src_directory\*.tar.gz in dest_directory
        Return : True or False
        """
        cmd = "tar -xvzf %s -C %s" % (src_directory, dest_directory)
        return self.run_and_check(cmd)

    @wait_until(sleeptime=5, timeout=60 * 60)
    def wait_shutdown(self):
        return self.is_down()

    def is_down(self):
        try:
            self.run_and_check('echo waiting for ssh to shutdown', timeout=5)
        except (OSError, EOFError, InitiatorError):
            logger.info('ssh appears to have shutdown')
            return ReturnCode(True, "host appears down")
        return ReturnCode(False)

    def reboot(self, wait=True):
        ret = self.run_and_check('reboot', False)
        if wait:
            ret = self.wait_shutdown()
        self.close()
        return ret

    def sed(self, filename, before, after, limit='', backup='.bak', flags=''):
        """
        Run a search-and-replace on ``filename`` with given regex patterns.

        Equivalent to ``sed -i<backup> -r -e "/<limit>/ s/<before>/<after>/<flags>g"
        <filename>``. Setting ``backup`` to an empty string will, disable backup
        file creation.

        For convenience, ``before`` and ``after`` will automatically escape forward
        slashes, single quotes and parentheses for you, so you don't need to
        specify e.g.  ``http:\/\/foo\.com``, instead just using ``http://foo\.com``
        is fine.

        If ``use_sudo`` is True, will use `sudo` instead of `run`.

        The ``shell`` argument will be eventually passed to `run`/`sudo`. It
        defaults to False in order to avoid problems with many nested levels of
        quotes and backslashes. However, setting it to True may help when using
        ``~fabric.operations.cd`` to wrap explicit or implicit ``sudo`` calls.
        (``cd`` by it's nature is a shell built-in, not a standalone command, so it
        should be called within a shell.)

        Other options may be specified with sed-compatible regex flags -- for
        example, to make the search and replace case insensitive, specify
        ``flags="i"``. The ``g`` flag is always specified regardless, so you do not
        need to remember to include it when overriding this parameter.

        """
        # Characters to be escaped in both
        for char in "/'":
            before = before.replace(char, r'\%s' % char)
            after = after.replace(char, r'\%s' % char)
        # Characters to be escaped in replacement only (they're useful in regexen
        # in the 'before' part)
        for char in "()":
            after = after.replace(char, r'\%s' % char)
        if limit:
            limit = r'/%s/ ' % limit

        context = {'script': r"'%ss/%s/%s/%sg'" % (limit, before, after, flags),
                   'filename': _expand_path(filename),
                   'backup': backup,
                   'extended_regex': '-E'}

        expr = r"sed -i%(backup)s %(extended_regex)s -e %(script)s %(filename)s"
        command = expr % context
        return self.run_and_check(command)

    def _uniqscsi(self, target):
        """
        Ensure that the ethdrv-stat dev files for target are unique. If there are many targets,
        populating dev tree with targets may bbe slow so many entries many initially appear under
        /dev/sda, or after version 5.2.2, many can be listed as 'init'.
        """
        stat = self.aoestat

        if target == 'all':
            i = 0
            self.aoeflush()
            while 1:
                wait = 0
                devs = []
                if 'init' in stat:
                    wait = 1
                else:
                    for targ in stat:
                        devs.append(stat[targ]['file'])
                if len(devs) != len(set(devs)):
                    wait = 1
                if wait == 0:
                    return stat
                i += 1
                if i % 10 == 0:
                    logger.debug("ethdrv-flush after %d waits", i)
                    self.aoeflush()
                time.sleep(1)
                stat = self.aoestat
        else:
            i = 0
            wait = 1
            while 1:
                targdev = ''
                devs = []
                for targ in stat:
                    if targ == target:
                        wait = 0
                        targdev = stat[targ]['file']
                        if stat[targ]['file'] == 'init':
                            wait = 1
                    else:
                        devs.append(stat[targ]['file'])
                if targdev in devs:
                    wait = 1
                if wait == 0:
                    break
                i += 1
                if i % 10 == 0:
                    logger.debug("ethdrv-flush after %d waits", i)
                    self.aoeflush()
                time.sleep(1)
                stat = self.aoestat

        return stat

    def target_is_available(self, target):
        """
        Check if a target is visible
        """
        if self.coraid_module == "aoe":
            self.aoediscover()
            stat = self.aoestat
        else:
            stat = self._uniqscsi(target)

        ret = ReturnCode(False)

        for targ in stat:
            if stat[targ]['target'] == target:
                ret.message = stat[targ]
                ret.status = True

        return ret

    @wait_until()
    def wait_target_is_available(self, target):
        """
        waits for the target be visible
        """
        ret = self.target_is_available(target)
        return ret

    def wipe_partition_table(self, path=None, lun=None, count=1):
        """
        If you are using a whole disk device for your physical volume, the disk must
        have no partition table.

        For DOS disk partitions, the partition id should be set to 0x8e using the fdisk
            or cfdisk command or an equivalent.
        For whole disk devices only the partition table must be erased, which will
            effectively destroy all data on that disk.
        You can remove an existing partition table by zeroing the first sector with
        the following command::

            # dd if=/dev/zero of=PhysicalVolume bs=512 count=1

        """
        if not isinstance(path, str) and not isinstance(lun, str):
            return ReturnCode(False, "Incompatible parameters: %s %s" % (path, lun))

        if path is None:
            path = self.aoestat.get(lun)['path']
            if path is None:
                return ReturnCode(False, "Couldn't find path to target %s" % lun)
        cmd = 'dd if=/dev/zero of=%s bs=512 count=%s' % (path, count)
        return self.run_and_check(cmd)

    def __info(self, infotype=None, name=None):
        if infotype not in ('pv', 'vg', 'lv'):
            logger.error("No or incorrect info type specified %s", infotype)
            return ReturnCode(False, "No or incorrect info type specified %s" % infotype)

        if name:
            cmd = '%ss --nameprefixes %s' % (infotype, name)
        else:
            cmd = '%ss --nameprefixes' % infotype

        vols = self.run_and_check(cmd)
        info = dict()
        ss = vols.message.splitlines()
        errors = list()
        unknowns = 0
        for s in ss:
            if 'error' in s or 'uuid' in s:
                errors.append(s)
                continue
            elif '_' in s:
                vals = list()
                col = s.strip()
                col = col.replace("'0 '", "'0'")
                col = col.split()
                if 'unknown device' in s:
                    key = "'unknown%s'" % unknowns
                    unknowns += 1
                    col.pop(0)
                    col.pop(0)
                else:
                    key = col.pop(0)
                for pair in col:
                    k, v = pair.split('=')
                    vals.append(v[1:v.rindex("'")])
                key = key[(key.index("'") + 1):key.rindex("'")]
                info[key] = dict(zip(header, vals))
            else:
                header = s
                header = header.strip().split()
                header.pop(0)
        if errors:
            info['errors'] = errors
        return info

    def pvinfo(self, pvname=None):
        return self.__info(infotype='pv', name=pvname)

    def pvcreate(self, path=None, lun=None):
        # One of these variables must be defined
        if not isinstance(path, str) and not isinstance(lun, str):
            return ReturnCode(False, "Incompatible parameters: %s %s" % (path, lun))

        if path is None:
            path = self.aoestat.get(lun)['path']
            if path is None:
                return ReturnCode(False, "Couldn't find path to target %s" % lun)
        cmd = 'pvcreate -f %s' % path
        return self.run_and_check(cmd)

    def pvremove(self, path=None, lun=None):
        if not isinstance(path, str) and not isinstance(lun, str):
            return ReturnCode(False, "Incompatible parameters: %s %s" % (path, lun))

        if path is None:
            path = self.aoestat.get(lun)['path']
            if path is None:
                return ReturnCode(False, "Couldn't find path to target %s" % lun)
        cmd = "pvremove -f %s" % path
        return self.run_and_check(cmd)

    def vginfo(self, vgname=None):
        return self.__info(infotype='vg', name=vgname)

    def vgcreate(self, vgname, devs=None, path=None):
        if not isinstance(devs, list) and not isinstance(path, str):
            return ReturnCode(False, "Incompatible parameters: %s %s" % (devs, path))

        cmd = 'vgcreate -f %s ' % vgname
        if type(path) is list:
            path = ' '.join(path)
        if not path:
            path = str()
            stat = self.aoestat
            # list of devices
            for d in devs:
                path += " " + stat.get(d)['path']
                if path is None:
                    logger.error("No path for lun %s" % d)
                    continue
        cmd += '%s ' % path
        return self.run_and_check(cmd)

    def vgmerge(self, vg_orig, vg_add):
        cmd = 'vgmerge %s %s' % (vg_orig, vg_add)
        return self.run_and_check(cmd)

    def vgremove(self, vgname):
        cmd = 'vgremove -f %s ' % vgname
        return self.run_and_check(cmd)

    def vgreduce(self, vgname, removemissing=False):
        cmd = 'vgreduce '
        if removemissing:
            cmd += '--removemissing '
        cmd += vgname
        return self.run_and_check(cmd)

    def lvinfo(self, vgname=None):
        return self.__info(infotype='lv', name=vgname)

    def lvconvert(self, vgname, repair=False):
        cmd = 'lvconvert '
        if repair:
            cmd += '-y --repair '

        cmd += vgname
        return self.run_and_check(cmd)

    def lvcreate(self, vgname, lvname, lv_size='100%FREE', stripe_sz=None, mirrors=0):
        cmd = 'lvcreate '
        if "FREE" in lv_size:
            cmd += '-l %s ' % lv_size
        else:
            cmd += '-L %s ' % lv_size

        if stripe_sz:
            vgs = self.vginfo(vgname=vgname)
            npv = vgs[vgname]['#PV']
            cmd += '-i %s -I %s ' % (npv, stripe_sz)

        if mirrors:
            cmd += '-m %s ' % mirrors

        cmd += '-n %s %s' % (lvname, vgname)
        return self.run_and_check(cmd)

    def lvextend(self, lvpath, size=None, percentage='+100%FREE'):
        if size:
            cmd = 'lvextend -L %s %s' % (size, lvpath)
        else:
            cmd = 'lvextend -l %s %s' % (percentage, lvpath)
        return self.run_and_check(cmd)

    def lvremove(self, lvpath):
        cmd = 'lvremove -f %s' % lvpath
        return self.run_and_check(cmd)

    def resize2fs(self, lvpath):
        cmd = 'resize2fs %s' % lvpath
        return self.run_and_check(cmd, timeout=1200)

    # Ctl and its dependencies
    # Todo: Breakout ctl into its own, nonblocking object

    def ctl(self, rw, key, skip, shelf_lun, total=None):
        """
        Ctl first verifies that the target exists, then reads
        from/writes to it using 'ctl'.
        """
        shelf_lun = str(shelf_lun)
        self.verifytarget(shelf_lun)
        b = self.get_block_devices(shelf_lun)
        cmd = "ctl -%s -k %s -s %s" % (rw, key, skip)
        if total:
            cmd += " -T %s" % total
        cmd += " %s" % b
        return self.run(cmd)

    def __uniqscsiall(self):
        """
        Ensure that the ethdrv-stat dev files are unique.  Especially
        if there are many targets, loading targets may take a while,
        so many entries appear under /dev/sda, or after version
        5.2.2, many can be listed as 'init'.
        """
        i = 0
        self.aoeflush()
        while 1:
            wait = 0
            stat = self.aoestat
            devs = []
            if 'init' in stat:
                wait = 1
            else:
                for targ in stat:
                    devs.append(stat[targ]['file'])
            if len(devs) != len(set(devs)):
                wait = 1
            if wait == 0:
                return stat
            i += 1
            if i % 10 == 0:
                logger.debug("ethdrv-flush after %d waits" % i)
                self.aoeflush()
            time.sleep(1)

    def __uniqscsi(self, target):
        """
        Ensure that the ethdrv-stat dev files for target are unique.
        Especially if there are many targets, loading targets may
        take a while, so many entries appear under /dev/sda, or after
        version 5.2.2, many can be listed as 'init'.
        """
        if target == 'all':
            return self.__uniqscsiall()
        i = 0
        wait = 1
        while 1:
            targdev = ''
            stat = self.aoestat
            devs = []
            for targ in stat:
                if targ == target:
                    wait = 0
                    targdev = stat[targ]['file']
                    if stat[targ]['file'] == 'init':
                        wait = 1
                else:
                    devs.append(stat[targ]['file'])
            if targdev in devs:
                wait = 1
            if wait == 0:
                return stat
            i += 1
            if i % 10 == 0:
                logger.debug("ethdrv-flush after %d waits" % i)
                self.aoeflush()
            time.sleep(1)

    @wait_until(timeout=300, sleeptime=5)
    def verifytarget(self, target):
        """
        Verifytarget waits for the target to show up
        in the aoe-stat or ethdrv-stat output, whichever
        is defined in self.coraid_module variable.
        """
        logger.debug("verifying target: %s ..." % target)
        self.aoediscover()
        target = str(target)
        modul = self.coraid_module
        if modul == 'aoe':
            stat = self.aoestat
        else:
            stat = self.__uniqscsi(target)
        for targ in stat:
            if stat[targ]['target'] == target and stat[targ]['ifs'][0] != "N/A":
                return stat[targ]

    def get_block_devices(self, address):
        """
        return a list of all /dev/ names for a specific shelf.lun, or
        a list of block files for all targets on a shelf, or
        if address=="all", all targets on all shelves.
        """
        # should this be an iterator that yields devices as they appear?

        if self.coraid_module == "ethdrv":
            ret = self._shelf2scsi(address)
        else:
            ret = self._shelf2etherd(address)
        retls = list()
        if type(ret) == str:
            retls = [ret]
        elif type(ret) == list:
            retls = ret
            # give each device 5 secs to mount after seeing it in aoestat
        for r in retls:
            i = 0
            while not os.path.exists(r) and i < 5:
                i += 1
                time.sleep(1)
        return ret

    def _shelf2etherd(self, shelf_lun):
        """
        Return where in the namespace linux has mounted AoE addressed
        targets in the form of:

            /dev/etherd/e01.5
        """
        stat = self.aoestat
        return _stat_device_match(shelf_lun, stat)

    def _shelf2scsi(self, shelf_lun):
        """
        Return a scsi device node for the given AoE Addressed LUN.

        If 'shelf_lun' is 'all', then return a list of all device
        names.  If 'shelf_lun' does not contain a '.', then return
        a list of all device names on the specified shelf.  If
        'shelf_lun' contains a '.', then return the device name
        only for the specified target, as a string.  Returns a path
        with the form: /dev/sd[a-zA-Z]+.
        """
        stat = self.__uniqscsi(shelf_lun)
        return _stat_device_match(shelf_lun, stat)
