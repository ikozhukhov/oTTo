# !usr/bin/env python
"""
initiators
----------

These are classes for interacting with Solaris hosts.

Basic Usage::

        from otto.initiators.solaris import SolarisSsh

        s = SolarisSsh(uname, host, passwd, prompt=None)
        s.connect()
        logger.info(s.release)
        s.disconnect()

"""

import re
import logging
import time
import os
from collections import defaultdict

from otto.lib.otypes import AoEAddress
from otto.utils import now
from otto.lib.otypes import InitiatorError, ReturnCode, Namespace
from otto.lib.pexpect import TIMEOUT
from otto.initiators.ethdrv import Ethdrv
from otto.connections.ssh import Client
from otto.lib.contextmanagers import ignored
from otto.lib.decorators import wait_until

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.initiators')
logger.addHandler(logging.NullHandler())


class Initiator(object):
    def __init__(self, coraid_module):
        self.coraid_module = coraid_module
        self._aoeversion = None

    def aoediscover(self):
        """
        Call the driver's discover command.  Returns ReturnCode object

        """
        cmd = 'echo 11 discover > /dev/ethdrv/ctl'
        return self.run_and_check(cmd)

    def aoeflush(self, aflag=True):
        """
        Call the driver's flush command. Return a ReturnCode object.
        """
        return self.run_and_check('ethdrvadm flush %s' % ('', '-a')[aflag])

    @property
    def aoestat(self):
        """
        Returns a dictionary of ethdrvadm list-devices -a in the following format::

                {'183.91': {'claim': None, 'target': '183.91', 'ifs': [1], 'iounit': None, 'state': None,
                            'file': 'sd39', 'device': 'sd39', 'path': None, 'port': [1], 'size': '8.000GB',
                            'paths': defaultdict(<function <lambda> at 0x10e432398>, {1: {'port': 1,
                                                                                        'address': ['002590c23e8a']}}),
                            'targpath': defaultdict(<function <lambda> at 0x10e432398>, {1: {'port': 1,
                                                                                        'address': ['002590c23e8a']}}),
        If port is N/A, port is an empty list and targpath/paths are empty dicts.
        """
        aoedd = defaultdict(
            lambda: {'file': None, 'device': None, 'path': None, 'port': None, 'ifs': None, 'target': None,
                     'size': None, 'iounit': None, 'state': None, 'claim': None, 'paths': None,
                     'targpath': defaultdict(lambda: {'address': None, 'port': None})})

        out = self.run_and_check('ethdrvadm list-devices -a')
        m = out.message.strip().splitlines()  # [header1, header2, lines, of, devices]
        if not m:
            return aoedd
        for l in m[2:]:
            if not l.startswith(' '):
                w = l.split()  # ['device', 'target', 'size', 'port']
                target = w[1]
                if w[3].find('N/A') is -1:
                    w[3] = [int(n) for n in w[3].split(',')]
                else:
                    w[3] = list()
                aoedd[target]['file'] = w[0]
                aoedd[target]['device'] = aoedd[target]['file']  # deprecated
                aoedd[target]['target'] = target
                aoedd[target]['size'] = w[2]
                aoedd[target]['port'] = w[3]
                aoedd[target]['ifs'] = aoedd[target]['port']  # deprecated
                aoedd[target] = Namespace(aoedd[target])
            else:
                w = l.split()  # ['port', 'addr0,addr1']
                w[0] = int(w[0])
                w[1] = w[1].split(',')
                aoedd[target]['targpath'][w[0]]['port'] = w[0]
                aoedd[target]['targpath'][w[0]]['address'] = w[1]
                aoedd[target]['targpath'][w[0]] = Namespace(aoedd[target]['targpath'][w[0]])
                aoedd[target]['paths'] = aoedd[target]['targpath']  # deprecated
        return aoedd

    @property
    def aoeversion(self):
        """
        Returns the driver version as a dict::

            {   'major': 6,
                'minor': 0,
                'revision' : 1,
                'release': 'R5'
                }

        """
        out = self.run_and_check('ethdrvadm version')
        l = out.message.splitlines()[0].split('.')
        l[2:3] = l[2].split('-')
        head = ['major', 'minor', 'revision', 'release']
        self._aoeversion = dict(zip(head, l))
        return self._aoeversion

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
        header = re.compile(r"Filesystem[ \t]*Size[ \t]*Used[ \t]*Available[ \t]*Capacity[ \t]*Mounted on")
        lines = output.splitlines()
        info = dict()
        if not header.search(lines[0]):
            print("output not recognized")
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

    def run_and_check(self, cmd, expectation=True):
        if True:
            raise NotImplemented
        return ReturnCode(False)


