#!/usr/bin/env python
# encoding: utf-8
"""
Basic Usage::

        from otto.appliances import vsx

        s = vsx(uname, host, passwd)
        s.connect()
        print(s.release)
        s.disconnect()

Anytime a target is a parameter to a method the target can be
specified as a string::

    "22.7"

or a dictionary in the form of::

    {'shelf': '22',
     'slot': '7'}

"""

import re
import os
import logging
import time

from otto.connections.ssh_pexpect import Ssh
from otto.lib.otypes import ApplianceError, ApplianceUsage, ReturnCode, AoEAddress
from otto.utils import aoetostr, strtoaoe, mkcmdstr

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.appliances')
logger.addHandler(logging.NullHandler())


class Vsx(Ssh):
    """
    A class for interacting with the vsx using ssh.
    Since the commands are basically passed through
    see the vsx manual for more info.

    extended parameters::

        expectation     (Boolean) if False the library will not raise exceptions for error: or usage:
        force           (Boolean) if True the method walks through the acceptance dialog

    """

    def __init__(self, user, host, password, prompt=None):
        self.user = user
        self.host = host
        self.password = password
        self.striped = False
        self.prompt = prompt
        if prompt is None:
            self.prompt = 'VSX\sshelf\s(unset|inactive|\d.*)>\s'
        self.use_pvs = None  # used only in Vsx.pvs method

    def connect(self, timeout=40, args=None):
        """
        Calls parent's connection method which will connect to and authenticate with host
        """
        return super(Vsx, self).connect(timeout=timeout, args=None)

    def run_and_check(self, cmd, expectation=True, force=False):
        """
        Run a command check the result.  If the caller cares about failure
        and the command fails we raise a generic exception.
        """
        result = ReturnCode(True)
        confirm = re.compile("Enter[ \t]*\'y\'*.")
        logger.info(cmd + " called")

        if force:
            t = self.prompt
            self.prompt = confirm
            self.run(cmd)
            self.prompt = t
            result.message = self.run('y')

        else:
            result.message = self.run(cmd)

        e = Exception()

        if result.message.startswith('error:'):
            if expectation:
                logger.error(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = ApplianceError(failmsg)

        elif result.message.startswith('usage:'):
            if expectation:
                logger.critical(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = ApplianceUsage(failmsg)
            result.status = False

        if not expectation:
            return result
        elif not result.status:
            raise e
        return result

    def expert_run(self, cmd):
        tprompt = self.prompt
        self.prompt = 'VSX EXPERTMODE# '
        self.run('/expertmode')
        self.run(cmd)
        self.prompt = tprompt
        self.run('exit')

    @property
    def release(self):
        """
        Returns a string containing
        the currently running CorOS release.
        """
        result = self.run_and_check('release')
        rel = result.message
        if rel.startswith('RELEASE'):
            rel = rel.split('\r\n')[1].strip()
        return rel

    @property
    def ifstat(self):
        """
        Returns a dictionary of interfaces encoded as dictionaries. e.g.::

            {'ether0':{'link': {'current': '1000', 'max': '1000'},
                        'mac': '0025900a856c',
                        'name': 'ether0'},
            'ether1':{'link': {'current': '0', 'max': '1000'},
                        'mac': '0025900a856d',
                        'name': 'ether1'}}

        """

        r = self.run_and_check('ifstat')
        rs = r.message.split('\r\n')
        columns = ['name', 'mac', 'link']
        header = re.compile(r"NAME[ \t]*ADDR[ \t]*LINK \(Mbps\)")
        ifaces = dict()

        hfound = False
        for line in rs:
            if not hfound:
                if header.search(line):  # TODO: This could be optimized
                    hfound = True
                    continue
            ls = line.split()
            p = dict(zip(columns, ls))
            f = ['current', 'max']
            t = p['link'].split('/')
            p['link'] = dict(zip(f, t))
            ifaces[p['name']] = p

        return ifaces

    def aoediscover(self):
        """
        aoediscover
        """
        return self.run_and_check("aoediscover")

    def aoeflush(self):
        """
        aoeflush
        """
        return self.run_and_check("aoeflush")

    @property
    def aoestat(self):
        """
        Returns a dictionary of aoe targets encoded as dictionaries eg.::

             {'8.8': {'address': {'shelf': '8', 'slot': '8'},
                     'config': '',
                     'ifaces': ['ether2,', 'ether6'],
                     'paths': [{'iface': 'ether2', 'mac': '003048b92888'},
                               {'iface': 'ether6', 'mac': '003048b92888'},
                               {'iface': 'ether2', 'mac': '003048b92889'},
                               {'iface': 'ether6', 'mac': '003048b92889'}],
                     'size': '80.026'},
             '8.9': {'address': {'shelf': '8', 'slot': '9'},
                     'config': '',
                     'ifaces': ['ether2,', 'ether6'],
                     'paths': [{'iface': 'ether2', 'mac': '003048b92888'},
                               {'iface': 'ether6', 'mac': '003048b92888'},
                               {'iface': 'ether2', 'mac': '003048b92889'},
                               {'iface': 'ether6', 'mac': '003048b92889'}],
                     'size': '80.026'}}

        """
        header = re.compile(r"TARGET[ \t]*SIZE\(GB\)[ \t]*PORT\(S\)")
        na = re.compile(r"error: target ([0-9]*\.)?[0-9]+ is currently not available")
        cmd = "aoestat -a"

        r = self.run_and_check(cmd)
        r = r.message  # TODO need to check the first line for na error and handle it

        targets = dict()
        if r.startswith('aoestat:'):  # TODO: File a bug this should be error:
            logger.error(r)
            return targets
        rs = r.split('\r\n')
        if not len(rs):
            return targets

        lun = r"^([0-9]+\.[0-9]+)[ \t]+([0-9]+\.[0-9]+)[ \t]+(.*)"
        mac = r"^[ \t]+([0-9A-Fa-f]{12})[ \t]+(.*)"
        config = r"^[ \t]+Config string:[ \t]*(.*)"
        serial = r"^[ \t]+Serial number:[ \t]*(.*)"
        snconflict = r"^[ \t]+Serial number conflict:[ \t]*(.*)"
        retries = r"^[ \t]+retries:[ \t]*(.*)"

        udt = dict()
        udt['lun'] = {'re': lun, 'name': 'lun'}
        udt['mac'] = {'re': mac, 'name': 'mac'}
        udt['config'] = {'re': config, 'name': 'config'}
        udt['serial'] = {'re': serial, 'name': 'serial'}
        udt['snconflict'] = {'re': snconflict, 'name': 'snconflict'}
        udt['retries'] = {'re': retries, 'name': 'retries'}

        hfound = False
        thistarg = None
        for line in rs:
            if not hfound:
                if header.search(line):
                    hfound = True
                    continue
            if line.startswith('error:'):
                if na.match(line):
                    continue
                else:
                    e = ApplianceError(line)
                    raise e

            targ = dict()
            for k in udt.keys():
                m = re.match(udt[k]['re'], line)
                if m:
                    name = udt[k]['name']
                    if name == 'lun':
                        addr = m.group(1)
                        targ['address'] = strtoaoe(addr)
                        targ['size'] = m.group(2)
                        targ['ifaces'] = m.group(3).split()  # TODO: is it space separated, or comma, or both?
                        targets[addr] = targ
                        thistarg = targ
                    elif name == 'mac':
                        if not thistarg:
                            logger.error("thistarg == None (mac)")
                            continue
                        x = thistarg.get('paths', list())
                        path = {'mac': m.group(1), 'iface': m.group(2)}
                        # check if a MAC address appears on multiple interfaces
                        ifaces = path['iface'].split(',')
                        if len(ifaces) > 1:
                            # create separate entries for each path
                            pl = list()
                            for j in ifaces:
                                p = {'mac': path['mac'], 'iface': j.strip()}
                                pl.append(p)
                        else:
                            pl = [path]
                        x.extend(pl)
                        thistarg['paths'] = x
                    elif name in ('config', 'serial', 'snconflict', 'retries'):
                        if not thistarg:
                            logger.error("thistarg == None (%s)" % name)
                            continue
                        thistarg[name] = m.group(1)
                    else:
                        logger.error("Vsx.aoestat match, but unexpected: \n\t%s" % line)
        return targets

    def mkpool(self, poolname, expectation=True, striped=False):
        """
        Creates a pool with the name secified by poolname. Returns a Boolean.
        """
        cmd = mkcmdstr('mkpool', poolname)
        result = self.run_and_check(cmd, expectation)
        if not result:
            return result
        if striped or self.striped:
            result = self.setpoolmode(poolname, "striped")
        return result

    def setpoolmode(self, pool, mode, expectation=True):
        """
        Sets pool mode. Returns a ReturnCode.
        """
        cmd = mkcmdstr('setpoolmode', mode, pool)
        result = self.run_and_check(cmd, expectation)
        return result

    def rmpool(self, poolname, expectation=True):
        """
        Removes the specified pool. Returns a ReturnCode.
        """
        cmd = mkcmdstr('rmpool', poolname)
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def pools(self):
        """
        Returns a dictionary of pools encoded as dictionaries.  e.g.::

            {'tidal': {'fextents': '19096',
                       'free': '80.094',
                       'lvs': ['one', 'two', 'three', 'four'],
                       'name': 'mypool',
                       'pvlist': ['8.0', '8.1', '8.2', '8.3', '8.4', '8.5'],
                       'pvs': '6',
                       'size': '480.139',
                       'textents': '114474',
                       'uextents': '95372'}}

        """
        columns1x = ['name', 'pvs', 'size', 'free', 'reserve']
        columns20 = ['name', 'pvs', 'size', 'free', 'used', 'mode']
        header = re.compile(r"POOL[ \t]*#PVs[ \t]*TOTAL\(GB\)[ \t]*FREE\(GB\)")
        pools = dict()

        cmd = 'pools'
        result = self.run_and_check(cmd)
        r = result.message
        if len(r) > 0:
            rs = r.split('\r\n')
            hfound = False
            for line in rs:
                if not hfound:
                    if header.search(line):
                        hfound = True
                        continue
                ls = line.split()
                lslen = len(ls)
                if lslen == len(columns20):
                    p = dict(zip(columns20, ls))
                elif lslen == len(columns1x):
                    p = dict(zip(columns1x, ls))
                else:
                    raise IndexError("pool entry header length is %s : %s" % (lslen, line))
                pools[p['name']] = p
        for poolname in pools:
            cmd = "pools -a " + poolname
            result = self.run_and_check(cmd)
            r = result.message

            rs = r.split('\r\n')
            hfound = False
            inlvs = False
            inpvs = False
            lvs = list()
            for line in rs:
                if not hfound and header.search(line):
                    #   POOL          #PVs  TOTAL(GB)   FREE(GB)
                    hfound = True
                    continue
                ls = line.split()
                if not inlvs:
                    if ls[0] == poolname:  # Alk3nTr4XHEV    16   1280.370   1227.140
                        continue
                    if ls[0] == 'Total':  # Total Exts : 305264 1280.370GB
                        pools[poolname]['textents'] = ls[3]
                    elif ls[0] == 'Free':  # Free Exts : 292573 1227.140GB
                        pools[poolname]['fextents'] = ls[3]
                    elif ls[0] == 'Unique':  # Unique Exts : 12675 53.163GB
                        pools[poolname]['uextents'] = ls[3]
                    elif ls[0] == 'LVs':
                        inpvs = False
                        lvs = ls[2:]
                        inlvs = True
                    elif ls[0] == 'PVs':  # PVs : 8.0 8.1 8.2 8.3 8.4 8.5 8.6 8.7 8.8 8.9 8.10 8.11 8.12 8.13
                        inpvs = True
                        pvl = ls[2:]
                        pools[poolname]['pvlist'] = pvl
                    elif inpvs:
                        pools[poolname]['pvlist'].extend(ls)
                else:
                    lvs.extend(ls)
            pools[poolname]['lvs'] = lvs

        return pools

    def mkpv(self, pool, target, expectation=True, srx=None):
        """
        Adds the specified target to a pool. Returns a Boolean.
        If srx is not None, verify that the VSX set the masks 
        for this PV on the SRX correctly.
        """
        target = aoetostr(target)
        cmd = mkcmdstr('mkpv', pool, target)
        result = self.run_and_check(cmd, expectation)
        if result and srx:
            result = self.check_sr_masks(srx, target)
            if not result and expectation:
                raise ApplianceError(result.message)
        return result

    def rmpv(self, pv, expectation=True, srx=None):
        """
        Remove the specified target from a pool. Returns a Boolean.
        If srx is not None, verify that the VSX removed the masks 
        for this PV on the SRX correctly.
        """
        pv = aoetostr(pv)
        if srx and self.pvs.get(pv):
            # it is a pv, so check that the masks are correct before removal
            r = self.check_sr_masks(srx, pv)
            if not r:
                if expectation:
                    raise ApplianceError(r.message)
                return r
        cmd = mkcmdstr('rmpv -f', pv)
        r = self.run_and_check(cmd, expectation)
        if r and srx:
            # verify that we removed all our macs from the sr masks
            # note: there is a delay between rmpv & removing the masks
            # try for 10 seconds, if it's not clean by then, error
            for i in range(100):
                r = self.check_sr_masks(srx, pv)
                if not r and r.message.find("is empty") != -1:
                    # mask list failed with: mask list is empty, which is what 
                    # we expect to happen after rmpv ... this is correct
                    return ReturnCode(True, r.message)
                time.sleep(0.1)
            e = "SRX %s mask list should be empty for PV %s" % (srx.shelf, pv)
            logger.error(e)
            if expectation:
                raise ApplianceError(e)
            r.message = e
        return r

    @property
    def pvs(self):
        """
        If supplied, 'self.use_pvs' should be a list of strings of the form::

            [ '8.1', '8.2', '8.3' ]

        Returns a dictionary of pvs encoded as dictionaries where the key is the pv number::

            {'8.1': {'dexents': '2',
                     'fexents': '19052',
                     'free': '79.910',
                     'mextents': '1',
                     'mirror': None,
                     'pool': 'recover',
                     'pv': '8.1',
                     'size': '80.026',
                     'stat': 'single',
                     'texents': '19079'},
             '8.2': {'dexents': '1',
                     'fexents': '19078',
                     'free': '80.019',
                     'mextents': '0',
                     'mirror': None,
                     'pool': 'recover',
                     'pv': '8.2',
                     'size': '80.026',
                     'stat': 'single',
                     'texents': '19079'}}

        """

        columns = ['pv', 'size', 'free', 'mirror', 'stat', 'pool']
        header = re.compile(r"PV[ \t]*TOTAL\(GB\)[ \t]*FREE\(GB\)[ \t]*MIRROR[ \t]*STATE[ \t]*POOL")
        pdict = dict()

        cmd = 'pvs -a'
        if self.use_pvs:
            cmd += " " + ' '.join(self.use_pvs)
        result = self.run_and_check(cmd)

        r = result.message
        p = dict()
        if len(r) > 0:
            rs = r.split('\n')
            current = "header"
            for line in rs:
                if current == "header":
                    if header.search(line):
                        current = "column"
                        p = dict()
                        #                        pp("clear: %s" % line)
                        continue
                elif current == "column":
                    #                    pp("column: %s" % line)
                    ls = line.split()
                    if len(ls) == 5:
                        ls = [ls[0], ls[1], ls[2], None, ls[3], ls[4]]
                    p = dict(zip(columns, ls))
                    current = "total"
                    continue
                elif current == "total":
                    #                    pp("total: %s" % line)
                    ls = line.split(":")
                    p['texents'] = ls[1].split()[0]
                    current = "free"
                    continue
                elif current == "free":
                    #                    pp("free: %s" % line)
                    ls = line.split(":")
                    p['fexents'] = ls[1].split()[0]
                    current = 'used'
                    continue
                elif current == "used":
                    #                    pp("used: %s" % line)
                    ls = line.split(":")
                    p['uexents'] = ls[1].split()[0]
                    current = 'dirty'
                    continue
                elif current == "dirty":
                    #                    pp("dirty: %s" % line)
                    ls = line.split(":")
                    p['dexents'] = ls[1].split()[0]
                    current = 'meta'
                    continue
                elif current == 'meta':
                    #                    pp("meta: %s" % line)
                    ls = line.split(":")
                    p['mextents'] = ls[1].split()[0]
                    current = 'header'
                    pdict[p['pv']] = p
                    continue

        return pdict

    def mklv(self, pool, size, lvname, thin=False, expectation=True):
        """
        Returns a ReturnCode.
        """
        cmd = "mklv "
        if thin:
            cmd += "-t "
        cmd += "%s %s %s" % (pool, size, lvname)
        result = self.run_and_check(cmd, expectation)
        return result

    def rmlv(self, lv, expectation=True):
        """
        Returns a Boolean.
        """
        cmd = mkcmdstr('rmlv -f', lv)
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def lvs(self):
        """
        Returns a dictionary of lvs encoded as dictionaries.  e.g.::
 
            {'storage1':{'lun': {'shelf': '1504', 'slot': '1'},
              'lv': 'storage1',
              'masks': '0',
              'mode': 'r/w',
              'size': '159.000',
              'status': 'offline'}}
 
        If an lv (name) is specified only that lv, if found is returned. If
        a specified lv is returned and is not found an empty dict is returned.
 
        """
        columns1 = ['lv', 'size', 'mode', 'lun', 'shadow', 'pool']
        columns2 = ['lv', 'size', 'mode', 'lun', 'pool', 'shadow']
        columns = None

        header1 = re.compile(r"LV[ \t]*SIZE\(GB\)[ \t]*MODE[ \t]*LUN[ \t]*SHADOW[ \t]*POOL")
        header2 = re.compile(r"LV[ \t]*SIZE\(GB\)[ \t]*MODE[ \t]*LUN[ \t]*POOL[ \t]*SHADOW")
        lvdict = dict()

        cmd = 'lvs -a'
        result = self.run_and_check(cmd)
        r = result.message
        if len(r) > 0:
            rs = r.split('\r\n')

            # keep this function clean for graceful fallback when we run 
            # older versions of VSX code, use lvs2() for new versions
            if re.search("PROV[ \t]+SHADOW[ \t]+STATE", rs[0]):
                return self.lvs2(rs)

            for line in rs:
                # the header is repeated before each LV in lvs -a output
                if header1.search(line):
                    columns = columns1
                    continue
                elif header2.search(line):
                    columns = columns2
                    continue
                    # we do not handle the extended '-a' output
                if line.find(':') != -1:
                    continue
                ls = line.split()
                # the first three columns always exist, in the same order
                lvls = [ls[0], ls[1], ls[2]]
                lslen = len(ls)
                if lslen == 6:
                    lvls.extend([ls[3], ls[4], ls[5]])

                elif lslen == 5:
                    # we don't know which field is missing: LUN or SHADOW, so we 
                    # determine if the LV has a shadow by looking at lvs -a output
                    hasshadow = False
                    for l in rs:
                        # ignore non extended output
                        if l.find(':') == -1:
                            continue
                        flds = l.split(':')
                        if flds[0].strip() == "Shadow":
                            # if the Shadow key has a value:
                            if len(flds) > 1 and flds[1].strip():
                                hasshadow = True
                                break
                    if columns[-1] == 'pool':
                        if hasshadow:
                            lvls.extend([None, ls[3], ls[4]])
                        else:
                            lvls.extend([ls[3], None, ls[4]])
                    elif columns[-1] == 'shadow':
                        if hasshadow:
                            lvls.extend([None, ls[3], ls[4]])
                        else:
                            lvls.extend([ls[3], ls[4], None])
                    else:
                        logger.error("columns changed: %s" % ' '.join(columns))
                        return False  # what should we return when there is a failure like this?

                elif lslen == 4:  # LV has neither LUN nor SHADOW
                    if columns[-1] == 'pool':
                        lvls.extend([None, None, ls[3]])
                    elif columns[-1] == 'shadow':
                        lvls.extend([None, ls[3], None])
                    else:
                        logger.error("columns changed: %s" % ' '.join(columns))
                        return False  # what should we return when there is a failure like this?

                lv = dict(zip(columns, lvls))
                lvdict[lv['lv']] = lv

        return lvdict

    def lvs2(self, lines):
        """
        Put all 'lvs -a' output into a dictionary.
        The lvs() function will call this one if the two new fields, 
        STATE and PROV show up in the header.  Keeping the old intact 
        for graceful handling of old versions of code, otherwise the 
        code just gets too nasty.  Interesting point: the VSX prints 
        the LV header before each LV if run with -a.
        For example, this on the VSX::

            VSX shelf 15008> lvs -a
            LV    SIZE(GB) MODE       LUN  POOL   PROV SHADOW     STATE
            leg       6000.000  r/w          p1   thin            healthy
                 Total Exts : 1430515 6000.015GB
                 Dirty Exts : 365 1.531GB
                  Thin Exts : 1430150 5998.484GB
                Unique Exts : 127 0.533GB
                  84.4 Exts : 238327 999.616GB
                  84.6 Exts : 238463 1000.186GB
                  84.7 Exts : 238464 1000.191GB
                 84.12 Exts : 238466 1000.199GB
                 84.15 Exts : 3 0.013GB
                 84.19 Exts : 1195 5.012GB
                 84.22 Exts : 237133 994.608GB
                 84.23 Exts : 238464 1000.191GB
                    Created : Fri Jun  1 14:00:29 EDT 2012
              Serial Number : 73099f44632bb4c785a5
                      Masks : 
               Reservations : 
                     Shadow : 
            VSX shelf 15008>

        produces this dictionary::

            { 'leg' : { 'lv' : 'leg',
                    'size' : '6000.000',
                    'mode' : 'r/w',
                    'lun' : None,
                    'pool' : 'p1',
                    'shadow' : None,
                    'state' : 'healthy',
                    'prov' : 'thin',
                    'Total Exts' : { 'count' : '1430515', 'size' : '6000.015GB' },
                    'Dirty Exts' : { 'count' : '365', 'size' : '1.531GB' },
                    'Thin Exts' : { 'count' : '1430150', 'size' : '5998.484GB' },
                    'Unique Exts' : { 'count' : '127', 'size' : '0.533GB' },
                    'PV Exts' : {
                        '84.4' : { 'count' : '238327', 'size' : '999.616GB' },
                        '84.6' : { 'count' : '238463', 'size' : '1000.186GB' },
                        '84.7' : { 'count' : '238464', 'size' : '1000.191GB' },
                        '84.12' : { 'count' : '238466', 'size' : '1000.199GB' },
                        '84.15' : { 'count' : '3', 'size' : '0.013GB' },
                        '84.19' : { 'count' : '1195', 'size' : '5.012GB' },
                        '84.22' : { 'count' : '237133', 'size' : '994.608GB' },
                        '84.23' : { 'count' : '238464', 'size' : '1000.191GB' }, }
                    'Created' : 'Fri Jun  1 14:00:29 EDT 2012',
                    'Serial Number' : '73099f44632bb4c785a5',
                    'Masks' : '',
                    'Reservations' : '',
                    'Shadow' : '' }
            ... }


        """
        lvdict = dict()
        # cache this value so it's done once, not once per lv
        poollist = self.pools.keys()
        for line in lines:
            # ignore each header
            # LV    SIZE(GB) MODE       LUN  POOL   PROV SHADOW     STATE
            if re.match("LV[ \t]+SIZE\(GB\)[ \t]+MODE", line):
                continue

            # Account for all '-a' output.  Assumes that we 
            # already have the non '-a' portion for this LV.
            if line.find(':') != -1:
                fields = line.split(':', 1)
                key = fields[0].strip()
                val = fields[1].strip()
                m = re.match("([0-9]+\.[0-9]+) Exts", key)
                if m:
                    pve = 'PV Exts'
                    pv = m.group(1)
                    if not lvdict[lv].get(pve):
                        lvdict[lv][pve] = dict()
                    lvdict[lv][pve][pv] = dict()
                    count, size = val.split()
                    lvdict[lv][pve][pv]['count'] = count
                    lvdict[lv][pve][pv]['size'] = size
                elif re.match("(Total|Dirty|Thin|Unique) Exts", key):
                    lvdict[lv][key] = dict()
                    count, size = val.split()
                    lvdict[lv][key]['count'] = count
                    lvdict[lv][key]['size'] = size
                else:
                    lvdict[lv][key] = val
                continue

            flds = line.split()
            lv = flds[0]
            lvdict[lv] = dict()
            # 1st 3 fields always exist, always in the same order
            lvdict[lv]['lv'] = lv
            lvdict[lv]['size'] = flds[1]
            lvdict[lv]['mode'] = flds[2]

            # LUN and SHADOW are optionally absent, so if we have 
            # all fields or both missing, it's easy.  If only one 
            # field is absent, which is it, LUN or SHADOW?
            nflds = len(flds)
            if nflds == 8:
                lvdict[lv]['lun'] = flds[3]
                lvdict[lv]['pool'] = flds[4]
                lvdict[lv]['prov'] = flds[5]
                lvdict[lv]['shadow'] = flds[6]
                lvdict[lv]['state'] = flds[7]
            elif nflds == 6:
                lvdict[lv]['lun'] = None
                lvdict[lv]['pool'] = flds[3]
                lvdict[lv]['prov'] = flds[4]
                lvdict[lv]['shadow'] = None
                lvdict[lv]['state'] = flds[5]
            elif nflds == 7:
                # If the 4th field is a pool name, LUN is 
                # missing, otherwise, SHADOW is missing.
                ispool = False
                for pool in poollist:
                    if pool == flds[3]:
                        ispool = True
                        break
                if ispool:
                    lvdict[lv]['lun'] = None
                    lvdict[lv]['pool'] = flds[3]
                    lvdict[lv]['prov'] = flds[4]
                    lvdict[lv]['shadow'] = flds[5]
                else:
                    lvdict[lv]['lun'] = flds[3]
                    lvdict[lv]['pool'] = flds[4]
                    lvdict[lv]['prov'] = flds[5]
                    lvdict[lv]['shadow'] = None
                lvdict[lv]['state'] = flds[6]
            else:
                raise ApplianceError("unrecognized format in Vsx.lvs -a: %s" % line)
        return lvdict

    def mklun(self, lv, lun, expectation=True):
        """
        assign a VSX LUN (shelf.lun) to an LV.
        Only one VSX LUN can be assigned to an LV. When using the mklun command,
        the LUN is entered in a shelf.lun format
        returns ReturnCode object
        """
        lun = aoetostr(lun)
        cmd = mkcmdstr('mklun', lv, lun)
        result = self.run_and_check(cmd, expectation)
        return result

    def rmlun(self, lun, expectation=True):
        """
        disassociates one VSX LUN from the associated LV.
        The VSX LUN must first be placed offline before it can be removed.
        returns ReturnCode object
        """
        lun = aoetostr(lun)
        cmd = mkcmdstr('rmlun', lun)
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def luns(self):
        columns = ['lun', 'status', 'lv', 'size', 'mode', 'masks']
        header = re.compile(r"LUN[ \t]*STATUS[ \t]*LV[ \t]*SIZE\(GB\)[ \t]*MODE[ \t]*MASKS")
        ldict = dict()

        cmd = 'luns'
        result = self.run_and_check(cmd)
        r = result.message
        if len(r) > 0:
            rs = r.split('\r\n')

            hfound = False
            for line in rs:
                addr = dict()

                if not hfound:
                    if header.search(line):
                        hfound = True
                        continue
                ls = line.split()
                if ls[4] > 0:
                    pass  # TODO: go get the masks for this?
                t = ls[0].split('.')
                addr['shelf'] = t[0]
                addr['slot'] = t[1]
                e = [addr, ls[1], ls[2], ls[3], ls[4], ls[5]]
                lun = dict(zip(columns, e))
                lunstr = aoetostr(lun['lun'])
                ldict[lunstr] = lun

        return ldict

    @property
    def sos(self):
        # TODO: Check for err (scpwipe)
        expectation = True
        t = self.timeout
        self.timeout = 600
        cmd = 'sos -t'
        result = self.run_and_check(cmd, expectation)
        r = result.message
        self.timeout = t

        return r

    @property
    def shelf(self):
        expectation = True
        cmd = 'shelf'
        result = self.run_and_check(cmd, expectation)
        r = result.message
        rs = r.split('\r\n')
        return rs[1]

    @shelf.setter
    def shelf(self, shelfnumber):
        """
        shelf (setter) attempts to change the VSX's shelf address, 
        and answers the CLI's (possible) prompt with 'ans'.
        """
        ans = 'y'
        expectation = True
        cmd = "shelf %s" % shelfnumber
        logger.debug(cmd)
        r = self.sendline(cmd)
        logger.debug(r)
        cpl = self.compile_pattern_list(
            [
                r"'n' to cancel, or 'y' to change all \[n\]: ",
                self.prompt,
            ])
        while 1:
            i = self.expect_list(cpl)
            if i == 0:
                r = self.run_and_check(ans, expectation=expectation)
                if not r and expectation:
                    raise ApplianceError(r.message)
            elif i == 1:
                break
            else:
                ctx = self.before + self.after
                msg = "%s: unexpected response: %s" % (cmd, ctx)
                logger.error(msg)
                raise ApplianceError(msg)

    def offline(self, lun, expectation=True):
        """
        Disables SAN access for one or more specified VSX LUN(s).
        """
        lun = aoetostr(lun)
        cmd = mkcmdstr('offline ', lun)
        result = self.run_and_check(cmd, expectation)
        return result

    def online(self, lun, expectation=True):
        """
        Enables SAN access for one or more VSX LUNs.
        """
        lun = aoetostr(lun)
        cmd = mkcmdstr('online', lun)
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def lvsnaps(self):
        columns1 = ['lv', 'date', 'size', 'lun', 'pool']
        columns2 = ['snapshot', 'date', 'size', 'class', 'schedule', 'hold']
        header1 = re.compile(r"LV[ \t]*DATE[ \t]*SIZE\(GB\)[ \t]*POOL")
        header2 = re.compile(r"SNAPSHOT[ \t]*DATE[ \t]*SIZE\(GB\)[ \t]*CLASS[ \t]*SCHEDULE[ \t]*HOLD")
        snaplist = list()

        cmd = 'lvsnaps'
        result = self.run_and_check(cmd)
        r = result.message

        key = None
        columns = None
        if len(r) > 0:
            rs = r.split('\r\n')

            for line in rs:
                if header1.search(line):
                    key = 'lv'
                    columns = columns1
                    continue
                if header2.search(line):
                    key = 'snapshot'
                    columns = columns2
                    continue
                ls = line.split()
                lslen = len(ls)
                collen = len(columns)
                if collen == 5:
                    if lslen == 5:
                        ls = [ls[0], ls[1], ls[2], ls[3], ls[4]]
                    if lslen == 4:
                        ls = [ls[0], ls[1], ls[2], None, ls[3]]
                elif collen == 6:
                    if lslen == 5:
                        ls = [ls[0], ls[1], ls[2], ls[3], None, ls[4]]
                    if lslen == 6:
                        ls = [ls[0], ls[1], ls[2], ls[3], ls[4], ls[5]]
                snap = dict(zip(columns, ls))
                snaplist.append(snap)

        snapdict = dict()
        for snap in snaplist:
            snapid = snap[key]
            snapdict[snapid] = snap
        return snapdict

    def snap(self, lv, expectation=True):
        """
        Creates manual snapshots for one or more LVs.
            returns ReturnCode object
        """
        cmd = mkcmdstr('snap', lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def reboot(self):
        """
        Shuts down the VSX core service then reboots the VSX appliance.
        """
        logger.info("rebooting %s" % self.host)
        self.sendline("reboot")
        # make sure a call to self.close does not kill 
        # the connection before the reboot cmd is sent
        time.sleep(3)

    def clone(self, original, new, expectation=True):
        """
        Makes a read/writable copy of the LV at a precise time, returns ReturnCode object
        """

        cmd = mkcmdstr('clone', original, new)
        result = self.run_and_check(cmd, expectation)
        return result

    def lvresize(self, size, lv, expectation=True):
        """
        Increases the size of the specified LV. returns ReturnCode object
        """
        ret = self.run_and_check("lvresize -f %s %s" % (str(size), lv), expectation)
        if ret.message.find("error: ") != -1:  # TODO: FILE bug for error not first, and -f not quiet
            ret.status = False
        return ret

    @property
    def certhash(self):
        cmd = 'certhash '
        result = self.run_and_check(cmd)
        r = result.message.strip()
        return r

    def setsecurity(self, address, encrypt=None, certhash=None, expectation=True):
        """
        Sets security information for a remote VSX at IP address.
        """
        cmd = mkcmdstr('setsecurity', address)
        if encrypt:
            cmd = cmd + ' ' + encrypt
            if certhash:
                cmd = cmd + ' ' + certhash

        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def security(self):
        """
        Returns a dictionary of the security parameters for all remote VSXen.
        """
        expectation = True
        columns = ['address', 'encrypt', 'hash']
        header = re.compile(r"IP ADDRESS[ \t]*ENCRYPT[ \t]*HASH")
        secdict = dict()

        r = self.run_and_check('security', expectation)
        rs = r.message.split('\r\n')
        for line in rs:
            if header.search(line):  # TODO: is this match too much overhead? (see remote)
                continue
            ls = line.split()
            secentry = dict(zip(columns, ls))
            secdict[secentry['address']] = secentry

        return secdict

    def setremote(self, remote, primary=None, secondary=None, expectation=True):
        """
        Links a single VSX or a VSX HA pair by providing primary and secondary IP address
        to one remote name (RNAME).
        RNAME is a local abstract name used to identify the remote VSX/VSX HA pair.
        The RNAME is then used in the shadowrecv and shadowsend commands to configure LV shadow replication.
        returns ReturnCode object
        """
        cmd = mkcmdstr('setremote', remote)
        if primary:
            cmd = cmd + ' ' + primary
            if secondary:
                cmd = cmd + ' ' + secondary
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def remote(self):
        columns = ['name', 'address1', 'address2']
        header = re.compile(r"NAME[ \t]*IP ADDRESS[ \t]*IP ADDRESS")
        rdict = dict()

        r = self.run_and_check('remote')
        rs = r.message.split('\r\n')
        hf = False
        for line in rs:
            if not hf:
                if header.search(line):
                    hf = True
                    continue
            ls = line.split()
            rentry = dict(zip(columns, ls))
            rdict[rentry['name']] = rentry
        return rdict

    def shadowrecv(self, remote, src, dest, expectation=True):
        """
        Make LV a shadow target for receiving snapshots from the src at the remote VSX-pair RNAME and dest lv.
        returns ReturnCode object
        """
        cmd = mkcmdstr('shadowrecv', remote, src, 'to', dest)
        result = self.run_and_check(cmd, expectation)
        return result

    def shadowsend(self, remote, src, dest, expectation=True):
        """
        estblishes a shadow connection between the source LV and the target LV.
        The source LV sends snapshots to a designated LV on the target VSX.
        returns ReturnCode object
        """
        cmd = mkcmdstr('shadowsend', remote, src, 'to', dest)
        result = self.run_and_check(cmd, expectation)
        return result

    def unshadow(self, lv, expectation=True):
        """
        removes the shadowrecv or shadowsend connection configured between a source LV and a target LV.
        It removes one side of the connection depending on where the command is issued (VSX source or VSX target).
        returns ReturnCode object
        """
        cmd = mkcmdstr('unshadow -f', lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def setsnaplimit(self, size, lv, expectation=True):
        """
        sets the potential snapshot storage limit for an LV.
        returns ReturnCode object
        """
        # setsnaplimit size[T,G,M,K] { Auto | Stop } LV [ ... ]
        cmd = mkcmdstr('setsnaplimit -f', size, lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def setsnapsched(self, sclass, when, retain, lv, expectation=True):
        """
        sets the schedule for automated snapshots of one or more LVs.
        returns ReturnCode object
        """
        # Class Time Retain LV [ ... ]
        cmd = mkcmdstr('setsnapsched', sclass, when, retain, lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def setshadowretain(self, cl, retain, lv, expectation=True):
        # setshadowretain Class Retain LV
        cmd = mkcmdstr('setshadowretain', cl, retain, lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def shadowretain(self, lv=None, expectation=True):
        cmd = 'shadowretain'
        if lv:
            cmd = mkcmdstr(cmd, lv)
        result = self.run_and_check(cmd, expectation)
        return result

    def wipe(self, srx=None):  # I'm not sure this belongs in the class.
        """
        Removes everything xlate: shadows, luns, lvs, snaps, pools, etc.
        """
        if self.hastate == "active":
            # all actions that require xlate
            luns = self.luns
            for i in luns.keys():
                if luns[i]['status'] == "online":
                    self.offline(i)
                self.rmlun(i)

            lvs = self.lvs
            for i in lvs.keys():
                if lvs[i]['shadow']:
                    self.unshadow(lvs[i]['lv'])

            for r in self.remote:
                self.setremote(r)
            for s in self.security:
                self.setsecurity(s)

            snaps = self.lvsnaps
            snaplist = snaps.keys()
            snaplist.reverse()

            for i in snaplist:
                self.rmlv(i)

            lvs = self.lvs
            lvlist = lvs.keys()

            for i in lvlist:
                self.rmlv(i)

            pvs = self.pvs
            pvlist = pvs.keys()

            for i in pvlist:
                self.rmpv(i, srx=srx)

            pools = self.pools
            poollist = pools.keys()

            for i in poollist:
                self.rmpool(i)

            self.aoeflush()  # hmm?

            # all actions that do not require xlate (currently nothing)

    @property
    def ipaddress(self):
        """
        Returns a list of ip capable interfaces encoded as dictionaries. e.g.::
        
            {'ether0':{'link': {'current': '1000', 'max': '1000'},
                        'mac': '0025900a856c',
                        'name': 'ether0',
                        'ip':'10.1.1.1'},
              'ether1':{'link': {'current': '0', 'max': '1000'},
                        'mac': '0025900a856d',
                        'name': 'ether1',
                        'ip' : None}}

        """

        cmd = 'ipaddress'
        columns = ['port', 'address', 'mask']
        header = re.compile(r"PORT[ \t]*IP ADDRESS[ \t]*MASK")

        r = self.run_and_check(cmd)
        ifdict = dict()
        rs = r.message.split('\r\n')

        for line in rs:
            if header.search(line):
                continue
            ls = line.split()
            ifc = dict(zip(columns, ls))
            ifdict[ifc['port']] = ifc

        return ifdict

    @property
    def ipgateway(self):
        """
        Returns a string if set and None if unset
        """
        cmd = 'ipgateway'
        header = re.compile(r"IP[ \t]*GATEWAY")
        result = self.run_and_check(cmd)
        r = result.message.split('\r\n')
        if header.match(r[0]):
            gw = r[1]
            return gw
        elif r[1].startswith("unset"):
            return None
        else:
            raise ApplianceError(result.message)

    @ipgateway.setter
    def ipgateway(self, ip):
        cmd = 'ipgateway %s' % ip
        err = re.compile(r"ipgateway:")
        r = self.run_and_check(cmd)
        if err.match(r.message):
            raise ApplianceError(r.message)

    @property
    def timesource(self):
        cmd = 'timesource'
        result = self.run_and_check(cmd)
        return result

    @timesource.setter
    def timesource(self, set_l):
        """
        vsx.timesource = aList
        where aList is a list of the args
        [ 'ntp', IPaddress] | ['local', yyyymmdd.hhmmss ]
        
        """
        src, arg = set_l.split()
        cmd = mkcmdstr('timesource', src, arg)
        self.run_and_check(cmd)  # TODO: do we need to check the return?

    @property
    def syslog(self):
        """
        Returns a dictionary::

            {'source': None, 'server': None}

        """
        cmd = 'syslog'
        header = re.compile(r"SOURCE[ \t]*SERVER")
        result = self.run_and_check(cmd)
        r = result.message.split('\r\n')
        if header.match(r[0]):
            source, server = r[1].split()
            return {'source': source, 'server': server}
        elif r[0].startswith("syslog: syslog not set"):
            return {'source': None, 'server': None}
        else:
            raise ApplianceError(result.message)

    @syslog.setter
    def syslog(self, ip):
        cmd = 'syslog %s' % ip
        err = re.compile(r"syslog:")
        r = self.run_and_check(cmd)
        if err.match(r.message):
            raise ApplianceError(r.message)

    @property
    def harole(self):
        cmd = 'harole'
        result = self.run_and_check(cmd)
        r = result.message
        rs = r.split('\r\n')
        if len(rs) > 1 and rs[0].strip() == "HAROLE":
            logger.info("%s harole is %s" % (self.host, rs[1]))
            return rs[1]
        else:
            logger.error(r)
            raise ApplianceError("harole unknown: %s" % r)

    @harole.setter
    def harole(self, r):
        """
        Argument r is a dictionary::
        
        {
                'role': "primary" | "secondary",
                [ 'address': "ipaddress" ],
                [ 'retain_config': "new" | "retain" ]
        }
        
        The 'address' key is mandatory if 'role' is "secondary".
        The 'retain_config' is optional and defaults to "new", 
        and is only used when moving to primary.
        """
        new_role = r['role']
        if new_role == "secondary":
            new_role += " %s" % r['address']
        current_role = self.harole
        will_reboot = False
        if new_role != current_role:
            will_reboot = True
        if r.get('address'):
            cmd = "harole %s %s" % (r['role'], r['address'])
            logger.info("%s: %s" % (self.host, cmd))
            tprompt = self.prompt
            self.prompt = "Continue\?"
            self.run(cmd)
            self.prompt = tprompt
            self.run("y", wait=not will_reboot)
        elif r.get('role'):
            cmd = "harole %s" % r['role']
            logger.info(self.host + ':' + cmd)
            tprompt = self.prompt
            self.prompt = "Continue\?"
            self.run(cmd)
            if new_role == "primary":
                self.prompt = "Enter 'retain' to retain config, or 'new' to remove config"
                self.run("y")
                cmd = "new"
                rc = r.get('retain_config')
                if rc:
                    cmd = rc
                self.run(cmd, wait=not will_reboot)
                self.prompt = tprompt
            else:
                self.prompt = tprompt
                self.run("y", wait=not will_reboot)
        if will_reboot:
            time.sleep(3)  # prevent race
            self.reconnect()

    @property
    def hastate(self):
        cmd = 'hastate'
        result = self.run_and_check(cmd)
        r = result.message
        rs = r.split('\r\n')
        logger.info(self.host + " hastate is " + rs[1])
        return rs[1]

    @hastate.setter
    def hastate(self, state):
        cmd = mkcmdstr('hastate', state)
        logger.info(self.host + ':' + cmd)
        self.run_and_check(cmd, expectation=False, force=True)
        if state == "active":
            while 1:
                try:
                    # we do not care about the value, we just need to 
                    # know if xlate is ready to receive commands or not
                    _ = self.shelf
                    break
                except Exception as e:
                    logger.debug(str(e))
                    time.sleep(0.5)

    def hastatus(self):
        """
        Returns a dictionary::

            {'peer': None,
            'remotestate': None,
            'role': None,
            'state': None,
            'status': None}

        containing the high availability status
        """
        hastat = dict()
        ret = self.run_and_check("hastatus")
        lines = ret.message.split('\n')
        if len(lines) < 2:
            return hastat
        flds = lines[1].split()
        if len(flds) < 5:
            return hastat
        hastat['role'] = flds[0]
        hastat['state'] = flds[1]
        hastat['peer'] = flds[2]
        hastat['status'] = flds[3]
        hastat['remotestate'] = flds[4]
        return hastat

    def update(self, pkg):
        """
        update the CorOS on the VSX (CorOS + VSX appliance specific
        functionality).
        """
        self.sendline('update %s' % pkg)
        i = self.expect(["Update will reboot.  Enter yes to continue:",
                         "Enter yes to confirm and reboot:"], timeout=60)
        if i == 0 or i == 1:
            self.sendline('yes')
        return True

    def shadow(self, src_lv, trg_lun, expectation=True):
        """
        Asynchronous read-only copy of a snapshot to a second VSX LV.
            returns ReturnCode object
        """
        trg_lun = aoetostr(trg_lun)
        cmd = mkcmdstr('shadow', src_lv, trg_lun)
        result = self.run_and_check(cmd, expectation)
        return result

    @property
    def build(self):
        """
        get build information
        """
        tprompt = self.prompt
        self.prompt = 'VSX EXPERTMODE# '
        self.run('/expertmode')
        cbuild = self.run('build')
        self.prompt = tprompt
        self.run('exit')
        return cbuild

    def clrpvmeta(self, pv, expectation=True):
        """
        clears the first 8k of an AoE target. If a user sets up a VSX, adds PVs, and then issues
        factoryreset, old metadata will be left on the PVs.
        To reuse the PVs the user must issue clrpvmeta.

        * as of release 1.5.0 the clrpvmeta cmd changed to a hidden cmd if running an older release
          we fall back gracefully.
        """
        cmd = mkcmdstr('/clrpvmeta -f', aoetostr(pv))
        result = self.run_and_check(cmd, expectation=False)
        if not result and result.message.startswith("unknown command: "):
            cmd = mkcmdstr('clrpvmeta -f', aoetostr(pv))
            result = self.run_and_check(cmd, expectation=False)
            if not result and expectation:
                raise ApplianceError(result.message)
        return result

    @property
    def snaplimit(self):
        """
        Returns a dictionary of snaplimits::

            {'temp': { 'limit': 'unset',
                       'lv': 'temp',
                       'used': '0.000'},
            'xfer': {'limit': 'ignore',
                      'lv': 'xfer',
                      'used': '0.000'}}

        """
        ret = self.run_and_check("snaplimit")
        sl = dict()

        if not ret:
            logger.error(ret.message)
            return sl
        hfound = False
        lines = ret.message.split('\n')
        for line in lines:
            if not hfound:
                hfound = True
                continue
            ls = line.split()
            if len(ls) == 2:
                lv = ls[0]
                sl[lv] = dict()
                sl[lv]['lv'] = lv
                sl[lv]['limit'] = None  # N/A in this VSX release
                sl[lv]['used'] = ls[1]
            elif len(ls) == 3:
                lv = ls[0]
                sl[lv] = dict()
                sl[lv]['lv'] = lv
                sl[lv]['limit'] = ls[1]
                sl[lv]['used'] = ls[2]
            else:
                print("snaplimit parsing error: '%s'" % line)
        return sl

    def rollback(self, lv, snap=None):
        """
        The rollback command is used to set an LV back to a known good state using a specified snapshot.
        Specifically, the rollback command will first sets the LV to match a specified snapshot;
        then removes any snapshots created after the specified snapshot
        returns ReturnCode object
        """
        cmd = "rollback -f %s" % lv
        if snap:
            cmd += " %s" % snap
        return self.run_and_check(cmd)

    @property
    def model(self):
        """
        Returns the VSX model as a string.
        """
        s = self.run("model")
        s = s.split('\n')
        return s[1]

    def mirror(self, pv, target, wait=False, expectation=True, srx=None):
        """
        Mirror a PV to a target LUN. If srx is not None, verify that the VSX 
        set the masks for this PV on the SRX correctly.
        """
        cmd = "mirror %s %s" % (pv, target)
        logger.debug(cmd)
        ret = self.run_and_check(cmd, expectation)
        # upon success, check both the pv and the target lun for vsx masks
        if ret and srx:
            ret = self.check_sr_masks(srx, pv)
        if not ret:
            if expectation:
                raise ApplianceError(ret.message)
            return ret
        if srx:
            ret = self.check_sr_masks(srx, target)
            if not ret:
                if expectation:
                    raise ApplianceError(ret.message)
                return ret
        if not wait:
            return ret
        while 1:
            state = self.pvs[pv]['stat']
            if state == "mirrored":
                ret.message = state
                break
            elif state != "silvering":
                # it's not still silvering, and it's not mirrored: busted
                e = "mirror %s->%s is %s" % (pv, target, state)
                logger.error(e)
                ret = ReturnCode(False, e)
                break
            time.sleep(1)
        if not ret and expectation:
            raise ApplianceError(ret.message)
        return ret

    def unmirror(self, pv, expectation=True, srx=None):
        """
        Unmirrors the target from the PV. If srx is not None, verify that the VSX 
        removed the masks for the target LUN, but left those for this PV correctly.
        """
        cmd = "unmirror -f %s" % pv
        target = None
        if srx:
            _pvs = self.pvs
            if _pvs.get(pv) and _pvs[pv]['stat'] != "single":
                target = _pvs[pv]['mirror']
                # it exists and is mirrored, so check the masks before unmirror
                r = self.check_sr_masks(srx, pv)
                if not r:
                    if expectation:
                        raise ApplianceError(r.message)
                    return r
                r = self.check_sr_masks(srx, target)
                if not r:
                    if expectation:
                        raise ApplianceError(r.message)
                    return r
        r = self.run_and_check(cmd, expectation)
        if r and srx:
            # verify that we retained all our macs in the sr mask list for pv
            r = self.check_sr_masks(srx, pv)
            if not r:
                if expectation:
                    raise ApplianceError(r.message)
                return r
                # and that we removed all our macs in the target's mask list
            r = self.check_sr_masks(srx, target)
            if r and r.message.find("is empty") == -1:
                if expectation:
                    e = "%s mask list should be empty upon unmirror: %s\n" % (target, r.message)
                    raise ApplianceError(e)
                return ReturnCode(False, r.message)
            else:
                # mask list failed with: target mask list is empty, which is what 
                # we expect to happen after unmirror ... this is correct
                r = ReturnCode(True, r.message)
        return r

    def brkmirror(self, pv, expectation=True, srx=None):
        """
        similar to unmirror, but it will set the primary half of the mirror to the broken state.
        The xlate config file will also be updated.
        """
        cmd = "brkmirror -f %s" % pv
        r = self.run_and_check(cmd, expectation)
        if r and srx:
            r = self.check_sr_masks(srx, pv)
            if not r and expectation:
                raise ApplianceError(r.message)
        return r

    def promote(self, pv, expectation=True):
        """
        promotes the SR/SRX LUN (mirrored target) to the primary PV,
        essentially switching the order of the mirror connection.
        This is useful for taking an SR/SRX LUN out of service.
        returns ReturnCode object
        """
        cmd = mkcmdstr('promote', aoetostr(pv))
        result = self.run_and_check(cmd, expectation)
        return result

    def mklegacy(self, lv, pool, target, expectation=True):
        """
        hidden command,  Legacy luns are needed when a user has a physical volume they must import directly into a VSX.
        The PV is added and an LV is created in one shot.
        The entire volume holds user data. There is no room for PV metadata, which is stored on another PV in the pool.
        """
        cmd = "/mklegacy %s %s %s" % (lv, pool, target)
        return self.run_and_check(cmd, expectation)

    @property
    def build(self):
        """
        Return urrent running build string
        """
        tprompt = self.prompt
        self.prompt = 'VSX EXPERTMODE# '
        self.run('/expertmode')
        cbuild = self.run('build')
        self.prompt = tprompt
        self.run('exit')
        return cbuild

    @property
    def mask(self):
        maskd = dict()
        for lv in self.lvs.keys():
            cmd = "mask %s" % lv
            # LV    LUN MASK(S)
            # four   000000000041 000000000042 000000000043 000000000044
            r = self.run_and_check(cmd)
            rs = r.message.split()
            maskd[rs[3]] = rs[4:]
        return maskd

    @mask.setter
    def mask(self, maskstring):
        """
        Set a mask with a string:
        mysx.mask = "+001004010203 -001004040506 mylv"
        """
        # wonder if we can use __iadd__ somehow with a func
        cmd = "mask %s " % maskstring
        self.run_and_check(cmd)

    @property
    def date(self):
        cmd = "date"
        r = self.run_and_check(cmd)
        return r.message

    @property
    def timezone(self):
        cmd = "timezone"
        r = self.run_and_check(cmd)
        ret = r.message.split('\n')[1]
        return ret

    @timezone.setter
    def timezone(self, zone):
        """
        Set the timezone with a string:
        mysx.timezone = "Navajo"
        """
        # wonder if we can use __iadd__ somehow with a func
        cmd = "timezone %s " % zone
        self.run_and_check(cmd)

    @property
    def timezones(self):
        cmd = "timezone -l"
        ret = self.run_and_check(cmd)
        header = re.compile(r"Available[ \t]*timezones:")
        hfound = False
        tzl = list()
        lines = ret.message.split('\n')
        for line in lines:
            if not hfound and header.match(line):
                hfound = True
                continue
            tzl.extend(line.split())
        tzl.sort()
        return tzl

    def set_memflags(self, flags):
        """
        Write 'memflag $flags' into the xlate/ctl file:

        """
        self.run_and_check("/expertmode")
        r = self.run_and_check("echo memflag %s > /n/xlate/ctl" % str(flags))
        logger.info(r.message)
        self.run_and_check("exit")
        return r

    def memchk(self):
        """
        Write 'memchk' into the xlate/ctl file:

        """
        self.run_and_check("/expertmode")
        r = self.run_and_check("echo memchk > /n/xlate/ctl")
        logger.info("memchk: '%s'" % r.message)
        self.run_and_check("exit")
        return r

    @property
    def sanaddr(self):
        """
        Sanaddr is the new address used for HA configurations, 
        instead of the IP address.  It is actually the EL address.
        """
        r = self.run_and_check("sanaddr")
        ret = r.message.split('\n')[1]
        return ret

    @property
    def hapeers(self):
        """
        Returns a dictionary of all accessible peers in the SAN.
        format::


            {'15008' : {
                    'shelf': "15008",
                    'addr': "5100002590602bea",
                    'model': "VSX3500-G6"
                   },
            '15024' : {
                    'shelf': "15024",
                    'addr': "51000025903b3ee6",
                    'model': "VSX3500-G6"
                   }
            }

        """
        hdr = False
        p = dict()
        r = self.run_and_check("hapeers")
        lines = r.message.split('\r\n')
        for l in lines:
            if re.match("SHELF[ 	]+ADDRESS[ 	]+MODEL", l):
                hdr = True
                continue
            if not hdr:
                logger.error("Vsx.hapeers(): did not find the expected header!")
                break
            ls = l.split()
            if len(ls) != 3:
                logger.error("malformed 'hapeers' output: %s" % r.message)
                return p
            sh = ls[0]
            p[sh] = dict()
            p[sh]['shelf'] = sh
            p[sh]['addr'] = ls[1]
            p[sh]['model'] = ls[2]
        return p

    def check_sr_masks(self, srx, pv):
        """
        VSX ether0 & ether1 are IP interfaces, and should not exist in 
        the SAN mac list.  All other VSX ports should exist in the list.
        Other macs in the list must be ignored here, as they may be from 
        a VSX in an HA relationship with this one (self).
        """
        pv = str(pv)
        logger.debug("checking sr masks for pv %s, shelf %s" % (pv, srx.shelf))
        sh = str(AoEAddress(pv).shelf)
        if sh != srx.shelf:
            e = "check_sr_masks(sr %s, pv %s): wrong shelf or not a PV" % (srx.shelf, pv)
            logger.error(e)
            return ReturnCode(False, e)
        slot = str(AoEAddress(pv).slot)
        nmacs = 0
        ifs = self.ifstat
        masks = srx.mask
        if not masks.get(slot):
            e = "SRX mask list for %s is empty" % pv
            logger.debug(e)
            return ReturnCode(False, e)
        for m in masks:
            if m == slot:
                for mask in masks[m]:
                    for i in ifs:
                        if ifs[i]['mac'] == mask:
                            if i == 'ether0' or i == 'ether1':
                                e = "VSX IP port %s disallowed" % str(ifs[i])
                                logger.error(e)
                                return ReturnCode(False, e)
                            nmacs += 1
                            # we only care about this VSX's (self's) SAN (non-IP) mac addresses
        if nmacs == (len(ifs) - 2):
            return ReturnCode(True)
        e = "SRX LUN %s masks != VSX SAN mac(s):\nsrx masks: %s\nvsx ifs: %s\n" % \
            (pv, str(masks[slot]), str(ifs))
        logger.error(e)
        return ReturnCode(False, e)

    @property
    def service(self):
        cmd = "service"
        ret = self.run_and_check(cmd)
        header = re.compile(r"SERVICE[ \t]*STATUS")
        hfound = False
        svcd = dict()
        lines = ret.message.split('\n')
        for line in lines:
            if not hfound and header.match(line):
                hfound = True
                continue
            svc, status = line.split()
            svcd[svc] = status
        return svcd

    @service.setter
    def service(self, setting):
        if type(setting) == str:
            svc, status = setting.split()
        elif type(setting) == list:
            svc, status = setting
        else:
            raise TypeError("Expected a string or list got %s" % str(type(setting)))
        cmd = "service %s %s" % (svc, status)
        self.run_and_check(cmd)

    @property
    def strict(self):
        tprompt = self.prompt
        self.prompt = 'VSX EXPERTMODE# '
        self.run('/expertmode')
        r = self.run_and_check('if (test -r /n/kfs/conf/strict) echo True; if not echo False')
        if r.message == 'False':
            r.status = False
        if r.message == 'True':
            r.status = True
        self.prompt = tprompt
        self.run('exit')
        return r

    @strict.setter
    def strict(self, setting):
        tprompt = self.prompt
        self.prompt = 'VSX EXPERTMODE# '
        self.run('/expertmode')
        if setting:
            self.run('touch /n/kfs/conf/strict')
        else:
            self.run('rm /n/kfs/conf/strict')
        self.prompt = tprompt
        self.run('exit')

    def memstir(self, msec=0):
        """
        If msec == 0, then kills the memstir process, otherwise 
        set the max range for the memstir process' random sleep.
        """
        self.run("/expertmode")
        self.run("echo memstir %d > /n/xlate/ctl" % msec)
        self.run("exit")

    def syslogtest(self, msg):
        """
        The syslogtest command generates a syslog message to the configured syslog
        server (see 'help syslog').  The message is comprised of all arguments
        concatenated into a single string.

        usage: syslogtest msg
        """
        logger.debug("syslogtest called with message: %s" % msg)
        r = self.run_and_check("syslogtest %s" % msg)
        return r

    def revalidate(self):
        """
        Mostly used to clear insurgent detection cache
        """
        self.expert_run('echo revalidate > /n/xlate/targ/ctl')
