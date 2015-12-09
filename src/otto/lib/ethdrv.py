from otto.lib.compute import average, standard_dev
from otto.lib.otypes import ReturnCode
from otto.lib.solaris import release_parse
from otto.utils import timefmt


def cmp_aoestat_devices(a, d):
    # if a.device != d.device or a.size != d.size:
    if a.size != d.size:
        return ReturnCode(False, 'aoestat %s does not match device %s' % (a, d))
    return ReturnCode(True)


def cmp_aoestat_targets(a, t):
    # Confirm aoestats.paths in targets.ea
    for l in a.port:
        for m in a.paths[l].address:
            found = False
            for n in t:
                mask = bin(n.ports)[2:][::-1]
                if a.paths[l].port < len(mask) and mask[a.paths[l].port] == '1' and m == n.ea:
                    found = True
            if not found:
                return ReturnCode(False, 'aoestat %s does not match targets %s' % (a, t))
    # Confirm targets.ea in aoestats.paths
    for l in t:
        mask = bin(l.ports)[2:][::-1]
        for m in range(len(mask)):
            if mask[m] == '1':
                if l.ea not in a.paths[m].address:
                    return ReturnCode(False, 'targets %s does not match aoestat %s' % (t, a))
    return ReturnCode(True)


def cmp_acbs_ca(a, c):
    if a.index != c.index or a.wnd != c.wnd:
        return ReturnCode(False, 'acbs %s does not match ca %s' % (a, c))
    return ReturnCode(True)


def cmp_hba_ports(h, p):
    checks = (h['port'] != str(p.index),
              h['mac'] != p.ea,
              h['type'] != p.name,
              h['link']['max'] != str(p.maxlink),
              h['link']['speed'] != str(p.currentlink))

    if True in checks:
        return ReturnCode(False, 'hba %s does not match ports %s' % (h, p))

    return ReturnCode(True)


def cmp_hba_ifstats(h, i):
    if h['port'] != str(i.port) or h['type'] != i.model or h['link']['speed'] != str(i.link):
        return ReturnCode(False, 'hba %s does not match ifstats %s' % (h, i))
    return ReturnCode(True)


def cmp_ports_ifstats(p, i):
    if p.index != i.port or p.name != i.model or p.currentlink != i.link:
        return ReturnCode(False, 'ports %s does not match ifstats %s' % (p, i))
    return ReturnCode(True)


