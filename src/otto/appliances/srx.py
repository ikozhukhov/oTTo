#!/usr/bin/env python
# encoding: utf-8

import os
import re
import logging
from time import sleep
from collections import OrderedDict, defaultdict

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())

from otto.connections.cec import Cec
from otto.connections.ssh_pexpect import Ssh
from otto.lib.otypes import ReturnCode, ApplianceError, ApplianceUsage, AoEAddress, Namespace, Drive
from otto.utils import aoetostr, now, timefmt, since
from otto.lib.pexpect import TIMEOUT, EOF


class Srx(Cec):
    """
    A class for interacting with the SRX using CEC.
    Since the commands are basically passed through
    see the SRX manual for more info.

    Individual drives may be accessed directly using *obj.sNum* where Num is
    the slot number::

        >> sr = Srx(shelfnum,'en0')
        >> sr.connect()
        >> print sr.s1.model
        'WD WD6001BKHG-02D22'

    """

    def __init__(self, shelf, iface, password=None, prompt=None, use_slots=None, version=None):
        self.luncomp = re.compile(
            r"^\s*?(?P<size>\d+\.\d+)\s+(?P<element>\d+\.\d+\.\d+)\s+(?P<drive>\d+\.\d+|update|missing)\s+(?P<state>([a-z]+,?)+)(\s+)?(?P<percent>\d+\.\d+%)?")
        self.lunhdr = re.compile(
            r"^(?P<lun>\d+)\s{1,3}(?P<label>[a-zA-Z0-9_\s\-]{6,17})\s+(?P<status>online|offline)\s+(?P<type>[a-zA-Z0-9]+)\s+(?P<size>\d+\.\d+)\s+(?P<state>\S+)\Z")
        self.lineterm = '\r+\n'
        self.driveahdr = None
        self.sample_warn = None
        self.confirm = None
        self.confirm_update_lun_format = None

        if prompt is None:
            prompt = r'SRX\s+((shelf\s+(unset|\d.*)>)|EXPERTMODE#)\s+'
        super(Srx, self).__init__(shelf, iface, password, prompt)

        self.use_slots = use_slots  #: a list of slots to restrict operations to.

        #: This is set to either 6|7 for backwards compatibile operations
        #: By default we auto negotioate this upon connection.
        self.version = None

        if version:

            self.version = int(version)
        else:
            self.version = version

        #: A dictionary for caching hard data that is otherwise slow to retrieve.  Currently
        #: there is only 'drives' which contains the last run of the drives command.
        self.cache = dict()
        #: Number of slots in this chassis auto determined at connect.
        self.slots = None

    def connect(self, timeout=10, expectation=True):
        if self.closed:  # in case of reconnect
            super(Srx, self).connect(timeout=timeout, expectation=expectation)

        if self.version is None:
            r = self.run('release').strip()
            if r.startswith('RELEASE'):
                r = r.split()[-1]

            result = re.match(r"^SR[X]?-([0-9]+)\.([0-9]+).*", r)
            if result:
                self.version = int(result.group(1))
            else:
                raise ApplianceError('Unable to identify SRX version running in shelf: %s: %s' % (result, r))

        self.slots = self._enumerate_slots()

        for slot in range(int(self.slots)):
            setattr(self, 's%s' % slot, Drive(self.shelf, slot, self.expert_run))

    def expert_run(self, cmd, expectation=True):
        if self.version < 7:  # there was no expertmode before 7
            ret = self.run_and_check(cmd, expectation)
        else:
            tprompt = self.prompt
            self.prompt = 'SRX EXPERTMODE#'
            self.run('/expertmode')
            ret = self.run_and_check(cmd, expectation)
            self.prompt = tprompt
            self.run('exit')
        return ret

    @property
    def ipaddress(self):
        """
        The ipaddress command returns a dictionary containing the information of
        the ipaddress command.

        Version support: 7
        """
        ipdd = defaultdict(lambda: {'port': None, 'address': None, 'mask': None, 'multipath': None})

        if self.version >= 7:
            r = self.run_and_check('ipaddress')
            rs = r.message.splitlines()
            for l in rs[1:]:
                vals = l.split()
                port_num = vals[0][-1]
                ipdd[port_num] = {}
                ipdd[port_num]['port'] = vals[0]
                ipdd[port_num]['address'] = vals[1]
                ipdd[port_num]['mask'] = vals[2]
                ipdd[port_num]['multipath'] = vals[3]
        return ipdd

    @property
    def ipgateway(self):
        """
        The ipgateway command returns a string containing the information of the ipgateway command

        Version support: 7
        """
        if self.version >= 7:
            r = self.run_and_check('ipgateway')
            rs = re.split(self.lineterm, r.message.strip())
            return rs[1]
        else:
            return str()

    def run_and_check(self, cmd, expectation=True, force=False, timeout=10):
        """
        Run a command check the result.  If the caller cares about failure
        and the command fails we raise a generic exception.
        """
        logger.info(cmd + " called")
        result = ReturnCode(True)
        if not self.confirm:
            self.confirm = re.compile("Enter\s+'y'\s+for yes,\s+'n'\s+for no\.\s+Continue\?\s+\[n\]")
        if not self.confirm_update_lun_format:
            self.confirm_update_lun_format = re.compile(r"Would you like to update the LUN format")

        if force:
            t = self.prompt
            self.prompt = [t, self.confirm, self.confirm_update_lun_format]
            result.message = self.run(cmd, timeout=timeout)
            self.prompt = t

            if self.match_index != 0:
                result.message = self.run('y')
        else:
            result.message = self.run(cmd, timeout=timeout)
        logger.debug("rx:" + result.message)
        errors = ['error:',
                  'usage:',
                  'directory entry not found',
                  'unrecoverable failure',
                  'unknown command',
                  'Update failed',
                  'No update files found']

        for x in errors:
            if result.message.count(x):
                result.status = False
                break

        # result.message = result.message.strip().replace('\r\r\n', '\r\n')

        if not result.status:
            if expectation:
                logger.error("%s: %s" % (cmd, result.message))
            else:
                return result
            raise ApplianceError("'%s' failed: %s" % (cmd, result.message))
        return result

    @property
    def release(self):
        """
        The release command returns a string containing the currently running release.

        On SRX6: the commands only returns a single line with the release already running.

        On SRX7
        If a tarc has been uploaded, but the SRX has not been updated, then there will
        be two fields, like so::

            SRX shelf 43> release
            RELEASE       NEXTRELEASE
            SRX-7.0.0-R6  SRX-7.0.0-R7
            SRX shelf 43>

        """
        r = self.run_and_check('release')
        lines = list()
        for line in re.split(self.lineterm, r.message.strip()):
            lines.append(line.strip())

        if len(lines) < 1:
            logger.error("parsing failure: '%s'" % r)
            return r
        if len(lines) == 1:  # SRX 6.X
            r = r.message.split(' - ')[0]
            return r
        if len(lines) == 2:  # SRX 7.X above
            rel = lines[1]
            flds = lines[1].split()
            if len(flds) > 1:
                rel = flds[0]
            return rel

    @property
    def next_release(self):
        """
        The next_release command returns a string containing the release that will
        run upon the user executing the 'update' command, after the SRX reboots.
        If a tarc has been uploaded, but the SRX has not been updated, then
        there will be two fields, like so::

            SRX shelf 43> release
            RELEASE       NEXTRELEASE
            SRX-7.0.0-R6  SRX-7.0.0-R7
            SRX shelf 43>

        """
        r = self.run('release')
        lines = r.splitlines()
        if len(lines) < 2:
            logger.error("parsing failure: '%s'" % r)
            return r
        next_rel = None
        flds = lines[1].split()
        if len(flds) > 1:
            next_rel = flds[1]
        return next_rel

    @property
    def model(self):
        """
        The model command returns a string containing the srx model.
        """
        if self.version >= 7:
            r = self.run_and_check('model')
            r.message = r.message.splitlines()
            if len(r.message) > 1:
                r.message = r.message[1]
        else:
            r = self.run_and_check('model')
        return r.message

    @property
    def serial(self):
        """
        The serial command returns a string containing the srx serial.
        """
        if self.version >= 7:
            r = self.run_and_check('serial')
            m = r.message.splitlines()
            if len(m) > 1:
                r.message = m[1]
        else:
            r = self.run_and_check('serial')
        return r.message

    @serial.setter
    def serial(self, sn):
        """
        Set the srx serial number.
        """
        cmd = "serial -s %s" % sn
        self.run_and_check(cmd)

    @property
    def date(self):
        """
        The date command returns a string containing the output of the date command.
        """
        r = self.run_and_check('date')
        return r.message

    @property
    def motd(self):
        """
        The motd command returns a string containing the output of the motd command.

        Version support: 7
        """
        if self.version >= 7:
            return self.run_and_check('motd').message
        else:
            return ''

    @property
    def list(self):
        """
        see otto.appliances.srx.Srx.luns
        """
        if self.version >= 7:
            return self.luns
        else:
            logger.info("making call to old code for list command")
            return self._list_6

    @property
    def _list_6(self):
        cmd = 'list -l'
        newlun = False
        luns = list()
        wlun = dict()

        r = self.run_and_check(cmd)

        # this is the meat of the method
        # if we weren't screen scraping this would be
        # a little less messy

        c = r.message.splitlines()
        for l in c:
            l = l.strip()
            if not len(l):
                return dict()
            m = l.split()[0]  # the first token on the line
            dots = m.count(".")
            if not dots:
                newlun = True
                raid = False
                component = False
            elif dots == 1:
                raid = True
                component = False
            elif dots == 2:
                component = True
                raid = False
            else:
                return False  # is that right?

            if newlun:
                if len(wlun):
                    luns.append(wlun)
                    wlun = {}
                ls = l.split()
                if ls == 3:
                    wlun['lun'], wlun['size'], wlun['online'] = ls
                else:
                    wlun['lun'] = ls[0]
                    wlun['size'] = ls[1]
                    wlun['online'] = ls[2]
                    label = ' '.join(ls[3:]).strip().strip("'")
                    wlun['label'] = label
                wlun['raids'] = list()
                if wlun['online'] == 'online':
                    wlun['online'] = True
                else:
                    wlun['online'] = False
                newlun = False

            elif raid:
                try:
                    number, size, kind, state = l.split()
                    percent = None
                except ValueError:
                    number, size, kind, state, percent = l.split()
                number = number.split(".")[1]
                r = {'number': number, 'size': size, 'kind': kind, 'state': state, 'components': list(),
                     'percent': percent}
                if wlun.get('raids'):
                    wlun['raids'].append(r)
                else:
                    wlun['raids'] = [r]
            elif component:
                feilds = l.split()
                if len(feilds) == 4:
                    position, stat, size, device = feilds
                else:
                    position, stat, size, device, percent = feilds

                for rd in wlun['raids']:
                    if rd['number'] == position.split('.')[1]:  # eg. 7 in 8.7.0
                        position = position.split('.')[-1]  # eg. 0 in 8.7.0
                        z = {'position': position, 'stat': stat, 'size': size, 'device': device}
                        rd['components'].append(z)
                        # TODO  error handling if none of the ifs hit?
        if len(wlun):
            luns.append(wlun)
        # here I'm punting on rewriting the function to build dicts.
        # this extra conversion will slow otto down a tiny bit
        ldict = dict()
        for l in luns:
            num = l.get('lun')
            ldict[num] = l

        if self.use_slots:  # do not use slots/show LUNs that are not ours
            use = set(self.use_slots)
            for lun in ldict.keys():
                for raid in ldict[lun]['raids']:
                    for comp in raid['components']:
                        if comp['device'].find('.') != -1:
                            slot = comp['device'].split('.')[1]
                            if slot not in use:
                                if ldict.get(lun):
                                    ldict.pop(lun)
        return ldict

    @property
    def luns(self):
        """
        Returns a dictionary with the LUNs' information like so::

            {'0': {   'label': 'update_lun',
                 'lun': '0',
                 'online': False,
                 'raids': [],
                 'size': '0.067',
                 'state': 'normal',
                 'status': 'offline',
                 'type': 'raw'},

             '1': {   'label': '',
                 'lun': '1',
                 'online': False,
                 'raids': [   {   'components': [   {   'device': '43.0',
                                                        'drive': '43.0',
                                                        'element': '1.0.0',
                                                        'position': '0',
                                                        'size': '500.108',
                                                        'stat': 'normal',
                                                        'state': 'normal'},
                                                    {   'device': '43.1',
                                                        'drive': '43.1',
                                                        'element': '1.0.1',
                                                        'position': '1',
                                                        'size': '500.108',
                                                        'stat': 'normal',
                                                        'state': 'normal'},
                                                    {   'device': '43.2',
                                                        'drive': '43.2',
                                                        'element': '1.0.2',
                                                        'position': '2',
                                                        'size': '500.108',
                                                        'stat': 'normal',
                                                        'state': 'normal'}]}],
                 'size': '1000.216',
                 'state': 'initing',
                 'status': 'offline',
                 'type': 'raid5'}}

        """
        if self.version == 6:
            logger.info("redirected to use 'luns' for 6")
            return self.list

        d = dict()
        r = self.run_and_check('luns -a')
        if not r:
            return d

        lun = None
        # groups correspond to LUN, LABEL, STATUS, TYPE, SIZE, STATE
        if not hasattr(self, 'lunhdr'):
            pass
            # groups correspond to SIZE, ELEMENT, DRIVE, STATE
        if not hasattr(self, 'luncomp'):
            pass

        lines = r.message.splitlines()
        for line in lines:
            line = line.strip()

            if not line or line.startswith('LUN'):
                continue

            m = re.search(self.lunhdr, line)

            if m:
                lun = m.group('lun')
                d[lun] = m.groupdict()
                d[lun]['raids'] = list()
                # Strip the label string from the above step
                d[lun]['label'] = d[lun]['label'].strip()
                # below is for backwards compatibility with Srx 6.x CLI
                d[lun]['online'] = False
                if d[lun]['status'] == 'online':
                    d[lun]['online'] = True
                continue

            if not lun:
                logger.error("parsing fail: no lun for '%s'" % line)
                continue
            m = re.search(self.luncomp, line)
            if m:
                comp = m.groupdict()
                flds = comp['element'].split('.')
                if len(flds) < 3:
                    logger.error("element '%s' parsing fail" % m.group(2))
                    continue
                raid = int(flds[1])
                # only add the new raid group, if necessary
                if raid == len(d[lun]['raids']):
                    d[lun]['raids'].append({'components': list()})
                d[lun]['raids'][raid]['components'].append(comp)
                # below is for backwards compatibility with Srx 6.x CLI
                comp['position'] = flds[2]
                comp['device'] = comp['drive']
                comp['stat'] = comp['state']
            else:
                logger.error("lun '%s' parsing fail: '%s'" % (lun, line))
                # do not use slots/show LUNs that are not ours
        if self.use_slots:
            use = set(self.use_slots)
            for lun in d.keys():
                for raid in d[lun]['raids']:
                    for comp in raid['components']:
                        if comp['drive'].find('.') != -1:
                            slot = comp['drive'].split('.')[1]
                            if slot not in use:
                                if d.get(lun):
                                    d.pop(lun)
        return d

    def online(self, lun, expectation=True):
        """
        Online a specific lun online.
        """
        cmd = "online %s" % lun
        r = self.run_and_check(cmd, expectation)
        return r

    def offline(self, lun, expectation=True):  # DISCUSS: run_and_check??
        """
        This command allows you to place a specific lun offline.
        """
        cmd = "offline %s" % lun
        r = self.run_and_check(cmd, expectation)
        return r

    def spare(self, drives, expectation=True):

        if self.version >= 7:
            return self.mkspare(drives=drives, expectation=expectation)
        else:
            logger.info("making call to older version of spare command")
            return self._spare_6(drives=drives, expectation=expectation)

    def _spare_6(self, drives, expectation=True):

        if type(drives) == list:
            drives = ' '.join(drives)
        cmd = "spare %s" % drives
        r = self.run_and_check(cmd, expectation)
        return r

    def mkspare(self, drives, expectation=True):
        """
        'Drives' is either a string or a list of strings.
        Returns a ReturnCode.
        """
        if type(drives) == list:
            drives = ' '.join(drives)
        cmd = "mkspare %s" % drives
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    @property
    def spares(self):
        """
        Returns a dictionary of parsed output.
        """
        d = dict()
        if self.version >= 7:
            cmd = 'spares'
        else:
            cmd = 'spare'
        r = self.run_and_check(cmd)
        if not r:
            return d
        lines = re.split(self.lineterm, r.message)
        for line in lines:
            if not line or line.startswith('DRIVE'):
                continue
            flds = line.split()
            if len(flds) < 2:
                logger.error("parsing failure: %s" % line)
                continue
            d[flds[0]] = {'drive': flds[0], 'size': flds[1]}
        return d

    def rmspare(self, drives, expectation=True):
        """
        Removes the spare role from one or more drives in a shelf.

        Drives is expected to be either a string, or a list of strings.
        Returns a ReturnCode.
        Version support: 6, 7
        """
        if type(drives) == list:
            drives = ' '.join(drives)
        cmd = "rmspare %s" % drives
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def cmenable(self, luns, expectation=True):
        """
        The cmenable command marks specified LUNs for NVRAM data protection and
        records the LUN serial number on the CacheMotion card.
        'Luns' is expected to be a string, or a list of strings.
        Returns a ReturnCode.
        Version support: 6, 7.
        """
        if type(luns) == list:
            luns = ' '.join(luns)

        if self.version >= 7:
            cmd = '/cmenable %s' % luns
        else:
            cmd = 'cmenable %s' % luns

        return self.run_and_check(cmd, expectation=expectation)

    def cmdisable(self, luns, expectation=True):
        """
        You can disable NVRAM data protection on a LUN by issuing cmdisable and
        specifying the LUN.
        'Luns' is expected to be a string, or a list of strings.
        Returns a ReturnCode.
        Version support: 6, 7.
        """
        if type(luns) == list:
            luns = ' '.join(luns)

        if self.version >= 7:
            cmd = '/cmdisable %s' % luns
        else:
            cmd = 'cmdisable %s' % luns

        return self.run_and_check(cmd, expectation=expectation)

    @property
    def cmlist(self):
        """
        Returns a dictionary indicating cache memory status of each existing lun.
        Version support: 6, 7.
        """

        if self.version >= 7:
            raise ApplianceUsage("The 'cmlist' command no longer exists in SRX-7.x.")
        else:
            return self._cmlist_6

    @property
    def _cmlist_6(self):
        """
        Returns a dictionary indicating cache memory status of eachexisting lun.

        A sample of the output is like this::

            SRX shelf 39> cmlist
            LUN   SERIAL
            0     7FED1FC0-00-4FC0351F
            1     7FED1FC0-01-4FC0355F
            2     7FED1FC0-02-4FC0357D
            3     7FED1FC0-03-4FC03587


        That will turn into the following dictionary::

            {
                '0' : '7FED1FC0-00-4FC0351F',
                '1': '7FED1FC0-01-4FC0355F',
                ......
            }

        """
        cmd = 'cmlist'
        cache_report = dict()

        r = self.run_and_check(cmd)
        if r:
            rs = re.split(self.lineterm, r.message)
            for l in rs:
                if l.startswith('LUN'):
                    # This is the output's header so we can safety ignore it
                    pass
                else:
                    lun, serial = l.split()
                    cache_report[lun] = serial
            return cache_report

    @property
    def cmstat(self):
        """
        Returns a dictionary indicating cache memory status of each lun::

            {
                '3' : 'enabled',
                '10': 'disabled'
            }

        Version support: 6, 7.
        """
        d = dict()

        if self.version >= 7:
            cmd = '/cmstat'
        else:
            cmd = 'cmstat'

        r = self.run_and_check(cmd)

        if not r:
            return d
        rs = re.split(self.lineterm, r.message)
        for l in rs:
            if not l or l.startswith('LUN'):
                continue
            else:
                lun, state = l.split()
                d[lun] = state
        return d

    @property
    def cmlunid(self):
        """
        The SSD non-volatile storage device on the CacheMotion card is a LUN with an ID
        that is 254 by factory default. Issuing cmlunid without
        arguments displays the CacheMotion LUN ID of the local CacheMotion card.
        """
        if self.version >= 7:
            cmd = '/cmlunid'
        else:
            cmd = 'cmlunid'

        return self.run_and_check(cmd)

    @cmlunid.setter
    def cmlunid(self, lun):
        """
        Change the LUN parameter of the local CacheMotion
        """
        if self.version >= 7:
            cmd = '/cmlunid %s' % lun
        else:
            cmd = 'cmlunid %s' % lun

        self.run_and_check(cmd)

    @property
    def cmcheck(self):
        """
        The cmcheck command provides cache statistics for both CacheMotion and EtherFlash Cache.

        Statistics for Cache level 0 apply to CacheMotion, while statistics for Cache level 1
        apply to EtherFlash Cache. See a sample below of the command ouptut.

        Parameters: None.

        Returns a dictionary representing the data reported by cmcheck, an empty dictionary will be returned if
        there's no data to report::

            {'0': {'device': [{'blocks_in_cache': '917504',
                           'data_blocks': '910164',
                           'device_name': '#S/sdS0/data',
                           'direct_blocks': '1',
                           'emptypos': '6360',
                           'first_data_block': '7227',
                           'id': '0',
                           'metadata_blocks': '7226',
                           'super_blocks': '1'}],
                   'hit_rate': '75',
                   'recent_hit_rate': '75',
                   'target': [{'hit_rate': '75',
                           'id': '1',
                           'in_cache': '910164',
                           'recent_hit_rate': '75',
                           'working_set': '827524'}]},
             '1': {'device': [{'blocks_in_cache': '335824',
                           'blocksize': '131072',
                           'data_blocks': '20483',
                           'device_name': '/raiddev/0/data',
                           'direct_blocks': '0',
                           'emptypos': '2',
                           'first_data_block': '85',
                           'flags': '0100',
                           'id': '0',
                           'metadata_blocks': '84',
                           'read_errors': '0',
                           'super_blocks': '1',
                           'version': '2',
                           'write_errors': '0'},
                          {'blocks_in_cache': '335824',
                           'blocksize': '131072',
                           'data_blocks': '20482',
                           'device_name': '/raiddev/3/data',
                           'direct_blocks': '0',
                           'emptypos': '2',
                           'first_data_block': '85',
                           'flags': '0100',
                           'id': '3',
                           'metadata_blocks': '84',
                           'read_errors': '0',
                           'super_blocks': '1',
                           'version': '2',
                           'write_errors': '0'}],
                   'hit_rate': '98',
                   'recent_hit_rate': '100',
                   'target': [{'hit_rate': '94',
                           'id': '0',
                           'in_cache': '8',
                           'recent_hit_rate': '25',
                           'working_set': '1'},
                          {'hit_rate': '98',
                           'id': '1',
                           'in_cache': '81928',
                           'recent_hit_rate': '100',
                           'working_set': '8'}]}}

        """

        cache = {}
        if self.version >= 7:
            cmd = '/cmcheck'
        else:
            cmd = 'cmcheck'
        result = self.expert_run(cmd)
        if result:
            data = result.message
        else:
            return cache
        targetCount = 0
        for l in re.split(self.lineterm, data):
            m = re.match('Cache level (\d)', l)
            if m:
                cacheID = m.group(1)
                cache[cacheID] = {}  # We add an element to the cache list
                targetCount = 0
                continue
            m = re.match('device (?P<id>\d):\s(?P<device_name>.*)', l)
            if m:
                devID = int(m.group('id'))
                if 'devices' not in cache[cacheID]:
                    cache[cacheID]['devices'] = {}  # We add an element to the device dict
                cache[cacheID]['devices'][devID] = m.groupdict()  # We add a dict of each device
                continue
            m = re.match(
                '(?P<blocks_in_cache>\d+) blocks in cache, first data block is (?P<first_data_block>\d+),  emptypos=(?P<emptypos>\d+)',
                l)
            if m:
                cache[cacheID]['devices'][devID] = m.groupdict()
                continue
            m = re.match(
                'version: (?P<version>\d+), blocksize: (?P<blocksize>\d+), flags: (?P<flags>\d+), write errors: (?P<write_errors>\d+), read errors: (?P<read_errors>\d+)',
                l)
            if m:
                cache[cacheID]['devices'][devID] = m.groupdict()
                continue
            m = re.match(
                '(?P<super_blocks>\d+) super blocks, (?P<metadata_blocks>\d+) metadata blocks, (?P<direct_blocks>\d+) direct blocks, (?P<data_blocks>\d+) data blocks',
                l)
            if m:
                cache[cacheID]['devices'][devID] = m.groupdict()
                continue
            m = re.match('hit rate (?P<hit_rate>\d+)%  recent hit rate (?P<recent_hit_rate>\d+)%', l)
            if m:
                cache[cacheID].update(m.groupdict())
                continue
            m = re.match(
                'target (?P<id>\d+)  in cache (?P<in_cache>\d+)  working set (?P<working_set>\d+)  hit rate (?P<hit_rate>\d+)%  recent hit rate (?P<recent_hit_rate>\d+)%',
                l)
            if m:
                if 'target' not in cache[cacheID]:
                    cache[cacheID]['target'] = {}
                cache[cacheID]['target'].update(m.groupdict())
                targetCount += 1
        return cache

    def fcenable(self, luns, expectation=True):

        if type(luns) == list:
            luns = ' '.join(luns)

        if self.version >= 7:
            return self.fclunenable(luns, expectation)
        else:
            logger.info('calling old code for fcenable command')
            return self._fcenable_6(luns, expectation)

    def _fcenable_6(self, luns, expectation=True):
        """
        The fcenable commmand enables read cache functionality for the data on specified LUNs.

        Parameters:
            lun: the lun we want to start using flash cache
        """
        return self.run_and_check('fcenable %s' % luns, expectation=expectation)

    def fclunenable(self, luns, expectation=True):
        """
        The fclunenable commmand enables read cache functionality for the data on specified LUNs.
        """
        return self.expert_run('fclunenable %s' % luns, expectation=expectation)

    def fcdisable(self, luns, expectation=True):
        """
        The fcdisable command disables read cache functionality for the data on
        either specified LUNs or all LUNs on the shelf.

        Version support: 6, 7
        """
        if type(luns) == list:
            luns = ' '.join(luns)

        if self.version >= 7:
            return self.fclundisable(luns, expectation=expectation)
        else:
            logger.info("calling old code for fcdisable command")
            return self._fcdisable_6(luns, expectation=expectation)

    def _fcdisable_6(self, luns, expectation=True):
        """
        The fcdisable command disables read cache functionality for the data on
         either specified LUNs or all LUNs on the shelf.

        Parameters::

            lun: the lun we want to stop using flash cache

        """
        return self.run_and_check('fcdisable %s' % luns, expectation=expectation)

    def fclundisable(self, lun, expectation=True):
        """
        The fclundisable command disables read cache functionality for the data on
        either specified LUNs or all LUNs on the shelf.
        """
        return self.expert_run('fclundisable %s' % lun, expectation=expectation)

    def fcconfig(self, slot, pct=None, expectation=True):

        if type(slot) == list:
            slot = ' '.join(slot)
        if self.version >= 7:
            return self.fcadd(slot, pct, expectation=expectation)
        else:
            logger.info("calling old code for fcconfig command")
            return self._fcconfig_6(slot, pct, expectation=expectation)

    def _fcconfig_6(self, slot, pct=None, expectation=True):
        """
        Configures a slot or a set of slots on a shelf to be used for flash cache.
        """
        if pct:
            cmd = 'fcconfig -o %s %s' % (pct, slot)
        else:
            cmd = 'fcconfig %s' % slot
        return self.run_and_check(cmd, expectation=expectation, timeout=60)

    def fcadd(self, slot, pct=None, expectation=True):
        """
        The fcadd command adds/configures one or more device(s) as a read cache, in
        order to significantly improve read performance on frequently acccessed data.
        Parameters::

            drive: the drives to turn into flash cache drives
            pct: Allows you to configure the overcommit percentage for the specified
                range of devices. Leaving a percentage of available space unused can
                improve performance and durability of SSDs.

        The default overcommit percentage is 20% when not specified.
        """
        if type(slot) == list:
            slot = ' '.join(slot)

        if pct:
            cmd = 'fcadd -o %s %s' % (pct, slot)
        else:
            cmd = 'fcadd %s' % slot
        return self.expert_run(cmd, expectation=expectation)

    def rmfcache(self, slot=None, expectation=True):

        if type(slot) == list:
            slot = ' '.join(slot)

        if self.version >= 7:
            return self.fcremove(slot, expectation=expectation)
        else:
            logger.info("calling old code for rmfcache command")
            return self._rmfcache_6(expectation=expectation)  # rmfcache on ver. 6 does not need a parameter

    def _rmfcache_6(self, expectation=True):
        """
        Remove the status of flash cache to all drives on the srx shelf.
        """
        cmd = 'rmfcache'
        return self.run_and_check(cmd, expectation)

    def fcremove(self, slot=None, expectation=True):
        """
        The fcremove command removes the read cache from the shelf as well as the
        cache configuration of all affected LUNs.  The 'drives' argument should be a
        string specifying either "all", the specific LUN, or a list of LUNs as strings.
        """
        if slot is not None:
            cmd = 'fcremove %s' % slot
        else:
            cmd = 'fcremove all'
        return self.expert_run(cmd, expectation=expectation)

    def fcstat(self):
        """
        The fcstat command displays the drive and it's size
        for each drive whose role is 'cache'.
        """
        d = dict()
        f = self.expert_run('fcstat')

        if self.version >= 7:
            if f:  # Looks to me like fcstat on ver 7 is passing wrong data
                regex = re.compile('(\d+\.\d+)\s+(\d+\.\d+)')
                for line in re.split(self.lineterm, str(f)):
                    if not line or line.startswith('DRIVE'):
                        continue
                    m = re.search(regex, line)
                    if not m:
                        raise ApplianceError("parse failure: '%s'" % line)
                    drive = m.group(1)
                    d[drive] = {'drive': drive, 'size': m.group(2)}
        else:
            if f:
                for line in str(f).split('\n'):
                    regExp = re.search('(\d+):\s+(disabled|enabled)', line)
                    if regExp:
                        d[regExp.group(1)] = regExp.group(2)

        return d

    @property
    def fcpriority(self):
        """
        Reports flash cache performance settings for each lun.

        Example:
            {
                '9'  : {'pri': '10', 'minpct': '10'},
                '10' : {'pri': '0', 'minpct': '0'},
                '8'  : {'pri': '10', 'minpct': '0'},
                '200': {'pri': '0', 'minpct': '0'}
            }

        """
        if self.version >= 7:
            return self.fclunstat
        else:
            return self._fcpriority_6()

    @fcpriority.setter
    def fcpriority(self, prioritystr):
        lun = str()
        pri = str()
        pct = str()
        flds = prioritystr.split()
        nargs = len(flds)
        if nargs > 2:
            lun = flds[0]
            pri = flds[1]
            pct = flds[2]
        elif nargs > 1:
            lun = flds[0]
            pri = flds[1]
        elif nargs > 0:
            lun = flds[0]
        if self.version >= 7:
            self.fclunpriority(lun, pri, pct=pct)
        elif self.version < 6:
            self._fcpriority_6(lun, pri, pct)

    def _fcpriority_6(self, lun=None, pri=None, pct=None):

        if lun:
            cmd = 'fcpriority %s %s' % (lun, pri)
            if pct:
                cmd += '%s' % pct
            return self.run_and_check(cmd)
        else:
            cmd = 'fcpriority'
            result = dict()

            fcstatus = self.run_and_check(cmd)

            if fcstatus:
                for line in str(fcstatus).split('\n')[1:]:
                    regExp = re.search('(\d+)\s+(\d+)\s+(\d+)', line)
                    result[regExp.group(1)] = {'pri': regExp.group(2), 'pct': regExp.group(3)}

            return result

    @property
    def fclunstat(self):
        """
        Returns a dictionary with the read cache status of all cache LUNs on the shelf.
        """
        r = dict()
        f = self.expert_run('fclunstat')
        if f:
            regex = re.compile('(\d+)\s+(disabled|enabled)\s+(\d+)\s+(\d+)')
            for line in re.split(self.lineterm, f.message.strip()):
                if not line or line.startswith('LUN'):
                    continue
                m = re.search(regex, line)
                if not m:
                    raise ApplianceError("parse failure: '%s'" % line)
                lun = m.group(1)
                r[lun] = dict()
                r[lun]['lun'] = lun
                r[lun]['status'] = m.group(2)
                r[lun]['pri'] = m.group(3)
                r[lun]['pct'] = m.group(4)
        return r

    def fclunpriority(self, lun, pri, pct=None, expectation=True):
        """
        The fclunpriority command allows you to specify performance improvement relative to
        other LUNs as well as the approximate minimum percentage of the cache targeted for the
        specified LUN.
        Parameters are expected to be strings::

            lun: the lun to affect with the command.
            pri: Enter a number from zero to 100. This number is a unitless value
                 that specifies performance improvement relative to other LUNs.
            pct: Enter a number from one to 100. This number is the approximate
                 minimum percentage of the cache targeted for the specified LUN.

        Returns a ReturnCode.
        """
        cmd = 'fclunpriority %s %s' % (lun, pri)
        if pct:
            cmd += ' %s' % pct
        return self.expert_run(cmd, expectation=expectation)

    def flushcacheenable(self, luns):
        """
        'luns' is expected to be a single lun as
        a string, or a list of luns as strings.
        Returns a ReturnCode.

        Version support: 7.0.1-R6 and above
        """
        if self.release < 'SRX-7.0.1-R6':
            return ReturnCode(False, 'flushcacheenable command unsupported in release {0}'.format(self.release))
        if type(luns) == list:
            luns = ' '.join(luns)
        return self.run_and_check('flushcacheenable {0}'.format(luns))

    def flushcachedisable(self, luns):
        """
        'luns' is expected to be a single lun as
        a string, or a list of luns as strings.
        Returns a ReturnCode.

        Version support: 7.0.1-R6 and above
        """
        if self.release < 'SRX-7.0.1-R6':
            return ReturnCode(False, 'flushcachedisable command unsupported in release {0}'.format(self.release))
        if type(luns) == list:
            luns = ' '.join(luns)
        return self.run_and_check('flushcachedisable {0}'.format(luns))

    @property
    def flushcachestat(self, luns=''):
        """
        Returns a dictionary containing available/provided luns and
        the flushcache state for each one (enabled or disabled).
        For example, this on the CLI::

            SRX shelf 43> flushcachestat
            LUN   FLUSHCACHE
            0       disabled
            1        enabled
            2       disabled
            3       disabled
            4       disabled
            SRX shelf 43>

        returns this::

            {   '0': {   'lun': '0', 'status': 'disabled'},
                '1': {   'lun': '1', 'status': 'enabled'},
                '2': {   'lun': '2', 'status': 'disabled'},
                '3': {   'lun': '3', 'status': 'disabled'},
                '4': {   'lun': '4', 'status': 'disabled'}}

        Version support: 7.0.1-R6 and above
        """
        d = dict()
        if self.release < 'SRX-7.0.1-R6':
            logger.error('flushcachestat command unsupported in release {0}'.format(self.release))
            return d
        if type(luns) == list:
            luns = ' '.join(luns)
        r = self.run_and_check('flushcachestat {0}'.format(luns))
        if not r:
            return d
        lines = r.message.splitlines()
        for line in lines:
            if not line or line.startswith('LUN'):
                continue
            flds = line.split()
            if len(flds) < 2:
                logger.error("parsing failure: '%s'" % line)
                continue
            lun = flds[0]
            d[lun] = {'lun': lun, 'status': flds[1]}
        return d

    @property
    def sos(self):
        """
        Run the sos command, and return the result as a string.
        Due to the CorOS integration into SRX-7.x, the sos command
        now returns a single line with an 'scp' command that the user
        can execute on a remote host in order to get a copy of the sos
        file that was saved to the staging area.  Use the otto.lib.srx.sos7()
        method to take the data returned from this command, and grab the
        contents of the sos file.

        """
        return self.run_and_check('sos', timeout=300).message

    def _check_range(self, slotrange, expectation=True):
        # check for slots in a range that are not in use_slots
        if self.use_slots is None:
            return ReturnCode(True, "no slots protected")
        first, last = slotrange.split('-')
        first = first.split('.')[1]
        selected = set(range(int(first), int(last) + 1))
        use = set()
        for x in self.use_slots:
            use.add(int(x))
        notmine = use.intersection(selected)
        if len(notmine) and expectation:
            raise Exception("implicit use of excluded slot(s) in range: %s" % notmine)
        else:
            return ReturnCode(False, "implicit use of excluded slot(s) in range: %s" % notmine)

    def make(self, lun, raidtype, slots='', lunvers=None, clean=False, force=True, expectation=True):
        if self.version >= 7:
            return self.mklun(lun, raidtype, drives=slots, lunvers=lunvers,
                              clean=clean, force=force, expectation=expectation)
        else:
            logger.info("calling old code for make command")
            return self._make_6(lun, raidtype, slots, lunvers, clean, force, expectation)

    def _make_6(self, lun, raidtype, slots=None, lunvers=None, clean=False, force=True, expectation=True):
        """
        make a lun
        clean  skips parity build
        lunvers allows specification of lun format
        raidtype is not checked but the sr supports::

            'jbod', 'raidL', 'raidl', 'raid0',
            'raid1', 'raid10', 'raid5', 'raid6rs', 'raw'

        """
        makeclean = ""
        s = str()

        if type(slots) == list:  # handle lists of type str or AoEAddress
            for j in slots:
                if type(j) == AoEAddress:
                    slots[slots.index(j)] = aoetostr(j)
                else:
                    if j.count("-"):
                        self._check_range(j, expectation)
                    elif self.use_slots:
                        selected = set()
                        use = set()
                        for x in self.use_slots:
                            use.add(int(x))

                        for x in slots:
                            if x.count("-"):
                                start, stop = x.split('-')
                                start = start.split('.')[1]
                                for i in range(int(start), int(stop) + 1):
                                    selected.add(i)
                            else:
                                selected.add(int(x.split('.')[1]))

                        notmine = selected.difference(use)
                        if notmine:
                            if expectation:
                                raise Exception("implicit use of excluded slot(s) in range: %s" % notmine)
                            else:
                                return ReturnCode(False, "implicit use of excluded slot(s) in range: %s" % notmine)

                    s = "%s %s" % (s, j)

        elif type(slots) == str:
            if self.use_slots:
                if slots.count('-'):  # determine need for looking in ranges
                    slist = slots.split()
                    for x in slist:
                        result = ReturnCode(True)
                        if x.count('-'):  # if this item is a range
                            result = self._check_range(x, expectation)
                        if not result:
                            return result

                else:  # assuming a str that is a range-less list of LUNs
                    selected = set()
                    use = set([int(x) for x in self.use_slots])
                    for slot in slots.split():  # possibly ws separated
                        selected.add(int(slot.split('.')[1]))

                    notmine = selected.difference(use)

                    if len(notmine):
                        if expectation:
                            raise Exception("use of excluded slot(s): %s" % notmine)
                        else:
                            return ReturnCode(status=False, message="use of excluded slot(s): %s" % notmine)

            s = slots

        if type(lunvers) is str:
            if not lunvers.startswith('-V'):
                lunvers = '-V %s ' % lunvers
        elif type(lunvers) is int:
            lunvers = '-V %s ' % lunvers
        elif lunvers is None:
            lunvers = ""

        if clean:
            makeclean = "-c "

        cmd = "make %s %s %s %s %s" % (lunvers, makeclean, lun, raidtype, s)

        result = self.run_and_check(cmd, expectation=expectation, force=force)

        if not result and expectation:
            raise ApplianceError("%s: %s" % (cmd, result.message))
        return result

    def mklun(self, lun, raidtype, drives=None, lunvers=None, clean=False, force=True, expectation=True):
        """
        make a lun
        clean  skips parity build
        lunvers allows specification of lun format
        raidtype is not checked but the sr supports::

            'jbod', 'raidL', 'raidl', 'raid0',
            'raid1', 'raid10', 'raid5', 'raid6rs', 'raw'

        """
        makeclean = ""
        s = str()

        if type(drives) == list:  # handle lists of type str or AoEAddress
            for j in drives:
                if type(j) == AoEAddress:
                    drives[drives.index(j)] = aoetostr(j)
                else:
                    if j.count("-"):
                        self._check_range(j, expectation=expectation)
                    elif self.use_slots:
                        selected = set()
                        use = set()
                        for x in self.use_slots:
                            use.add(int(x))

                        for x in drives:
                            if x.count("-"):
                                start, stop = x.split('-')
                                start = start.split('.')[1]
                                for i in range(int(start), int(stop) + 1):
                                    selected.add(i)
                            else:
                                selected.add(int(x.split('.')[1]))

                        notmine = use.difference(selected)

                        if notmine and expectation:
                            raise Exception("implicit use of excluded slot(s) in range: %s" % notmine)
                        else:
                            return ReturnCode(False, "implicit use of excluded slot(s) in range: %s" % notmine)

                    s = "%s %s" % (s, j)

        elif type(drives) == str:
            if self.use_slots:
                if drives.count('-'):  # determine need for looking in ranges
                    slist = drives.split()
                    for x in slist:
                        result = ReturnCode(True)
                        if x.count('-'):  # if this item is a range
                            result = self._check_range(x, expectation=expectation)
                        if not result:
                            return result

                else:  # assuming a str that is a range-less list of LUNs
                    selected = set()
                    use = set([int(x) for x in self.use_slots])
                    for slot in drives.split():  # possibly ws separated
                        selected.add(int(slot.split('.')[1]))

                    notmine = selected.difference(use)

                    if len(notmine):
                        if expectation:
                            raise Exception("use of excluded slot(s): %s" % notmine)
                        else:
                            return ReturnCode(status=False, message="use of excluded slot(s): %s" % notmine)

            s = drives

        if type(lunvers) is str:
            if not lunvers.startswith('-V'):
                lunvers = '-V %s ' % lunvers
        elif type(lunvers) is int:
            lunvers = '-V %s ' % lunvers
        elif lunvers is None:
            lunvers = ""

        if clean:
            makeclean = "-c "

        cmd = "mklun %s %s %s %s %s" % (lunvers, makeclean, lun, raidtype, s)

        result = self.run_and_check(cmd, expectation=expectation, force=force)

        if not result and expectation:
            raise ApplianceError("%s: %s" % (cmd, result.message))
        return result

    def jbod(self, slot, expectation=True, force=True):
        if type(slot) == list:
            slot = ' '.join(slot)

        if self.version >= 7:
            return self.mkjbod(slot, expectation=expectation, force=force)
        else:
            logger.info("calling old code for jbod command")
            return self._jbod_6(slot, expectation=expectation, force=force)

    def _jbod_6(self, slot, expectation=True, force=True):
        cmd = "jbod %s" % slot
        return self.run_and_check(cmd, expectation=expectation, force=force)

    def mkjbod(self, drive, expectation=True, force=True):
        cmd = 'mkjbod %s' % drive
        return self.run_and_check(cmd, expectation=expectation, force=force)

    def remove(self, luns, expectation=True, force=True):
        if self.version >= 7:
            return self.rmlun(luns, expectation=expectation, force=force)
        else:
            logger.info("calling old code for remove command")
            return self._remove_6(luns, expectation, force=force)

    def _remove_6(self, lun, expectation=True, force=True):
        """
        Removes a lun. If the lun is offline
        """

        if type(lun) == dict:
            lun = aoetostr(lun)
        else:
            lun = str(lun)
        if force:
            cmd = 'offline -f %s' % lun  # TODO: this is not what force is for.

            result = self.run_and_check(cmd)
            if not expectation:
                if result.message.endswith('not found, skipping'):
                    logger.error("%s: %s" % (cmd, result.message))
                    result.status = False
                elif result.message.endswith('is not a valid lun value'):
                    logger.critical("%s: %s" % (cmd, result.message))
                    result.status = False

        cmd = "remove -f %s" % lun
        result = self.run_and_check(cmd)
        if not expectation:
            if result.message.endswith('not found, skipping'):
                logger.error("%s: %s" % (cmd, result.message))
                result.status = False
            elif result.message.endswith('is not a valid lun value'):
                logger.critical("%s: %s" % (cmd, result.message))
                result.status = False

        return result

    def rmlun(self, luns, expectation=True, force=True):
        """
        Remove specified luns. If it/they is/are online, first offline it/them.
        Returns a ReturnCode.
        """
        if type(luns) == dict:
            luns = aoetostr(luns)
        elif type(luns) == list:
            luns = ' '.join(luns)
        else:
            luns = str(luns)
        flagf = str()
        if force:
            flagf = '-f'
        return self.run_and_check("rmlun %s %s" % (flagf, luns), expectation=expectation)

    @property
    def disks(self):
        """
        Returns a dictionary with information of disks.

        """
        if self.version >= 7:
            return self.drives
        else:
            logger.info("calling old code for disks command")
            return self._disks_6

    @property
    def _disks_6(self):
        """
        Get disk info !this does not use the disks command! Returns an ordered dict::

            s.disks['22']
            {'FW': 'SN04',
             'Model': 'ST9500530NS',
             'SN': '9SP2K7M3',
             'config': None,
             'geometry': '976773168 512',
             'hresets': '0',
             'link': '1.5 Gb/s',
             'r0resets': '0',
             'sstate': 'up',
             'state': 'up',
             'type': 'sata',
             'version': None}

        """
        # I think this is gated by the speed of the console
        cmd = 'ls /raiddev/'
        diskd = OrderedDict()
        result = self.run_and_check(cmd)

        if result:
            if self.use_slots:
                use = set(self.use_slots)
            else:
                use = set()
            ignored = {'events', 'extra', 'stat', 'ctl'}
            have = set()
            rs = re.split(self.lineterm, result.message)
            for line in rs:
                flds = line.split('/raiddev/')
                if len(flds) > 1:
                    have.add(flds[1])
            have = have.difference(ignored)
            if use:
                use = have.intersection(use)
            else:
                use = have
            ouse = [y for y in use]
            ouse.sort(key=int)
            for disk in ouse:
                current = dict()
                cmd = 'cat /raiddev/{0:>s}/stat'.format(disk)
                result = self.run_and_check(cmd)
                r = result.message
                rs = re.split(self.lineterm, r.strip())
                for line in rs:
                    if line:
                        kvpair = line.split(':')
                        k = kvpair[0]
                        if len(kvpair) < 2:
                            logger.error("failed to split, expected a colon here: '%s'" % line)
                            continue
                        v = kvpair[1].strip()
                        current[k] = v
                if current['sstate'] != 'missing':
                    diskd[disk] = current
        else:
            raise ApplianceError(result.message)

        for d in diskd:

            r = self.run_and_check('disks -a %s.%s' % (self.shelf, d))
            rs = r.message.splitlines()
            if not self.driveahdr:
                self.driveahdr = \
                    re.compile(r"^(?P<drive>\d+.\d+)\s+"
                               r"(?P<size>(\*?\d+\.\d+GB|missing|up))"
                               r"(\s+(?P<role>[0-9+\.0-9+\.0-9+|cache|no disk|spare]*?)\s+"
                               r"(?P<model>[\w\s\-]+)\s+"
                               r"(?P<firmware>[a-zA-Z0-9\.\-]+)\s+"
                               r"(?P<mode>(sata|sas)\s+\d+.\d+Gb/s))?")

            tablehdrfound = False
            diskhdrfound = False
            for l in rs:
                if tablehdrfound is False:
                    if l.startswith('DISK'):
                        tablehdrfound = True
                    continue

                disk = d
                if not diskhdrfound:
                    summary = re.search(self.driveahdr, l)
                    try:
                        diskd[disk] = summary.groupdict()
                    except AttributeError:
                        raise ApplianceError('Somethings wrong with my input line:\n%s' % l)
                    diskhdrfound = True
                    continue
                try:
                    k, v = l.strip().split(':')
                except ValueError:
                    raise ApplianceError("expecting a key:value output, got this: %s" % l.strip())
                v = v.replace("'", "")
                diskd[d][k] = v.strip()
                if self.use_slots and d not in self.use_slots:
                    continue

        for i in diskd.keys():
            disk = "%s.%s" % (self.shelf, i)
            cmd = "disks -c %s" % disk
            ret = self.run_and_check(cmd)
            cline = re.split(self.lineterm, ret.message.strip())
            cline = cline[1].split()
            if len(cline) > 2:
                version = cline[1]
                config = ' '.join(cline[2:])
                diskd[i]['version'] = version
                diskd[i]['config'] = config
            else:
                diskd[i]['version'] = None
                diskd[i]['config'] = None
                diskd[i]['slot'] = i
        self._set_disks(diskd)

        return diskd

    @property
    def drives(self):
        """
        Returns an ordered dict of drive info indexed by slot::

            >> sr.drives['0']

            {'FW': 'SN04',
             'Model': 'ST9500530NS',
             'SN': '9SP2K7M3',
             'config': None,
             'geometry': '976773168 512',
             'hresets': '0',
             'link': '1.5 Gb/s',
             'r0resets': '0',
             'sstate': 'up',
             'state': 'up',
             'type': 'sata',
             'version': None}

        """
        diskd = OrderedDict()
        dlist = list()
        d = self.run_and_check('drives')
        ds = re.split(self.lineterm, d.message.strip())
        for line in ds:
            if line.startswith('DRIVE'):
                continue
            did, dstate = line.split()[:2]
            if dstate != 'missing':
                if self.use_slots:
                    slot = did.split('.')[1]
                    if int(slot) in self.use_slots or slot in self.use_slots:
                        dlist.append(did)
                else:
                    dlist.append(did)

        for d in dlist:
            r = self.run_and_check('drives -a %s' % d)
            rs = re.split(self.lineterm, r.message.strip())
            if not self.driveahdr:
                self.driveahdr = \
                    re.compile(r"^(?P<drive>\d+.\d+)\s+"
                               r"(?P<size>\*?\d+\.\d+)\s+"
                               r"(?P<role>[0-9+\.0-9+\.0-9+|cache|spare]*?)\s+"
                               r"(?P<model>[a-zA-Z0-9\s\])\s+"
                               r"(?P<firmware>[a-zA-Z0-9\.\-]+)\s+"
                               r"(?P<mode>(sata|sas)\s+\d+.\d+Gb/s)")

            foundheader = False
            for l in rs:
                if l.startswith('DRIVE'):
                    continue
                disk = d.split('.')[1]
                if not foundheader:
                    summary = re.search(self.driveahdr, l)
                    try:
                        diskd[disk] = summary.groupdict()
                    except AttributeError:
                        raise ApplianceError("regex:\n%s\ndid not match:\n %s" % (self.driveahdr.pattern, l))
                    foundheader = True
                    continue
                try:
                    k, v = l.strip().split(':')
                except ValueError:
                    raise ApplianceError("expecting a key:value output, got this: %s" % l.strip())
                v = v.replace("'", "")
                diskd[d.split('.')[1]][k] = v.strip()
                if self.use_slots and d not in self.use_slots:
                    continue

            ret = self.run_and_check("drives -c %s" % d)
            cline = ret.message.splitlines()
            cline = cline[1].split()
            if len(cline) > 1:
                version = cline[1]
                config = ' '.join(cline[2:])
                diskd[disk]['version'] = version
                diskd[disk]['config'] = config
            else:
                diskd[disk]['version'] = None
                diskd[disk]['config'] = None
        self._set_disks(diskd)
        return diskd

    @property
    def temp(self):
        """
        Returns the state of the shelf's temperature using srx command temp

        """
        columns = ['location', 'temp']
        rdict = dict()

        r = self.run_and_check('temp')
        rs = r.message.splitlines()

        for line in rs:
            if not line or line.startswith(r'LOCATION'):
                continue
            ls = line.split()
            ps = dict(zip(columns, ls))
            rdict[ps['location']] = ps['temp']
        return rdict

    @property
    def power(self):
        """
        returns the state of the power supplies

        Version support: 6, 7
        """
        columns = ['psu', 'status', 'temp', 'fan1rpm', 'fan2rpm']
        rdict = dict()
        r = self.run_and_check('power')
        rs = r.message.splitlines()
        for line in rs:
            if not line or line.startswith(r'PSU'):
                continue
            ls = line.split()
            ps = dict(zip(columns, ls))
            rdict[ps['psu']] = ps
        return rdict

    def reboot(self):
        """
        Reboot the appliance

        Version support: 6, 7.
        """
        cmd = "reboot"
        if self.version >= 7:
            cmd = "reboot -f"
        s = self.run(cmd, wait=False)
        if s.find("error") != -1:
            return ReturnCode(False, s)
        sleep(1)
        return ReturnCode(True)

    def debug(self, setto):
        if self.version >= 7:
            # This code functionality depends on SRX-3460 get fixed.
            # cmd = '/debug %s' % setto
            r = self.expert_run('debug %s' % setto)
            logger.warning('setting debug to %s' % setto)
            return r
        else:
            logger.warning('setting debug to %s' % setto)
            cmd = "debug %s" % setto
        r = self.run_and_check(cmd)
        return r

    @property
    def ifstat(self):
        """
        Returns a dictionary of interfaces encoded as dictionaries::

            {'ether0': {'link': {'current': '1000', 'max': '1000'},
                'mac': '003048b92888',
                'name': 'ether0'},
            'ether1': {'link': {'current': '1000', 'max': '1000'},
                'mac': '003048b92889',
                'name': 'ether1'},
            'ether2': {'link': {'current': '0', 'max': '10000'},
                'mac': '003048da5b00',
                'name': 'ether2'},
            'ether3': {'link': {'current': '0', 'max': '10000'},
                'mac': '003048da5b01',
                'name': 'ether3'}}

        """
        cmd = 'ifstat'
        columns = ['name', 'mac', 'link']
        mheader = re.compile(r"NAME[ \t]*ADDR[ \t]*LINK \(Mbps\)[ \t]*MTU")
        oheader = re.compile(r"NAME[ \t]*ADDR[ \t]*LINK \(Mbps\)")
        r = self.run_and_check(cmd)
        rs = re.split(self.lineterm, r.message.strip())

        ifaces = dict()

        hfound = False
        for line in rs:
            if not hfound:
                if oheader.search(line):
                    hfound = True
                    if mheader.search(line):
                        columns = ['name', 'mac', 'link', 'mtu']
                    continue
            ls = line.split()
            if len(ls) > len(columns):
                current = ls[2]
                mx = ls[3]
                ls.pop(3)
                ls[2] = current + mx
            p = dict(zip(columns, ls))

            f = ['current', 'max']
            t = p['link'].split('/')
            p['link'] = dict(zip(f, t))
            ifaces[p['name']] = p

        return ifaces

    @property
    def fans(self):
        """
        Returns fan status as a dictionary.

        """
        d = dict()
        columns = ['fan', 'rpm']
        r = self.run_and_check('fans')
        if not r:
            return d
        rs = re.split(self.lineterm, r.message)
        for line in rs:
            if not line or line.startswith('FAN'):
                continue
            ls = line.split()
            p = dict(zip(columns, ls))
            d[p['fan']] = p['rpm']
        return d

    def _wipe_spare(self):
        """
        Removes all spare drives configured in this shelf.
        """
        if self.version >= 7:
            cmd = 'spares'
        else:
            cmd = 'spare'
        result = self.run_and_check(cmd)

        if result:
            r = result.message
            for line in re.split(self.lineterm, r):
                regExp = re.search(r'(\d+\.\d+)\s+.*', line)
                if regExp:
                    self.rmspare(regExp.group(1))

    def _wipe_cache(self):
        """
        Removes all cache drives configured in this shelf.
        """
        try:
            self.rmfcache()
        except ApplianceError as e:
            raise e

    def wipe(self, resetsize='-c'):
        """
        Remove all luns on this shelf.
        """
        while 1:

            luns = self.list
            if not luns:
                break
            for l in luns:
                if not l:
                    continue
                self.offline(l)
                self.remove(l, force=True)
        self._wipe_spare()
        self._wipe_cache()

        for d in range(self.slots):
            if getattr(self, 's%s' % d).get('Model'):
                self.setsize(resetsize, '{0}.{1}'.format(self.shelf, d))

    @property
    def maxsize(self):
        """
        Maxsize sums the disk capacity in the use_slots
        list for this SR.  It returns the value in bytes.

        """
        sz = 0
        if self.version >= 7:
            ddict = self.drives
        else:
            ddict = self.disks
        for d in ddict:
            if self.use_slots and not (d in self.use_slots):
                continue
            gl = ddict[d]['geometry'].split()
            nsect = int(gl[0])
            sectsz = int(gl[1])
            sz += nsect * sectsz
        return sz

    # TODO does this belong in this class?
    def diskmap(self, lun):
        """
        Return a dictionary with the shelf.slot with associated with
        the raid device index (lun.comp.drive).
        Returns a dictionary like::

            {'84.8':'7.0.0',
            '84.2':'7.0.1',
            '84.3':'7.0.2'}

        """
        dmap = dict()
        sh = self.shelf

        if self.version >= 7:
            s = self.expert_run("cat /raid/%s/raidstat" % lun)
            regex = re.compile(r"^([0-9]+\.[0-9]+\.[0-9]+)\s+[0-9]+\s+[a-zA-Z,]+\s+" +
                               "/(raiddev|sys/config)/([0-9]+|update)(/)?.*")
            lines = s.message.splitlines()

            for l in lines[1:]:
                m = re.match(regex, l)
                if m:
                    slot = m.group(3)
                    if slot == 'update':
                        slot = 'ramfs'
                    drive = "%s.%s" % (sh, slot)
                    dmap[drive] = m.group(1)
                else:
                    f = l.split()
                    if len(f) > 3 and f[3] != "missing":
                        logger.error("unhandled diskmap line: %s" % l)
        else:
            rs = self.run_and_check("cat /raid/%s/raidstat" % lun)
            lines = rs.message.splitlines()
            for l in lines[1:]:
                m = re.match(r"^([0-9]+\.[0-9]+\.[0-9]+) [0-9]+ " +
                             "[a-zA-Z\, ]+ \/raiddev\/([0-9]+)\/.*", l)
                if m:
                    dmap["%s.%s" % (sh, m.group(2))] = m.group(1)
                else:
                    f = l.split()
                    if len(f) > 3 and f[3] != "missing":
                        print "unhandled diskmap line: %s" % l

        return dmap

    def fail(self, disk, expectation=True):
        """
        This will fail the specified drive.

        """
        if self.version >= 7:
            return self.faildrive(drive=disk, expectation=expectation)
        else:
            logger.info("calling old code for disks command")
            return self._fail_6(disk, expectation)

    def _fail_6(self, disk, expectation=True):
        """
        Fail the specified disk.  Disk is in lun.part.element format. Returns a ReturnCode.
        """
        cmd = "fail %s" % disk
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def unfail(self, disk, expectation=True, slot=None):
        """
        Will unfail a drive.

        """
        if self.version >= 7:
            return self.replacedrive(disk, expectation, slot)
        else:
            logger.info("calling old code for unfail command")
            return self._unfail_6(disk, expectation)

    def _unfail_6(self, disk, expectation=True):
        """
        Un-fail the specified disk.  Disk is in lun.part.element format. Returns a ReturnCode.
        """
        cmd = "unfail %s" % disk
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def faildrive(self, drive, expectation=True):
        """
        Fail the specified drive.  Drive is in lun.part.element format.
        Returns a ReturnCode.
        """
        r = self.run_and_check("faildrive %s" % drive, expectation=expectation)
        return r

    @property
    def uptime(self):
        """
        Displays the amount of time the appliance has been running since the last reboot.

        """
        cmd = "uptime"
        r = self.run_and_check(cmd)
        return r.message

    @property
    def when(self):
        """
        Returns a dictionary::

            {'lun':'1.0'
            'percent': '44.06 '
            'rate': '83542.02'
            'time':'3:43:15'}

        """
        columns = ['lun', 'percent', 'rate', 'time']
        d = dict()
        r = self.run_and_check('when')

        if not len(r.message):
            return d

        for line in r.message.splitlines():
            if self.version >= 7:
                if not line or line.startswith('LUN'):  # header
                    continue
                ls = line.split()

                d[ls[0]] = dict(zip(columns, ls))
            else:
                ls = line.split()
                if len(ls) >= 6:
                    ls = ls[0], ls[1][:-1], ls[2], ls[4]  # remove non-data
                    d[ls[0]] = dict(zip(columns, ls))
        return d

    def update(self, reboot=True, lun=True, fname=None):
        """
        The update command updates the CorOS release on the appliance.

        If reboot is True, sets the '-r' flag, and forces a reboot.
        Either 'lun' can be True, or 'fname' can be a string of the
        already scp'd tarc name to use, but both 'lun' and 'fname' can not
        be set at the same time.  If neither is set, then returns the
        possibilities for updating, if any.  'fname' can be '-f' to get the
        update code to "find" the update fname.  Warning: it will find one
        (of possibly many) fname in /staging/, so you need to be sure
        there's only one there and that it's the one you want to use.

        """
        if self.version >= 7:
            if lun and fname:
                raise Exception("Srx.update(): both 'lun' and 'fname' should not be set.")
            wait = False
            cmd = "update"
            if reboot:
                cmd += " -r"
            if lun:
                cmd += " "  # 7.0 release mandated that, update = update lun
            elif fname:
                cmd += " %s" % fname
            else:
                wait = True
            r = self.run(cmd, wait=wait)
            if wait:  # will only be True if 'lun' and 'fname' are not set
                tarc = re.compile(r"^SRX\-[0-9]+\.[0-9]+\.[0-9]+\-R[0-9]+\.tarc")
                for line in re.split(self.lineterm, r):
                    if line.find("No update files found") != -1:
                        break
                    if re.match(tarc, line):
                        r = line.strip()
                        break
            elif reboot:
                # wait for the CLI message that assures we
                # won't be allowed to run further CLI commands
                self.expect(["System rebooting ...", TIMEOUT], timeout=120)
        else:
            cmd = "update -f"
            r = self.run(cmd, wait=False)
        return r

    def disktest(self, mode, disk, expectation=True):
        """
        Destructive read/write test of a drive.

        """

        cmd = "disktest %s %s" % (mode, disk)
        try:
            if self.version >= 7:
                r = self.expert_run(cmd, expectation=expectation)
            else:
                r = self.run_and_check(cmd, expectation=expectation)
        except ApplianceError as e:
            raise e
        return r

    def setsize(self, size, drives):  # TODO: file SR bug: size is not optional
        """
        Makes a drive looks lower than or equal to drive size.

        size = '-c' means restore the disk to its actual size
        drives can be a string or a list of strings

        """
        if type(drives) is list:
            drives = ' '.join(drives)
        if self.version >= 7:
            cmd = "/setsize %s %s" % (size, drives)
        else:
            cmd = "setsize %s %s" % (size, drives)
        return self.run_and_check(cmd)

    @property
    def mask(self):
        """
        Returns a dictionary with a list of macs per LUN.

        """
        d = dict()
        r = self.run_and_check('mask')

        if not r:
            return d

        masks = re.split(self.lineterm, r.message)
        for line in masks:
            if not line or line.startswith('LUN'):
                continue
            ls = line.strip().split()
            if len(ls) > 1:
                d[ls[0]] = ls[1:]
        return d

    @mask.setter
    def mask(self, maskstring):
        """
        Mask a Lun
        Unfortunately, the interface remained the same, but the order of arguments between
        SRX-6.x and SRX-7.x were reversed, and we have to figure it out here.

        SRX-6.x usage:
            mask lun ... [ +mac ... ] [ -mac...]
        SRX-7.x usage:
            mask [ {+|-} mac ... ] [ lun ... ]

        """

        if self.version >= 7:
            luns = str()
            args = str()
            for arg in maskstring.split():
                if arg[0] == '+' or arg[0] == '-':
                    args += ' ' + arg
                else:  # we have to assume it's a lun
                    luns += ' ' + arg
            cmd = "mask %s %s" % (args, luns)
            r = self.run_and_check(cmd)
            if not r:
                logger.error(r.message)
        else:
            maskstring = maskstring.split()
            lun = maskstring[0].strip()
            for curr in maskstring[1:]:
                if curr[0] == "+":
                    cmd = "echo mask %s > /raid/%s/ctl" % (curr[1:], lun)
                    self.run_and_check(cmd)
                elif curr[0] == "-":
                    cmd = "echo rmmask %s > /raid/%s/ctl" % (curr[1:], lun)
                    self.run_and_check(cmd)

    @property
    def iostats(self):
        """
        Returns io statistics for each lun and it's underlying disks::

            {'10': {'id': '10',
              'kind': 'lun',
              'read': {'MB': '0.000', 'avg': '0', 'max': '0'},
              'write': {'MB': '0.000', 'avg': '0', 'max': '0'}},
             '10.0.0': {'id': '10.0.0',
              'kind': 'disk',
              'read': {'MB': '0.677', 'avg': '2', 'max': '15'},
              'write': {'MB': '0.000', 'avg': '0', 'max': '0'}},
             '10.0.1': {'id': '10.0.1',
              'kind': 'disk',
              'read': {'MB': '0.677', 'avg': '1', 'max': '20'},
              'write': {'MB': '0.000', 'avg': '0', 'max': '0'}}
            }

        """
        d = dict()
        r = self.run_and_check('iostats')

        if not r:
            return d

        if not self.sample_warn:
            self.sample_warn = re.compile(
                r"warning:[ \t]*iosample[ \t]*smaller[ \t]*than[ \t]*requested[ \t]*\[1 != 3\]")

        rs = r.message.splitlines()
        headerlen = 8
        columns = ['id', 'read', 'write', 'kind']

        for line in rs:
            if not line or line.startswith('LUN'):
                continue
            if self.sample_warn.search(line):
                continue
            ls = line.split()
            if len(ls) < headerlen - 1:
                continue
            m = ls[0]  # the first token on the line
            dots = m.count(".")
            rd = {'MB': ls[1].split('MB')[0], 'avg': ls[2].split('ms')[0], 'max': ls[3].split('ms')[0]}
            wd = {'MB': ls[4].split('MB')[0], 'avg': ls[5].split('ms')[0], 'max': ls[6].split('ms')[0]}
            if dots:
                kind = 'disk'
            else:
                kind = 'lun'
            entry = [ls[0], rd, wd, kind]
            p = dict(zip(columns, entry))
            d[p['id']] = p
        return d

    @property
    def sysstat(self):
        """
        Return the utilization of each cpu in a dict::

            {'0': {'cpu': '0', 'idle%': '99', 'int%': '0'},
             '1': {'cpu': '1', 'idle%': '99', 'int%': '0'},
             '2': {'cpu': '2', 'idle%': '98', 'int%': '0'},
             '3': {'cpu': '3', 'idle%': '99', 'int%': '0'}}

        """
        if self.version >= 7:
            ret = self.expert_run('sysstat', expectation=False)
        else:
            cmd = "sysstat"
            ret = self.run_and_check(cmd)

        statd = dict()
        if ret:
            r = re.split('(?:\r+\n){2}', ret.message.strip())
            for cpu in r:
                curr = dict()
                for fld in re.split(self.lineterm, cpu):
                    k, v = fld.split('=')
                    curr[k] = v
                statd[curr['cpu']] = curr
        return statd

    def smartdisable(self, drives, expectation=True):
        """
        drives is either a single drive as a string, or a list of drives as strings.
        drives can also be a series-expanded set of drives as a string, eg: '43.0-23'.
        Returns a ReturnCode.
        """
        if type(drives) == list:
            drives = ' '.join(drives)
        cmd = "smartdisable %s" % drives
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def smartenable(self, drives, expectation=True):
        """
        drives is either a single drive as a string, or a list of drives as strings.
        drives can also be a series-expanded set of drives as a string, eg: '43.0-23'.
        Returns a ReturnCode.
        """
        if type(drives) == list:
            drives = ' '.join(drives)
        cmd = "smartenable %s" % drives
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    @property
    def iomode(self):
        """
        'Luns' should either be a string or a list of strings.
        Return a dictionary with iomode information::

            {'0': {'lun': '0', 'mode': 'sequential'},
             '1': {'lun': '1', 'mode': 'random'},
             '2': {'lun': '2', 'mode': 'random'}}

        """
        d = dict()
        r = self.run_and_check('iomode')
        if not r:
            return d
        for line in r.message.splitlines():
            if not line or line.startswith('LUN'):
                continue
            lun, mode = line.split()
            d[lun] = {'lun': lun, 'mode': mode}
        return d

    def setiomode(self, mode, lun, expectation=True):
        """
        Change the io access mode of a lun or list of luns.
        """

        if type(lun) == list:
            lun = ' '.join(lun)
        cmd = "setiomode %s %s" % (mode, lun)
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def cecenable(self, ifs):
        """
        'ifs' is expected to be a single interface as
        a string, or a list of interfaces as strings.
        Returns a ReturnCode.

        Version support: 7
        """
        if type(ifs) == list:
            ifs = ' '.join(ifs)
        return self.run_and_check('cecenable %s' % ifs)

    def cecdisable(self, ifs):
        """
        'ifs' is expected to be a single interface as
        a string, or a list of interfaces as strings.
        Returns a ReturnCode.

        Version support: 7
        """
        if type(ifs) == list:
            ifs = ' '.join(ifs)
        return self.run_and_check('cecdisable %s' % ifs)

    @property
    def cecstat(self):
        """
        Returns a dictionary containing available interfaces and
        the cec state for each one (enabled or disabled).
        For example, this on the CLI::

            SRX shelf 43> cecstat
            NAME              CEC
            ether0       disabled
            ether1        enabled
            ether2       disabled
            ether3       disabled
            ether4       disabled
            SRX shelf 43>

        returns this::

            {   'ether0': {   'ifc': 'ether0', 'status': 'disabled'},
                'ether1': {   'ifc': 'ether1', 'status': 'enabled'},
                'ether2': {   'ifc': 'ether2', 'status': 'disabled'},
                'ether3': {   'ifc': 'ether3', 'status': 'disabled'},
                'ether4': {   'ifc': 'ether4', 'status': 'disabled'}}

        Version support: 7
        """
        d = dict()
        r = self.run_and_check('cecstat')
        if not r:
            return d
        lines = r.message.splitlines()
        for line in lines:
            if not line or line.startswith('NAME'):
                continue
            flds = line.split()
            if len(flds) < 2:
                logger.error("parsing failure: '%s'" % line)
                continue
            ifc = flds[0]
            d[ifc] = {'ifc': ifc, 'status': flds[1]}
        return d

    def replace(self, comp, drive, expectation=True):
        """
        Replace a filed drive..

        """

        if self.version >= 7:
            return self.replacedrive(comp, expectation, drive)
        else:
            return self._replace_6(comp, drive, expectation)

    def _replace_6(self, comp, drive, expectation=True):
        """
        Replace a failed drive.  Can replace itself.
        comp is in 'lun.part.element' format, drive is in 'shelf.slot' format.
        Returns a ReturnCode.
        """
        cmd = "replace %s %s" % (comp, drive)
        return self.run_and_check(cmd, expectation=expectation)

    def replacedrive(self, drive, expectation=True, slot=None):  # Check this last parameter for None
        """
        Replace a failed component with a new drive (or possibly itself).
        comp is expected to be in 'lun.part.drive' format.  Returns a ReturnCode.
        """
        if not slot:
            slot = "%s.%s" % (self.shelf, drive.split('.')[-1])
        r = self.run_and_check("replacedrive %s %s" % (drive, slot), expectation=expectation)
        if not r and expectation:
            raise ApplianceError(r.message)
        return r

    def resetdrive(self, drives, expectation=True):
        """
        This is only useful when drives enter a connectfail state.
        'Drives' is expected to be a string or a list of strings.
        Returns a ReturnCode.

        Version support: 7
        """
        if type(drives) == list:
            drives = ' '.join(drives)
        r = self.run_and_check("resetdrive %s" % drives)
        if not r and expectation:
            raise ApplianceError(r.message)
        return r

    def eject(self, luns, expectation=True):
        """
        This will eject one or more luns.

        Similar to the remove command, but eject does not clear the RAID config on the component drives of a lun.

        Returns a ReturnCode.
        """
        if self.version >= 7:
            return self.ejectlun(luns, expectation)
        else:
            logger.info("calling old code for eject command")
            return self._eject_6(luns, expectation)

    def _eject_6(self, luns, expectation=True):
        if type(luns) == dict:
            luns = aoetostr(luns)
        elif type(luns) == list:
            luns = ' '.join(luns)
        else:
            luns = str(luns)
        cmd = 'eject -f %s' % luns
        return self.run_and_check(cmd, expectation)

    def ejectlun(self, luns, expectation=True):
        """
        This will eject one or more luns.
        """
        if type(luns) == dict:
            luns = aoetostr(luns)
        elif type(luns) == list:
            luns = ' '.join(luns)
        else:
            luns = str(luns)
        cmd = 'ejectlun -f %s' % luns
        return self.run_and_check(cmd, expectation)

    def restore(self, oldshelf=None, oldlun=None, newlun=None, flagl=None, expectation=True):
        """
        This will restore a lun reading drives's config in an SRX.
        """

        if self.version >= 7:
            return self.restorelun(oldshelf, oldlun, newlun, flagl, expectation)
        else:
            return self._restore_6(oldshelf, oldlun, newlun, flagl, expectation)

    def _restore_6(self, oldshelf=None, oldlun=None, newlun=None, flagl=None, expectation=True):
        cmd = "restore"
        if flagl:
            cmd += " -l"
        if oldshelf:
            cmd += " %s" % oldshelf
        if oldlun:
            cmd += " %s" % oldlun
        if newlun:
            cmd += " %s" % newlun
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def restorelun(self, oldshelf=None, oldlun=None, newlun=None, flagl=None, expectation=True):
        """
        Returns a ReturnCode.
        usage: restorelun [ -l ] [ oldshelfno [ oldlun [ newlun ] ] ]

        Version support: 7
        """
        cmd = "restorelun"
        if flagl:
            cmd += " -l"
        if oldshelf:
            cmd += " %s" % oldshelf
        if oldlun:
            cmd += " %s" % oldlun
        if newlun:
            cmd += " %s" % newlun
        r = self.run_and_check(cmd, expectation=expectation)
        return r

    def setslotled(self, state, slots, expectation=True):
        """
        'Slots' is either a string or a list of strings.
        Returns a ReturnCode

        """
        if type(slots) == list:
            slots = ' '.join(slots)
        r = self.run_and_check("setslotled %s %s" % (state, slots), expectation=expectation)
        return r

    def slotled(self, slots=None, expectation=True):
        """
        'Slots' is either a string or a list of strings.
        Returns a dictionary.

        """
        d = dict()
        if not slots:
            slots = str()
        elif type(slots) == list:
            slots = ' '.join(slots)
        r = self.run_and_check("slotled %s" % slots, expectation=expectation)
        if not r:
            return d
        lines = re.split(self.lineterm, r.message)
        for line in lines:
            if not line or line.startswith('SLOT'):
                continue
            flds = line.split()
            if len(flds) < 2:
                logger.error("parsing error: %s" % line)
                continue
            d[flds[0]] = {'slot': flds[0], 'state': flds[1]}
        return d

    def smartlog(self, drives=None):
        """
        'Drives' can either be a string or a list of strings.
        Returns a dictionary of drives and any associated S.M.A.R.T info.

        Version support: 7
        """
        d = dict()
        if not drives:
            drives = str()
        elif type(drives) == list:
            drives = ' '.join(drives)
        r = self.run_and_check("/smartlog %s" % drives)
        if not r:
            return d
        drive = None
        drivehdr = re.compile(r"^(\d+\.\d+)\s+([a-zA-Z0-9\-_]*)\s+(.*)")
        info = re.compile(r"^\s+(.*)")
        lines = re.split(self.lineterm, r.message)
        for line in lines:
            if not line or line.startswith('DRIVE'):
                continue
            m = re.search(drivehdr, line)
            if m:
                drive = m.group(1)
                d[drive] = {'drive': drive}
                d[drive]['model'] = m.group(2)
                d[drive]['fw'] = m.group(3).strip('\r')
                d[drive]['log'] = str()
                continue
            m = re.search(info, line)
            if m:
                if not drive:
                    logger.error("parsing failure: %s" % line)
                    continue
                d[drive]['log'] += m.group(1)
        return d

    @property
    def spareled(self, expectation=True):
        """
        Returns a string; either 'enabled' or 'disabled'.
        """
        if self.version >= 7:
            cmd = '/spareled'
        else:
            cmd = 'spareled'
        r = self.run_and_check(cmd, expectation=expectation)
        return r.message

    @spareled.setter
    def spareled(self, state, expectation=True):
        """
        Sets whether the spares' leds will flash or not.
        """
        if state != 'enable' and state != 'disable':
            raise ApplianceUsage("you're doing it wrong!")
        if self.version >= 7:
            cmd = '/spareled'
        else:
            cmd = 'spareled'
        self.run_and_check('{0} {1}'.format(cmd, state), expectation=expectation)

    @property
    def syslog(self):
        """
        Returns a dictionary of source, server and local interface::

            {'source': '10.176.200.87',
             'server': '10.176.110.1',  # destinantion
             'interface': 'ether0'}

        """
        if self.version >= 7:
            return self._syslog_7
        else:
            return self._syslog_6

    @property
    def _syslog_7(self):
        d = {'source': 'unset', 'server': 'unset', 'interface': 'ether0'}
        r = self.run_and_check('syslog')
        if not r:
            return d
        lines = re.split(self.lineterm, r.message.strip())
        if len(lines) < 2:
            logger.error("parsing failure: '%s'" % r.message)
            return d
        flds = lines[1].split()
        if len(flds) < 2:
            logger.error("parsing failure: '%s'" % lines[1])
            return d
        d = {'source': flds[0], 'server': flds[1]}
        return d

    @property
    def _syslog_6(self):
        d = {'source': 'unset', 'server': 'unset', 'interface': 'ether0'}
        r = self.run_and_check('syslog -p')
        if not r:
            return d
        lines = re.split(self.lineterm, r.message.strip())
        d = {'source': lines[1].split(':')[1].strip(), 'server': lines[0].split(':')[1].strip(),
             'interface': lines[2].split(':')[1].strip()}
        return d

    @syslog.setter
    def syslog(self, syslog=None):
        """
        Takes a single syslog server IP or a dict as input::

            {'source': '10.176.200.87',
             'server': '10.176.110.1',  # destinantion
             'interface': 'ether0'}

        """
        s = dict()
        if type(syslog) is not dict:
            s['server'] = syslog
            s['source'] = ""
            s['interface'] = 'ether0'
        else:
            s = syslog
        if self.version >= 7:
            return self.run_and_check('syslog %s' % s['server'])
        else:
            result = ReturnCode(True)
            # Configure destination IP
            self.run('syslog -c', force=True, ans=s['server'])
            result.message = self.run(s['source'], force=True, ans=s['interface'])
            logger.info(result.message)

    def syslogtest(self, msg, sev=None):
        """
        Send a test syslog message
        """
        if self.version >= 7:
            return self.run_and_check('syslogtest %s' % msg)
        else:
            if sev is None:
                sev = ''
            else:
                sev = '-s {0}'.format(sev)
            return self.run_and_check('syslog {0} {1}'.format(sev, msg))

    def label(self, name, luns, expectation=True):
        """
        Place a label on the requested LUN(s).
        'Luns' is either a string or a list of strings.
        """
        if type(luns) == list:
            luns = ' '.join(luns)
        return self.run_and_check('label %s %s' % (name, luns), expectation)

    def unlabel(self, luns, expectation=True):
        """
        Removes any label from the requested LUN(s).
        'Luns' is either a string or a list of strings.
        """
        if type(luns) == list:
            luns = ' '.join(luns)
        return self.run_and_check('unlabel %s' % luns, expectation)

    def setvlan(self, vlanid, luns, expectation=True):
        """
        Sets the vlanid for the given LUN(s).
        A valid vlan id is a number between 1 and 4094 (inclusive).
        'Luns' is either a string or a list of strings.  Returns a ReturnCode.

        Version support: 7
        """
        if type(luns) == list:
            luns = ' '.join(luns)
        cmd = "setvlan %s %s" % (vlanid, luns)
        return self.run_and_check(cmd, expectation=expectation)

    def clrvlan(self, luns, expectation=True):
        """
        Clears any vlan id for the given LUN(s).

        Version support: 7
        """
        if type(luns) == list:
            luns = ' '.join(luns)
        return self.run_and_check("clrvlan %s" % luns, expectation=expectation)

    def vlans(self, luns=None):
        """
        Returns a dictionary of VLANs for the specified LUNs, or all LUNs on the shelf.
        Any LUN that is not a part of a VLAN gets an empty value in the VLAN column.

        Version support: 7
        """
        if not luns:
            luns = str()
        if type(luns) == list:
            luns = ' '.join(luns)
        d = dict()
        r = self.run_and_check('vlans %s' % luns)
        if not r:
            return d
        lines = re.split(self.lineterm, r.message)
        for line in lines:
            if not line or line.startswith('LUN'):
                continue
            flds = line.split()
            d[flds[0]] = {'lun': flds[0], 'vlan': None}
            if len(flds) > 1:
                d[flds[0]]['vlan'] = flds[1]
        return d

    def lunfailguarddisable(self, lun, expectation=True):
        """
        Disable fail guard on specified lun.
        """
        if self.version >= 7:
            return self._lunfailguarddisable(lun, expectation)
        else:
            return self._lunfailguarddisable_6(lun, expectation)

    def _lunfailguarddisable(self, lun, expectation=True):
        """
        Disable fail guard on specified lun.
        Don't call this directly.  Call lunfailguarddisable instead.
        """
        cmd = "/lunfailguarddisable -f %s" % lun
        return self.run_and_check(cmd, expectation)

    def _lunfailguarddisable_6(self, lun, expectation=True):
        """
        Disable fail guard on specified lun.
        Don't call this directly.  Call lunfailguarddisable instead.
        """
        cmd = "setlunfailguard -f off %s" % lun
        return self.run_and_check(cmd, expectation)

    def lunfailguardenable(self, lun, expectation=True):
        """
        Enable fail guard on specified lun.
        """
        if self.version >= 7:
            return self._lunfailguardenable(lun, expectation)
        else:
            return self._lunfailguardenable_6(lun, expectation)

    def _lunfailguardenable(self, lun, expectation=True):
        """
        Enable fail guard on specified lun.
        Don't call this directly.  Call lunfailguardenable instead.
        """
        cmd = "/lunfailguardenable -f %s" % lun
        return self.run_and_check(cmd, expectation)

    def _lunfailguardenable_6(self, lun, expectation=True):
        """
        Enable fail guard on specified lun.
        Don't call this directly.  Call lunfailguardenable instead.
        """
        cmd = "setlunfailguard -f on %s" % lun
        return self.run_and_check(cmd, expectation)

    @property
    def timezone(self):
        """
        The timezone command returns a string containing the srx timezone.

        Version support: 7
        """
        if self.version >= 7:
            cmd = "timezone"
            r = self.run_and_check(cmd)
            out = r.message
            timezone = out.split()[1]
        else:
            raise ApplianceUsage("The 'timezone' command doesn't exist for SRX 6.x and lower.")
        return timezone

    @timezone.setter
    def timezone(self, timezone):
        """
        Change the timezone

        Version support: 7
        """
        if self.version >= 7:
            cmd = 'timezone %s' % timezone
            self.run_and_check(cmd)
        else:
            raise ApplianceUsage("The 'timezone' command doesn't exist for SRX 6.x and lower.")

    @property
    def timezones(self):
        """
        The timezones command returns a list containing the available timezones.

        Version support: 7
        """

        if self.version >= 7:
            cmd = "timezone -l"
            r = self.run_and_check(cmd)
            out = r.message
            timezones = out.split()
            timezones.remove("Available")
            timezones.remove("timezones:")
        else:
            raise ApplianceUsage("The 'timezone' command doesn't exist for SRX 6.x and lower.")

        return timezones

    @property
    def timezone_list(self):
        return self.timezones

    @property
    def service(self):
        """
        The service property returns a dictionary of services::

            {'ftp': {'name': 'ftp', 'status': 'enabled'},
             'ntp': {'name': 'ntp', 'status': 'disabled'},
             'ssh': {'name': 'ssh', 'status': 'enabled'}}

        Version support: 7
        """
        services = {}
        if self.version >= 7:
            cmd = "service"
            r = self.run_and_check(cmd)
            lines = re.split(self.lineterm, r.message.strip())
            for line in lines:
                line = line.strip()
                if not line or line.startswith('SERVICE'):
                    continue
                name, status = line.split()
                services[name] = {}
                services[name]['name'] = name
                services[name]['status'] = status
        else:
            raise ApplianceUsage("The 'service' command doesn't exist for SRX 6.x and lower.")
        return services

    def disable_service(self, service, expectation=True):
        """
        Disable a service

        Version support: 7
        """
        if self.version >= 7:
            if service not in ('ftp', 'ntp', 'ssh'):
                raise ApplianceUsage("unknown service: %s" % service)
            cmd = "service %s disable" % service
            return self.run_and_check(cmd, expectation)
        else:
            raise ApplianceUsage("The 'service' command doesn't exist for SRX 6.x and lower.")

    def enable_service(self, service, expectation=True):
        """
        Enable a service

        Version support: 7
        """
        if self.version >= 7:
            if service not in ('ftp', 'ntp', 'ssh'):
                raise ApplianceUsage("unknown service: %s" % service)
            cmd = "service %s enable" % service
            return self.run_and_check(cmd, expectation)
        else:
            raise ApplianceUsage("The 'service' command doesn't exist for SRX 6.x and lower.")

    def _set_disks(self, diskd):
        self.cache['disks'] = diskd
        for slot, data in diskd.iteritems():
            setattr(self, "s%s" % slot, Namespace(data))

    def _enumerate_slots(self):
        cmd = "ls /raiddev/| grep [0-9]+ | wc -l"
        ret = self.expert_run(cmd)
        if ret:
            return int(ret.message)
        else:
            raise ApplianceError("can't enumerate slots:%s\n returns\n%s" % (cmd, ret.message))