class ZFSSystem(object):
    """
    Class for operating on zpools.  This is used with multiple inheritance for creating Solaris objects.
    """

    def zpool_create(self, pname, targets, ptype='', num_devices=1, spares=None, timeout=600, expectation=True):
        """
        This method will create a zpool of name pname; working on support for multiple vdevs

        :param pname: zpool name
        :param targets: a list of SRX targets in the form shelf.lun
        :param ptype: a type for the zpool to create, like raidz2, mirror, etc
        :param num_devices: number of devices to use per vdev
        :param spares: is a list of targets that will be used as spare for the zpool
        :param expectation: If the caller cares about failure and the command fails we raise a generic exception.

        Returns a ReturnCode object
        """

        pools_list = self.zpool_list  # get the list of current existing pools
        addlist = targets

        if pools_list.get(pname):  # pool already exist and we need to add devices

            while addlist:
                r = self.zpool_add(pname, addlist[:num_devices], ptype, expectation)
                if r:
                    addlist = addlist[num_devices:]
                elif not expectation:
                    return ReturnCode(False, 'An error was detected while creating pool: %s' % r.message)

        else:  # pool does not exist, we need to create it first.
            r = self._zpool_create(pname, addlist[:num_devices], ptype, spares)
            if expectation and not r:
                raise InitiatorError("%s" % r)
            addlist = addlist[num_devices:]

            while addlist:
                r = self.zpool_add(pname, addlist[:num_devices], ptype, expectation)
                if r:
                    addlist = addlist[num_devices:]
                elif not expectation:
                    return ReturnCode(False, 'An error was detected while creating pool:\n %s' % r.message)
                else:
                    raise InitiatorError("%s" % r)

        start = now()
        deadline = start + timeout

        # This should probably become otto.lib.solaris.target_in_zpool
        waitlist = [self._target2device(target) for target in targets]
        while waitlist:
            for pool in self.zpool_status():
                if pool['pool'] == pname:
                    for target in waitlist:
                        if target in pool['config'].keys():
                            waitlist.remove(target)
            if now() > deadline:
                raise InitiatorError("missed deadline: %s timed out %ssec waiting on:\n%s" % (deadline,
                                                                                              now() - start,
                                                                                              waitlist))

        for pool in self.zpool_status():
            if pool['pool'] == pname:
                return ReturnCode(True, message=pool)

        return ReturnCode(False, "Couldn't find pool after creation")

    def _target2device(self, t):  # TODO: Replace with lib.solaris.targ2disk
        """
        This method will try to identify a device name for a particular target.
        """

        device = self.run_and_check('ls /dev/rdsk/c*t%sd%s*' % tuple(t.split('.')))
        rregex = re.match('/dev/rdsk/c(\d+)t%sd%s' % tuple(t.split('.')), device.message)
        if rregex:
            return 'c%s' % rregex.group(1) + 't%sd%s' % tuple(t.split('.'))
        else:
            return None

    def zpool_root(self):
        """
        Return the root zpool
        """
        result = self.run_and_check('zfs list')
        if result:
            for line in result.message.splitlines():
                if line:
                    ls = line.split()
                    if ls[4] == '/':
                        r = ls[0].split('/')
                        return r[0]
        logger.warn("Unable to find root pool: %s" % result.message)
        return ''

    def zpool_add(self, pname, targets, ptype='', expectation=True):
        """
        Take a list of targets (shelf.lun), find the device for them and add it to an existing zpool.
        """

        if type(targets) == list:
            devices = [self._target2device(target) for target in targets]  # target is in the form shelf.lun
            if len(devices) > 0:
                cmd = 'zpool add -f %s %s' % (pname, ptype)
                for d in devices:
                    if d:  # Skip devices not found, will be reported as None.
                        cmd += ' %s' % d
                return self.run_and_check(cmd, False)
            else:
                return ReturnCode(False, 'Devices were not found')
        elif type(targets) == str:
            device = self._target2device(targets)
            if device:
                cmd = 'zpool add -f %s %s %s' % (pname, ptype, device)
                return self.run_and_check(cmd, expectation)
            else:
                return ReturnCode(False, 'Device for target %s not found' % targets)

    def _zpool_create(self, pname, targets, ptype='', spares=None):
        """
        This gets called from abstraction zpool_create and does zpool creation.
        """

        if type(targets) == list:
            devices = [self._target2device(target) for target in targets]
            spare_devices = []
            if spares:
                spare_devices = [self._target2device(spare) for spare in spares]
            if len(devices) > 0:
                cmd = 'zpool create -f %s %s' % (pname, ptype)
                for d in devices:
                    if d:
                        cmd += ' %s' % d
                if spares:
                    cmd += ' spare'
                    for s in spare_devices:
                        if s:
                            cmd += ' %s' % s
                return self.run_and_check(cmd, False)
                # it could be a question being asked during the creation.
            else:
                return ReturnCode(False, 'Devices not found at initiator')

        elif type(targets) == str:
            device = self._target2device(targets)
            spare_devices = []
            if spares:
                spare_devices = [self._target2device(spare) for spare in spares]
            if device:
                cmd = 'zpool create -f %s %s %s' % (pname, ptype, device)
                if spares:
                    cmd += ' spare'
                    for s in spare_devices:
                        if s:
                            cmd += ' %s' % s
                return self.run_and_check(cmd, False)  # FIXME, same as above run command.
            else:
                return ReturnCode(False, 'Device for target %s not found' % targets)

    def zpool_destroy(self, pname, expectation=True, force=False):
        """
        Remove an existing zpool from the system.
        """

        if force:
            cmd = 'zpool destroy -f %s' % pname
        else:
            cmd = 'zpool destroy %s' % pname

        return self.run_and_check(cmd, expectation)

    @property
    def zpools(self):
        """
        Return a dictionary with some useful information taken from zpool list -H command::

            {'rpool': {'alloc': '6.72G',
                'altroot': '-',
                'cap': '53%',
                'dedup': '1.00x',
                'free': '5.90G',
                'health': 'ONLINE',
                'size': '12.6G'}}

        """

        cmd = 'zpool list -H'  # -H no headers and separate fields by a single tab instead of variable space.
        rdict = dict()
        columns = ['size', 'alloc', 'free', 'cap', 'dedup', 'health', 'altroot']  # zpool @ SunOS 5.11

        result = self.run_and_check(cmd)

        if result:
            for line in result.message.splitlines():
                if line:
                    ls = line.split()
                    if len(ls[1:]) == len(columns):
                        rdict[ls[0]] = dict(zip(columns, ls[1:]))
        return rdict

    @property
    def zpool_list(self):
        return self.zpools

    @property
    def zfs_list(self):
        """
        Return a dictionary from zfs list -H command::

            coraid@solaris-client-4:~$ zfs list -H
            rpool   4.69G   51.9G   4.61M   /rpool
            rpool/ROOT      2.62G   51.9G   31K     legacy
            rpool/ROOT/solaris      2.62G   51.9G   2.49G   /

        Returns: 

            {'rpool': {'avail': '51.9G',
                       'mountpoint': '/rpool',
                       'name': 'rpool',
                       'refer': '4.61M',
                       'used': '4.69G'},
             'rpool/ROOT': {'avail': '51.9G',
                            'mountpoint': 'legacy',
                            'name': 'rpool/ROOT',
                            'refer': '31K',
                            'used': '2.63G'},
             'rpool/ROOT/solaris': {'avail': '51.9G',
                                    'mountpoint': '/',
                                    'name': 'rpool/ROOT/solaris',
                                    'refer': '2.49G',
                                    'used': '2.63G'}}

        :rtype: dict
        """

        cmd = 'zfs list -H'  # -H Scripted mode. Do not display headers & separate fields
        # by a single tab instead of arbitrary space.
        rdict = dict()
        columns = ['name', 'used', 'avail', 'refer', 'mountpoint']  # zfs @ SunOS 5.11
        result = self.run_and_check(cmd)

        if result:
            for line in re.split('\r+\n', result.message.strip()):
                l = line.split()
                if len(l) == len(columns):
                    rdict[l[0]] = dict(zip(columns, l))
        return rdict

    @property
    def zfs_get_share(self):
        """
        a dictionary with some useful information taken from zfs get share command.

        :rtype: dict

        For example::

            coraid@solaris-client-4:~$ zfs get share
            NAME                                          PROPERTY  VALUE  SOURCE
            bpool3/users/cifs1                            share     name=cifs1,path=/bpool3/users/cifs1,prot=smb  local
            bpool3/users/cifs2                            share     name=cifs2,path=/bpool3/users/cifs2,prot=smb  local
            bpool3/users/nfs1                             share     name=nfs1,path=/bpool3/users/nfs1,prot=nfs  local
            bpool3/users/nfs2                             share     name=nfs2,path=/bpool3/users/nfs2,prot=nfs  local

        Returns::

            {'rpool': {'avail': '51.9G',
                       'mountpoint': '/rpool',
                       'name': 'rpool',
                       'refer': '4.61M',
                       'used': '4.69G'},
             'rpool/ROOT': {'avail': '51.9G',
                            'mountpoint': 'legacy',
                            'name': 'rpool/ROOT',
                            'refer': '31K',
                            'used': '2.63G'},
             'rpool/ROOT/solaris': {'avail': '51.9G',
                                    'mountpoint': '/',
                                    'name': 'rpool/ROOT/solaris',
                                    'refer': '2.49G',
                                    'used': '2.63G'}}

        :rtype: dict
        """

        cmd = 'zfs get share'
        rdict = dict()
        columns = ['name', 'property', 'value', 'source']  # zfs @ SunOS 5.11
        result = self.run_and_check(cmd)

        if result:
            for line in re.split('\r+\n', result.message.strip()):
                if line.startswith('NAME'):
                    continue
                l = line.split()
                if len(l) == len(columns):
                    rdict[l[0]] = dict(zip(columns, l))
        return rdict

    def zpool_wipe(self, expectation=True, force=False):
        """
        Return list of the zpool existing in the system and will try to remove them.
        """

        rpool = self.zpool_root()
        plist = self.zpool_list
        for pool in plist:
            if pool != rpool:
                self.zpool_destroy(pool, expectation, force)
                time.sleep(2)

    def zpool_import(self, pname):
        """
        Import the string pname
        """
        cmd = 'zpool import %s' % pname
        return self.run_and_check(cmd, False)

    def zpool_export(self, pname):
        """
        Export the string pname
        """
        cmd = 'zpool export %s' % pname
        return self.run_and_check(cmd, False)

    def zpool_status(self, expectation=True):
        pools = list()
        for pool in self.zpools.keys():
            cmd = "zpool status -v %s" % pool
            r = self.run_and_check(cmd)
            if r:
                pools.append(self.parse_status(r.message))
            elif expectation:
                raise InitiatorError("zpool statius failed:\n%s" % r.message)
        return pools

    @staticmethod
    def parse_status(status):
        pool = dict()
        pool['config'] = dict()
        try:
            summary, config = re.split("NAME\s+STATE\s+READ\s+WRITE\s+CKSUM", status)
        except ValueError:
            raise InitiatorError("Couldn't find regions in status output:\n%s" % status)
        for line in summary.strip().splitlines():

            k, v = line.split(':', 1)
            if k == 'config':
                continue
            pool[k.strip()] = v.strip()
        for line in config.strip().splitlines():
            if re.match(r"^\s", line):
                name, state, read, write, cksum = line.split()[:5]
                pool['config'][name] = {'name': name, 'state': state, 'read': read, 'write': write, 'cksum': cksum}
                detail = line.split()[5:]
                if detail:
                    pool['config']['detail'] = detail
        return pool

    def run_and_check(self, cmd, expectation=True):
        if True:
            raise NotImplemented
        return ReturnCode(False)