def verify_local(initiator):
    aoestat = initiator.aoestat
    acbs = initiator.ethdrv.acbs
    ca = initiator.ethdrv.ca
    cfg = initiator.ethdrv.config
    devices = initiator.ethdrv.devices
    targets = initiator.ethdrv.targets

    for i in aoestat:
        if i not in acbs:
            return ReturnCode(False, 'aoestat %s not in acbs:\%s' % (i, initiator.ethdrv.acbs))
        if i not in ca:
            return ReturnCode(False, 'aoestat %s not in ca' % i)
        if i not in cfg:
            return ReturnCode(False, 'aoestat %s not in config' % i)
        if i in devices:
            n = cmp_aoestat_devices(aoestat[i], devices[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'aoestat %s not in devices' % i)
        if i in targets:
            n = cmp_aoestat_targets(aoestat[i], targets[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'aoestat %s not in targets' % i)

    for i in acbs:
        if i not in aoestat:
            return ReturnCode(False, 'acbs %s not in aoestat' % i)
        if i in ca:
            n = cmp_acbs_ca(acbs[i], ca[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'acbs %s not in aoestat' % i)
        if i not in cfg:
            return ReturnCode(False, 'acbs %s not in config' % i)
        if i not in devices:
            return ReturnCode(False, 'acbs %s not in devices' % i)
        if i not in targets:
            return ReturnCode(False, 'acbs %s not in targets' % i)

    for i in ca:
        if i not in aoestat:
            return ReturnCode(False, 'ca %s not in aoestat' % i)
        if i in acbs:
            n = cmp_acbs_ca(acbs[i], ca[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'ca %s not in acbs' % i)
        if i not in cfg:
            return ReturnCode(False, 'ca %s not in config' % i)
        if i not in devices:
            return ReturnCode(False, 'ca %s not in devices' % i)
        if i not in targets:
            return ReturnCode(False, 'ca %s not in targets' % i)

    for i in cfg:
        if i not in aoestat:
            return ReturnCode(False, 'config %s not in aoestat' % i)
        if i not in acbs:
            return ReturnCode(False, 'config %s not in acbs' % i)
        if i not in ca:
            return ReturnCode(False, 'config %s not in ca' % i)
        if i not in devices:
            return ReturnCode(False, 'config %s not in devices' % i)
        if i not in targets:
            return ReturnCode(False, 'config %s not in targets' % i)

    for i in devices:
        if i in aoestat:
            n = cmp_aoestat_devices(aoestat[i], devices[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'devices %s not in aoestat' % i)
        if i not in acbs:
            return ReturnCode(False, 'devices %s not in acbs' % i)
        if i not in ca:
            return ReturnCode(False, 'devices %s not in ca' % i)
        if i not in cfg:
            return ReturnCode(False, 'devices %s not in config' % i)
        if i not in targets:
            return ReturnCode(False, 'devices %s not in targets' % i)

    for i in targets:
        # check for stale target
        seen = False
        for j in targets[i]:
            if j.ports != 0:
                seen = True
        if not seen:
            continue
        if i in aoestat:
            n = cmp_aoestat_targets(aoestat[i], targets[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'targets %s not in aoestat' % i)
        if i not in acbs:
            return ReturnCode(False, 'targets %s not in acbs' % i)
        if i not in ca:
            return ReturnCode(False, 'targets %s not in ca' % i)
        if i not in devices:
            return ReturnCode(False, 'targets %s not in devices' % i)
        if i not in targets:
            return ReturnCode(False, 'targets %s not in targets' % i)

    hba = initiator.hba_ports
    ports = initiator.ethdrv.ports
    ifstats = initiator.ethdrv.ifstats

    for i in hba:
        if int(i) in ports:
            n = cmp_hba_ports(hba[i], ports[int(i)])
            if not n:
                return n
        else:
            return ReturnCode(False, 'hba %s not in ports' % i)
        if int(i) in ifstats:
            n = cmp_hba_ifstats(hba[i], ifstats[int(i)])
            if not n:
                return n
        else:
            return ReturnCode(False, 'hba %s not in ifstats' % i)

    for i in ports:
        if str(i) in hba:
            n = cmp_hba_ports(hba[str(i)], ports[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'ports %s not in hba' % i)
        if i in ifstats:
            n = cmp_ports_ifstats(ports[i], ifstats[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'ports %s not in ifstats' % i)

    for i in ifstats:
        if str(i) in hba:
            n = cmp_hba_ifstats(hba[str(i)], ifstats[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'ifstats %s not in hba' % i)
        if i in ports:
            n = cmp_ports_ifstats(ports[i], ifstats[i])
            if not n:
                return n
        else:
            return ReturnCode(False, 'ifstats %s not in ports' % i)

    v = initiator.aoeversion
    r = release_parse(initiator.ethdrv.release)
    if r != v:
        return ReturnCode(False, 'release %s does not match version %s' % (r, v))

    # just read; nothing to compare with
    _ = initiator.ethdrv.corestats
    _ = initiator.ethdrv.ctl
    _ = initiator.ethdrv.units
    _ = initiator.ethdrv.elstats

    return ReturnCode(True)


def list_stats(l):
    stats = '\tsamples:%s' % len(l)
    stats += '\taverage:%s' % timefmt(average(l))
    stats += '\tstddev:%s' % timefmt(standard_dev(l))
    stats += '\tmax:%s' % max(l)
    stats += '\tmin:%s' % min(l)
    return stats