class SrxApplcon(Srx):
    """
    Creates an Srx object that uses a specified gateway vsx to connect.  This
    will allow multiple users to control the Srx without interfering with one
    another.

    """

    def __init__(self, vsxuser, vsxaddr, vsxpassword, shelf, use_slots=None):
        self.vsx = Vsx(self.user, self.vsxaddr, self.password)
        self.run = self.vsx.run
        self.user = vsxuser
        self.vsxaddr = vsxaddr
        self.shelf = shelf
        self.prompt = '(LD|SR|SRX)\sshelf\s(unset|\d.*)>'
        self.sample_warn = None
        self.confirm = None
        self.confirm_update_lun_format = None
        self.host = self.shelf
        self.use_slots = use_slots
        self.password = vsxpassword
        self.closed = True  # since we didn't call __spawn

        self.lineterm = '\r+\n'
        self.driveahdr = None
        self.sample_warn = None
        self.confirm = None
        self.confirm_update_lun_format = None
        self.cache = dict()

    def connect(self, timeout=40, args=None):
        """
        connect to a vsx and tunnel through applcon
        """

        if args == 'esm':
            self.vsx.prompt = r'ESM IP \d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}>'
        self.vsx.connect()

        if args == 'esm':
            self.vsx.prompt = r'ESM EXPERTMODE# '
        else:
            self.vsx.prompt = 'VSX EXPERTMODE# '
        self.vsx.run('/expertmode')

        self.vsx.prompt = self.prompt
        r = self.vsx.run("applcon %s" % self.shelf)
        if r:
            self.closed = False

            version = self.run('release')
            if version.startswith('RELEASE'):
                version = r.split()[-1]

            result = re.match(r"^SR[X]?-([0-9]+)\.([0-9]+).*", version)
            if result:
                self.version = int(result.group(1))
            else:
                raise ApplianceError('Unable to identify SRX version running in shelf: %s: %s' % (result, r))

        return r

    @property
    def match_index(self):
        return self.vsx.match_index


