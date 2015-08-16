#!/usr/bin/env python

import logging
import os
from pprint import pformat

from otto.lib.otypes import Namespace

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.intitiators')
logger.addHandler(logging.NullHandler())


class Ethdrv(object):
    """
    A class for interacting with initiator's debug files.
    Requires get_ethdrv call back function.  This callback function
    must return the contents of the specified entity (filename) under the
    ethdrv parent (directory).

    Basic Usage::

            from otto.initiators.solaris import Solaris

            i = solaris.Solaris(uname, host, passwd, prompt=None)
            i.connect()
            print i.ethdrv.release
            i.disconnect()

    """

    def __init__(self, get_ethdrv):
        self.get_ethdrv = get_ethdrv

    @property
    def acbs(self):
        """
        Returns a dictionary of acbs in the following format::

                {'141.2': {'arcnt': 0,
                           'index': 186,
                           'out': 0,
                           'qcnt': 0,
                           'resent': 0,
                           'sent': 5403,
                           'state': 4,
                           'target': '141.2',
                           'unex': 0,
                           'wnd': 16}
                           }

        """
        dev = dict()
        head = ['index', 'state', 'target', 'out', 'wnd', 'qcnt', 'arcnt', 'sent', 'resent', 'unex']
        out = self.get_ethdrv('acbs')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            for i in range(len(w)):
                if w[i].isdigit():
                    w[i] = int(w[i])
            dev[w[2]] = Namespace(dict(zip(head, w)))
        return dev

    @property
    def ca(self):
        """
        Returns a dictionary of ca in the following format::

                {'141.2': {'cwnd': 16,
                           'index': 186,
                           'out': 0,
                           'rttavg': 3.8,
                           'rttdev': 2.9,
                           'ssthresh': 8,
                           'target': '141.2',
                           'wnd': 16}}

        """
        dev = dict()
        head = ['index', 'target', 'out', 'cwnd', 'wnd', 'ssthresh', 'rttavg', 'rttdev']
        out = self.get_ethdrv('ca')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            for i in [0, 2, 3, 4, 5]:
                w[i] = int(w[i])
            for i in [6, 7]:
                w[i] = float(w[i])
            dev[w[1]] = Namespace(dict(zip(head, w)))
        return dev

    @property
    def config(self):
        """
        Returns a dictionary of config in the following format::

                {'140.17': {'config': 'N/A',
                            'target': '140.17'},
                 '55.203': {'config': 'com.myco.hba hosts=MEGADETH',
                            'target': '55.203'}}

        """
        dev = dict()
        head = ['target', 'config']
        out = self.get_ethdrv('config')
        m = out.message.splitlines()
        for l in m:
            w = l.split(None, 1)
            try:
                dev[w[0]] = Namespace(dict(zip(head, w)))
            except IndexError:
                logger.critical("can't index %s" % pformat(w))

        return dev

    @property
    def corestats(self):
        """
        Returns a dictionary of corestats in the following format::

            {'arallocfail': 0,
             'arcnt': 0,
             'badcap': 0,
             'badcappair': 0,
             'cecdr': 0,
             'cecrx': 0,
             'cectx': 0,
             'ioqueue': 0,
             'iorequest': 0,
             'ioretire': 0,
             'iosend': 0,
             'iosubmit': 0,
             'sgallocfail': 0,
             'sgbufallocfail': 0,
             'sgbufcnt': 32778,
             'sgcnt': 23,
             'shortcap': 0,
             'srallocfail': 0,
             'srcnt': 0}

        """
        dev = dict()
        out = self.get_ethdrv('corestats')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            for i in w:
                j = i.split('=')
                dev[j[0]] = int(j[1])
        return Namespace(dev)

    @property
    def ctl(self):
        """
        Returns a dictionary of ctl in the following format::

            {'tdeadsecs': 180, 'rqsize': 8192, 'srdebug': 'off',
             'qdepth': 'n/a', 'trace': 'off'}

        """
        dev = dict()
        out = self.get_ethdrv('ctl')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            if w[1].isdigit():
                dev[w[0]] = int(w[1])
            else:
                dev[w[0]] = w[1]
        return Namespace(dev)

    @property
    def devices(self):
        """
        Returns a dictionary of devices in the following format::

            {'141.2': {'device': 'sd66',
                       'target': '141.2',
                       'size': '1000.204GB'}
            }

        """
        dev = dict()
        head = ['device', 'target', 'size']
        out = self.get_ethdrv('devices')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            dev[w[1]] = Namespace(dict(zip(head, w)))
        return dev

    @property
    def elstats(self):
        """
        Returns a dictionary of elstats in the following format::

            {'ArpIn': 18510,
             'ArpOut': 16786,
             'DropNoAvail': 0,
             'DropNoMatch': 0,
             'DropNoSync': 0,
             'DropNoWait': 0,
             'DropQpass': 0,
             'DropReject': 0,
             'DropSeq': 0,
             'HlenErrs': 0,
             'InMsgs': 0,
             'LenErrs': 0,
             'OutMsgs': 0,
             'Retrans': 0,
             'elarp': {0: {'creason': '',
                           'crto': 90,
                           'deathtime': 30000,
                           'delayedack': 0,
                           'flags': 0,
                           'id0': 2093,
                           'local': '510000100401336a!17007',
                           'next': 2093,
                           'opens': 0,
                           'outqlen': 0,
                           'rcvd': 0,
                           'remote': '0000000000000000!0',
                           'resends': 0,
                           'rid0': 0,
                           'rqlen': 0,
                           'rto': 90,
                           'rttseq': 0,
                           'rxidle': 84429880,
                           'sa': 50,
                           'state': 'Listen',
                           'sv': 10,
                           'txidle': 84429880,
                           'unack': 2094},
                       1: {'creason': 'connection closed: ecbclose',
                           'crto': 90,
                           'deathtime': 30000,
                           'delayedack': 0,
                           'flags': 0,
                           'id0': 2093,
                           'local': '510000100401336a!7',
                           'next': 2093,
                           'opens': 0,
                           'outqlen': 0,
                           'rcvd': 0,
                           'remote': '0000000000000000!0',
                           'resends': 0,
                           'rid0': 0,
                           'rqlen': 0,
                           'rto': 90,
                           'rttseq': 0,
                           'rxidle': 84429880,
                           'sa': 50,
                           'state': 'Closed',
                           'sv': 10,
                           'txidle': 84429880,
                           'unack': 2094}},
             'myeladdr': '510000100401336a'}

        """
        dev = dict()
        out = self.get_ethdrv('elstats')
        stats, arp = out.message.split('el arp table:')
        m = stats.splitlines()
        for line in m:
            w = line.split(':')
            if len(w) < 2:
                continue
            v = w[1].strip()
            if v.startswith('5100') and len(v) == 16:
                dev[w[0]] = v
            elif v.isdigit():
                dev[w[0]] = int(v)
        elarp = dict()
        dev['elarp'] = elarp
        dev = Namespace(dev)
        m = arp.splitlines()
        elstates = ('Avail', 'Closed', 'Syncer', 'Syncee', 'Estab', 'Closing', 'Listen', 'Initing')
        for line in m:
            if not line:
                continue
            if not line.startswith(elstates):
                continue
            r = line.rsplit('[', 1)[1].strip(']')  # Extract creason before split
            k = int(line.split()[1].strip('[]'))  # This will extract just the number from [0]
            v = line.split()[2:]
            d = dict()
            d['state'] = line.split()[0]
            d['local'] = v[0]
            d['remote'] = v[1]
            for i in range(2, len(v), 2):
                if v[i] == 'creason':
                    d[v[i]] = r
                    break
                d[v[i]] = int(v[i + 1])
            elarp[k] = Namespace(d)
        dev.elarp = elarp
        return dev

    @property
    def ifstats(self):
        """
        See `HBA Namespace documentation`_. Some fields are chipset depentdent.  Some fields are only
        present when non-zero.

        Returns a dictionary of ifstats in the following format::

                {'1': {'Broadcast Packets Transmitted': 2216, 'drdh': 470, ... }}

        """
        dev = dict()
        hwords = ['reg', 'seen', 'icr', 'ims', 'im', 'Rdbal', 'Rdbah', 'Tdbal', 'Tdbah', 'Rxdctl']
        out = self.get_ethdrv('ifstats')
        t = out.message.split('***')[1:]
        for i in range(0, len(t), 2):
            w = t[i].split()
            w[0] = int(w[0])
            head = ['port', 'model', 'reg']
            d = dict(zip(head, w))
            m = t[i + 1].split('\r\n')
            for l in m:
                l = l.strip()
                if not l:
                    continue
                if l.startswith('link'):  # assume last line
                    w = l.split(':')
                    d[w[0]] = int(w[1].strip())
                    break
                elif l.startswith('speeds'):
                    w = l.split()
                    for i in w[1:]:
                        j = i.split(':')
                        d['link%s' % j[0]] = int(j[1])
                elif l.find('=') is not -1:
                    w = l.split()
                    for i in w:
                        j = i.split('=')
                        if j[0] in hwords:
                            d[j[0]] = j[1]  # XXX Store this as int?
                        elif j[1].isdigit():
                            d[j[0]] = int(j[1])
                        else:
                            d[j[0]] = j[1]
                else:
                    w = l.split(':')
                    v = w[1].strip()
                    if v.isdigit():
                        d[w[0]] = int(v)
                    else:
                        d[w[0]] = v
            dev[d['port']] = Namespace(d)
        return dev

    @property
    def ports(self):
        """
        Returns a dictionary of ports in the following format::

            {0: {'currentlink': 0,
                 'ea': '00100401336a',
                 'index': 0,
                 'maxlink': 10000,
                 'name': 'EHBA-20-E-SFP'},
             1: {'currentlink': 10000,
                 'ea': '00100401336b',
                 'index': 1,
                 'maxlink': 10000,
                 'name': 'EHBA-20-E-SFP'}}

        """
        dev = dict()
        head = ['index', 'name', 'ea', 'currentlink', 'maxlink']
        out = self.get_ethdrv('ports')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            w[0] = int(w[0])
            x = w[3]
            w.pop()
            w.append(int(x.split('/')[0]))
            w.append(int(x.split('/')[1]))
            dev[w[0]] = Namespace(dict(zip(head, w)))
        return dev

    @property
    def release(self):
        """
        Returns release string
        """
        return self.get_ethdrv('release').message.splitlines()[0]

    @property
    def targets(self):
        """
        Returns a dictionary list of targets in the following format::

                {'200.135': [{'active': 1, 'targ': '200.135', 'ea': '0025906694a9', 'ports': 2},
                             {'active': 1, 'targ': '200.135', 'ea': '0025906694a8', 'ports': 2}]

        """
        dev = dict()
        head = ['targ', 'ea', 'ports', 'active']
        out = self.get_ethdrv('targets')
        m = out.message.splitlines()
        for l in m:
            w = l.split()
            w[2] = int(w[2])
            w[3] = int(w[3])
            if not dev.get(w[0]):
                dev[w[0]] = list()
            dev[w[0]].append(Namespace(dict(zip(head, w))))
        return dev

    @property
    def units(self):
        """
        Returns a dictionary of units in the following format::

            {'ea': '002590c23e63', 'product': 'SRX',
             'eladdr': '5100002590c15a6a', 'ports': 2}

        """
        head = ['eladdr', 'product', 'ea', 'ports']
        out = self.get_ethdrv('units')
        l = out.message.splitlines()[0]
        w = l.split()
        w[3] = int(w[3])
        return Namespace(dict(zip(head, w)))