class RSFSystem(object):
    @property
    def rsfcli_status(self):
        """
        Returns a dictionary containing information about the rsf configuration::

            {'cluster': {'CRC': '0x5d68', 'name': 'bbox-cluster-1'},
            'errors': 0,
            'hearbeat': {'0': {'destination': 'street [10.175.50.76]',
                        'index': '0',
                        'last_index': '154376',
                        'last_timestamp': 'Thu Jan 23 11:01:33',
                        'source': 'wells',
                        'state': 'Up',
                        'type': 'net'},
                  '1': {'destination': 'street',
                        'disc': 'c0t5000C500572F501Fd0s0',
                        'index': '1',
                        'last_index': '154376',
                        'last_timestamp': 'Thu Jan 23 11:01:33',
                        'readsector': '518',
                        'source': 'wells',
                        'state': 'Up',
                        'type': 'disc',
                        'writesector': '512'}},
            'heartbeats': {'configured': '6', 'down': '0', 'up': '6'},
            'hosts': {'street': {'built_on': '12-Nov-2013-11:39',
                          'hostname': 'street',
                          'ip': '10.175.50.76',
                          'service_startups': 'enabled',
                          'state': 'UP'},
                    'wells': {'built_on': '12-Nov-2013-11:39',
                         'hostname': 'wells',
                         'ip': '10.175.50.74',
                         'service_startups': 'enabled',
                         'state': 'UP'}},
            'nodes': {'configured': '2', 'online': '2'},
            'service': {'0': {'description': 'Coraid bpool3 ZFS service',
                       'hosts': {'street': {'mode': 'automatic',
                                            'name': 'street',
                                            'state': 'unblocked',
                                            'status': 'stopped'},
                                 'wells': {'mode': 'automatic',
                                           'name': 'wells',
                                           'state': 'unblocked',
                                           'status': 'running'}},
                       'index': '0',
                       'ip': 'bbox-vip-1',
                       'name': 'bpool3'}},
            'services': {'running': '1', 'stopped': '1'}}

        """
        rdict = dict()
        cmd = 'rsfcli status'
        result = self.run_and_check(cmd)
        if result:
            if not re.search('rsfcli: command not found', result.message):
                rdict['hosts'] = dict()
                rdict['service'] = dict()
                rdict['services'] = dict()
                for line in result.message.splitlines():
                    if line:
                        # Contacted localhost in cluster "bbox-cluster-1", CRC = 0x5d68
                        m = re.search(
                            'Contacted\s+localhost\s+in\s+\cluster\s+\"(?P<name>[^\"]+)\",\s+CRC\s+=\s+(?P<CRC>[0-9a-fx]+)',
                            line)
                        if m:
                            rdict['cluster'] = m.groupdict()
                            continue
                        # Host wells (10.175.50.74) UP, service startups enabled,
                        m = re.search(
                            'Host\s+(?P<hostname>[\S]+)\s+\((?P<ip>[0-9\.]+)\)\s+(?P<state>[^,]+),\s+service\s+startups\s+(?P<service_startups>[^,]+),',
                            line)
                        if m:
                            currenthost = m.group('hostname')
                            rdict['hosts'][currenthost] = m.groupdict()
                            continue
                        # RSF-1 release 3.8.9, built on 12-Nov-2013-11:39 "3.8.9".
                        m = re.search(
                            '\s+RSF-1\s+release\s+(?P<release>[0-9\.]+),\s+built\s+on\s+(?P<built_on>[\S]+)\s+\"(?P=release)\"\.',
                            line)
                        if m:
                            for item in m.groupdict():
                                rdict['hosts'][currenthost][item] = m.groupdict()[item]
                            continue
                            # 2 nodes configured, 2 online.
                        m = re.search('(?P<configured>[0-9]+)\s+nodes\s+configured,\s+(?P<online>[0-9]+)\s+online.',
                                      line)
                        if m:
                            rdict['nodes'] = m.groupdict()
                            continue
                            # 0 Service bpool3, IP address bbox-vip-1, "Coraid bpool3 ZFS service":
                        m = re.search(
                            '(?P<index>[0-9]+)\s+Service\s+(?P<name>[^,]+),\s+IP\s+address\s+(?P<ip>[^,]+),\s+\"(?P<description>[^\"]+)\":',
                            line)
                        if m:
                            currentservice = m.groupdict()['index']
                            rdict['service'][currentservice] = m.groupdict()
                            rdict['service'][currentservice]['hosts'] = dict()
                            continue
                            # running automatic unblocked on wells
                        m = re.search(
                            '\s+(?P<status>[\S]+)\s+(?P<mode>[\S]+)\s+(?P<state>[\S]+)\s+on\s+(?P<name>[^$]+)', line)
                        if m:
                            rdict['service'][currentservice]['hosts'][m.group('name')] = m.groupdict()
                            continue
                            # 1 service configured
                        m = re.search('(?P<configured>[0-9]+)\s+services\s+configured', line)
                        if m:
                            rdict['services'] = m.groupdict()
                            continue
                            # 1 service instance stopped
                        m = re.search('\s+(?P<stopped>[0-9]+)\s+service\s+instance\s+stopped', line)
                        if m:
                            rdict['services']['stopped'] = m.groupdict()['stopped']
                            continue
                            # 1 service instance running
                        m = re.search('\s+(?P<running>[0-9]+)\s+service\s+instance\s+running', line)
                        if m:
                            rdict['services']['running'] = m.groupdict()['running']
                            continue
                            # Heartbeats:
                        m = re.search('Heartbeats:', line)
                        if m:
                            rdict['hearbeat'] = dict()
                            continue
                        # 0 net wells -> street [10.175.50.76]: Up, last heartbeat #154376 Thu Jan 23 11:01:33
                        m = re.search(
                            '(?P<index>[0-9]+)\s+(?P<type>[\S]+)\s+(?P<source>[\S]+)\s+\->\s+(?P<destination>[^:]+):\s+(?P<state>[^,]+),\s+last\s+heartbeat\s+#(?P<last_index>[0-9]+)\s+(?P<last_timestamp>[^$]+)',
                            line)
                        if m:
                            rdict['hearbeat'][m.groupdict()['index']] = m.groupdict()
                            continue
                        # 1 disc wells -> street (via /dev/rdsk/c0t5000C500572F501Fd0s0:512,/dev/rdsk/c0t5000C500572F501Fd0s0:518) [(20]: Up, last heartbeat #154376 Thu Jan 23 11:01:33
                        m = re.search(
                            '(?P<index>[0-9]+)\s+(?P<type>[\S]+)\s+(?P<source>[\S]+)\s+\->\s+(?P<destination>[\S]+)\s+\(via\s+(?:/dev/rdsk/(?P<disc>[^:]+):(?P<writesector>[0-9]+),/dev/rdsk/(?P=disc):(?P<readsector>[0-9]+))\)\s+\[\([0-9]+\]:\s+(?P<state>[^,]+),\s+last\s+heartbeat\s+#(?P<last_index>[0-9]+)\s+(?P<last_timestamp>[^$]+)',
                            line)
                        if m:
                            rdict['hearbeat'][m.groupdict()['index']] = m.groupdict()
                            continue
                        # 6 heartbeats configured, 6 up, 0 down
                        m = re.search(
                            '(?P<configured>[0-9]+)\s+heartbeats\s+configured,\s+(?P<up>[0-9]+)\s+up,\s+(?P<down>[0-9]+)\s+down',
                            line)
                        if m:
                            rdict['heartbeats'] = m.groupdict()
                            continue
                        # No errors detected
                        m = re.search('(?P<count>[\S]+)\s+errors\s+detected', line)
                        if m:
                            if m.groupdict()['count'] == 'No':
                                rdict['errors'] = 0
                            else:
                                rdict['errors'] = int(m.groupdict()['count'])

        return rdict

    @property
    def ipadm(self):
        """
        Returns a dictionary with the formatted output of 'ipadm'
        *** NOTE ***  'afi' is intended to represent 'address families::

            {   'lo0': {   'addr': '',
                           'afi': { 'v4' :   {   'addr': '127.0.0.1/8',
                                          'class-type': 'static',
                                          'name': 'lo0/v4',
                                          'state': 'ok',
                                          'under': ''},
                                    'v6' :   {   'addr': '::1/128',
                                          'class-type': 'static',
                                          'name': 'lo0/v6',
                                          'state': 'ok',
                                          'under': ''}},
                           'class-type': 'loopback',
                           'name': 'lo0',
                           'state': 'ok',
                           'under': ''}
            }

        """
        rdict = dict()
        columns = ['name', 'class-type', 'state', 'under', 'addr']

        result = self.run_and_check('ipadm')

        for line in re.split('\n', result.message):
            if line.startswith('NAME'):
                continue
            l = line.split()
            # change '--' to empty string
            for ndx in range(len(l)):
                if l[ndx] == '--':
                    l[ndx] = ''
            if len(l) == len(columns):
                if l[0].find('/') != -1:
                    parts = l[0].split('/')
                    rdict[parts[0]]['afi'][parts[1]] = dict(zip(columns, l))
                else:
                    rdict[l[0]] = dict(zip(columns, l))
                    rdict[l[0]]['afi'] = dict()
        return rdict

    def run_and_check(self, cmd, expectation=True):
        if True:
            raise NotImplemented
        return ReturnCode(False)