class SrxSsh(Ssh, Srx):
    """
    A class for interacting with the Srx using ssh.
    Since the commands are basically passed through
    see the Srx manual for more info.

    extended parameters::

        expectation     (Boolean) if False the library will not raise exceptions for error: or usage:
        force           (Boolean) if True the method walks through the acceptance dialog

    """

    def __init__(self, user, host, password, prompt=None, use_slots=None):
        self.user = user
        self.host = host
        self.password = password
        self.striped = False
        self.prompt = prompt
        self.version = 7
        if prompt is None:
            self.prompt = 'SRX\sshelf\s(unset|inactive|\d.*)>\s'
        self.sample_warn = None
        self.confirm = None
        self.confirm_update_lun_format = None
        self.cache = dict()
        self.lineterm = '\r+\n'
        self.driveahdr = None
        self.use_slots = use_slots
        self.connected = False

    def connect(self, timeout=40, args=None):
        """
        Calls Ssh's connection method which will connect to and authenticate with host
        """
        ret = super(SrxSsh, self).connect(timeout=timeout, args=None)
        if ret:
            self.connected = True
            ret = self.run_and_check('shelf')
            if ret:
                self.shelf = ret.message.strip()

        self.slots = self._enumerate_slots()

        for slot in range(int(self.slots)):
            setattr(self, 's%s' % slot, Drive(self.shelf, slot, self.expert_run))

        return ret

    def disconnect(self):
        """
        Calls Ssh's disconnect method
        """
        return super(SrxSsh, self).disconnect()

    def reconnect(self, after=10, timeout=40, attempts=10):
        """
        Calls Ssh's reconnection method which will reconnect to and authenticate with host
        """
        # Needs to be removed
        sleep(3 * 60)  # srx 7 takes about 3 minutes to reboot
        failed = 0
        if timeout is None:
            timeout = self.timeout

        self.connected = False
        self.close()
        start = now()
        while not self.connected:
            sleep(after)
            try:
                if self.connect(timeout=timeout):
                    break
                else:
                    if failed > attempts:
                        raise ApplianceError
                    else:
                        failed += 1
            except (TIMEOUT, EOF) as e:
                self.connected = False
                self.close()
        logger.debug("reconnected after %s" % timefmt(since(start)))
        return True