class SolarisSsh(Client, ZFSSystem, Initiator):
    """
    A paramiko based solaris client.
    """

    def __init__(self, *args, **kwargs):
        if isinstance(args[0], dict):  # this allows instantiation with a config dict item
            for k, v in args[0].items():
                setattr(self, k, v)

        else:
            self.user = args[0]
            self.hostname = args[1]
            self.password = args[2]
        self.ethdrv = Ethdrv(self.get_ethdrv)
        super(SolarisSsh, self).__init__(self.hostname, self.user, self.password)
        self.os = 'solaris'
        self.nsdir = '/dev/ethdrv'

    def reboot(self, wait=True):
        """
        reboot the intiator using 'init 6' do not return until ssh stops working
        """
        cmd = "init 6"
        ret = self.run_and_check(cmd)
        if wait:
            ret = self.wait_shutdown()
        self.close()
        return ret

    @wait_until(sleeptime=5, timeout=60 * 60)
    def wait_shutdown(self):
        return self.is_down()

    def is_down(self):
        try:
            self.run_and_check('echo waiting for ssh to shutdown', timeout=5)
        except (OSError, TIMEOUT):
            logger.info('ssh appears to have shutdown')
            return ReturnCode(True, "host appears down")
        return ReturnCode(False)

    def get_ethdrv(self, fname):
        """
        Required function for Ethdrv class
        """
        sftpsession = self.open_sftp()
        try:
            fh = sftpsession.open('/dev/ethdrv/%s' % fname, 'r')
            ret = ReturnCode(True)
            ret.message = fh.read()
        except Exception as e:
            ret = ReturnCode(False, str(e))
        return ret
        # return self.run_and_check('cat /dev/ethdrv/%s' % fname)

    def reconnect(self, after=10, timeout=10, args=None):
        """
        attempts to reconnect to the host in a loop.  ?BUG: This will never give up.

        :param after:
        :type after: float
        :param timeout: length of time to wait each time
        :type timeout: float
        :param args: left in for compatibility with pexpect ssh
        :type args: None
        :return: True
        """
        while 1:
            with ignored(InitiatorError):
                time.sleep(after)
                if super(SolarisSsh, self).connect(timeout=timeout):
                    return True

    def run_and_check(self, cmd, expectation=True, force=False, timeout=None):
        """
        Run a command check the result.  If the caller cares about failure, indicated by
        not setting expectation to False, and the command fails we raise an exception.
        """
        logger.info("calling %s" % cmd)
        if force:
            raise NotImplementedError
        else:
            result = self.run(cmd, timeout=timeout)

        if not result and expectation:
            logger.critical(result.message)
            raise InitiatorError(result.message)
        else:
            return result

    def put(self, localpath, remotepath=None):
        """
        put a file on the initiator from the controlling host
        :param localpath:
        :param remotepath: If None use pwd and basename
        :return:
        """
        if not remotepath:
            remotepath = os.path.basename(localpath)
        sftpsession = self.open_sftp()
        sftpsession.put(localpath, remotepath)
        return

    def get(self, remotepath, localpath=None):
        """
        get a file from the initiator and write it to the controlling host

        :param remotepath: path to remote file
        :param localpath: If None use pwd and basename
        :return:
        """
        if not localpath:
            localpath = "%s/%s" % (os.getcwd(), os.path.basename(remotepath))
        sftpsession = self.open_sftp()
        sftpsession.get(remotepath, localpath)
        return

    def verify_hba_ports_speed(self):
        """
        This function verifies HBA ports speed information
        :return: True if current link rate is in the output
        """
        ports_result = self.run_and_check('ethdrvadm list-ports')
        match = re.search('EHBA-\d+-.*?/(\d+)', str(ports_result))
        if match:
            speed = match.group(1)
            logger.info(
                "ethdrvadm list-ports command ran sucessfully showing link Type and link Speed : %s" % speed)
            return True
        else:
            logger.info("ethdrvadm list-ports command failed, not showing link Speed... ")
            return False

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
        r = self.run_and_check('ethdrvadm list-ports')
        if not r:
            return ports
        lines = r.message.splitlines()
        for l in lines[1:]:  # We skip the header
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

    def lun_exists(self, lun, flush=True):
        """
        Returns lun's aoestat dict::

            {'device': 'sd379', 'port': ['1'], 'target': '91.1', 'size': '2000.398GB'}

        or False in ReturnCode format
        """
        if flush:
            self.aoeflush()
        n = self.aoestat
        if lun in n:
            return ReturnCode(True, n[lun])
        return ReturnCode(False, '%s not found' % lun)

    @property
    def uname(self):
        return self.run_and_check('uname').message.rstrip()

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
        header = re.compile(r"Filesystem[ \t]*Size[ \t]*Used[ \t]*Available[ \t]*Capacity[ \t]*Mounted on")
        lines = output.splitlines()
        info = dict()
        if not header.search(lines[0]):
            print("output not recognized")
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
        :return: list of all /dev/rdisks entries
        :rtype:
        """
        return self.run_and_check('ls /dev/rdsk').message.splitlines()

    def targ2sd(self, targ):
        """
        :return: the symbolic sd device name for the AoE Target
        """
        ret = ''
        if not targ:
            return targ
        n = self.lun_exists(str(targ))
        if n:
            ret = n.message.device
        return ret

    def sd2dev(self, sdname, path='/dev/rdsk/', postfix='p0'):
        """
        :return: disk device or character device for a given sd name as /dev/dsk or /dev/rdsk

        For zpool use set path='/dev/dsk' and postfix=''

        :param sdname: the sd device name e.g. sd35
        :param path: '/dev/rdsk/' or '/dev/dsk/' to toggle character device node
        :param postfix: which slice or partition. Defaults to BIOS whole disk.
        :return:
        """
        ret = ''
        if not sdname:
            return sdname
        cmd = "iostat -nl 1 " + sdname + "|head -n1"
        result = self.run_and_check(cmd)
        if result:
            s = result.message.split()
            if len(s) == 3:
                ret = "%s%s%s" % (path, s[1], postfix)
        return ret

    def sd2targ(self, sd):
        """
        return the aoe target address backing the given /dev/sd* device.
        :param sd:
        :type sd:
        :return:
        :rtype:
        """
        devname = self.sd2dev(sd, path='', postfix='')
        if not devname:
            return devname
        else:
            devtargre = re.compile(r"c\d+t(?P<major>\d+)d(?P<minor>\d+)")
            r = re.match(devtargre, devname)
            if r:
                r = r.groupdict()
                target = AoEAddress(r['major'], r['minor'])
            else:
                target = None
        return target

    def targ2dev(self, targ, path='/dev/rdsk/', postfix='p0'):
        """
        Return the device path for an aoe Target. Defaults to BIOS whole disk for use with fio's raw.
        For zpool use set path='/dev/dsk' and postfix=''

        :param targ: the aoe device e.g. '2.1' or as AoEAddress type
        :param path: '/dev/rdsk/' or '/dev/dsk/' to toggle character device node
        :param postfix: which slice or partition.
        :return:
        """
        n = self.targ2sd(str(targ))
        if n:
            return self.sd2dev(n, path, postfix)
        else:
            return ''

    def _target2device(self, t):
        """
        try to identify a device name for a particular target.
        """

        device = self.run_and_check('ls /dev/rdsk/c*t%sd%s*' % tuple(t.split('.')))
        rregex = re.match('/dev/rdsk/c(\d+)t%sd%s' % tuple(t.split('.')), device.message)

        if rregex:
            return 'c%s' % rregex.group(1) + 't%sd%s' % tuple(t.split('.'))
        else:
            return None
