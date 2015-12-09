"""
A collection of functions to simplfy common VSX operations.
"""
import logging
import os
import re

from otto.lib.otypes import ReturnCode
from otto.appliances.vsx import Vsx
from otto.lib.decorators import wait_until

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.lib')
logger.addHandler(logging.NullHandler())


def pv_is_empty(vsx, pv=None):  # TODO: use pv to filter results
    """
    Check if most of the metadata is empty and that extents are
    correctly accounted for. pv parameter is ignored for now
    """
    if not isinstance(vsx, Vsx):
        e = ReturnCode(False)
        e.message = "object is not a Vsx instance"
        return e

    total = 0
    free = 0
    dirty = 0
    meta = 0
    sh = vsx.shelf

    ret = vsx.pvs
    if not ret.status:
        return ret
    p = ret.message
    ret = ReturnCode(True)
    used = calculate_metaext(total, 4096)
    if used != dirty:
        e = "pv has too many dirty extents, should be %d on VSX %s:\n%s" % (used, sh, p)
        logger.error(e)
        ret.status = False
        ret.message = e
    if meta:
        e = "meta extents not zero on VSX %s:\n%s" % (sh, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    if total != free + dirty:
        e = "pv accounting error on VSX %s:\n%s" % (sh, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    return ret


def pool_is_empty(vsx, pool):
    """
    Verifypool makes sure that the pool has no extents allocated.
    """
    if not isinstance(vsx, Vsx):
        e = ReturnCode(False)
        e.message = "object is not a Vsx instance"
        return e

    total = 0
    free = 0
    unique = 0
    shelf = vsx.shelf
    ret = vsx.run_and_check("pools -a %s" % pool)  # TODO: teach this that pools has -a
    if not ret.status:
        return ret
    p = ret.message
    ret = ReturnCode(True)
    m = re.search(r"Total[ \t]+Exts[ \t]+:[ \t]+([0-9]+)[ \t]+", p)
    if m:
        total = int(m.group(1))
    m = re.search(r"Free[ \t]+Exts[ \t]+:[ \t]+([0-9]+)[ \t]+", p)
    if m:
        free = int(m.group(1))
    m = re.search(r"Unique[ \t]+Exts[ \t]+:[ \t]+([0-9]+)[ \t]+", p)
    if m:
        unique = int(m.group(1))
    if total:
        e = "Empty pool %s on %s has %d total extents:\n%s" % (pool, shelf, total, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    if free:
        e = "Empty pool %s on %s has %d free extents:\n%s" % (pool, shelf, free, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    if unique:
        e = "Empty pool %s on %s has %d unique extents:\n%s" % (pool, shelf, unique, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    m = re.search(r"PVs[ \t]+:[ \t]+[0-9]+\.[0-9]+", p)
    if m:
        e = "Empty pool %s on %s has PVs:\n%s" % (pool, shelf, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    m = re.search(r"LVs[ \t]+:[ \t]+(.*)[ \t]+", p)
    if m:
        e = "Empty pool %s on %s has LVs:\n%s" % (pool, shelf, p)
        logger.error(e)
        ret.status = False
        ret.message += "\n%s" % e
    return ret


def lv_is_empty(vsx, lv):
    """
    Verify there are no snap extents left on this LV.
    """
    su = get_snap_used(vsx, lv)
    r = ReturnCode(False)
    if su == "0.000":
        r.status = True
    else:
        r.message = "Stray snap extents on LV %s: %s" % (lv, su)
        logger.error(r.message)
    return r


def get_snap_used(vsx, lv):
    """
    Get space used by an LV's snapshots
    returns a string representing GB 
    """
    helptxt = vsx.run("help")
    if helptxt.find("snaplimit") == -1:
        return "0.000"  # not implemented in this release of the VSX
    nse = vsx.snaplimit([lv])
    if not len(nse):
        return "0.000"  # no snaps
    used = nse[lv].get('used')
    return used


def pv_is_mirrored(vsx, pv):
    """
    Check whether or not a pv is mirrored and
    is done silvering.
    """
    if not isinstance(vsx, Vsx):
        e = ReturnCode(False)
        e.message = "Object is not a Vsx instance"
        return e
    pv = vsx.pvs.get(pv)

    if not pv:
        e = ReturnCode(False)
        e.message = "pv not found"
        return e
    if pv.get('stat') != 'mirrored':
        e = ReturnCode(False)
        e.message = "pv not mirrored"
        return e

    pool = pv.get('pool')
    pv = pv.get('pv')
    tprompt = vsx.prompt
    vsx.prompt = 'VSX EXPERTMODE# '
    vsx.run_and_check('/expertmode')
    cmd = "ls /n/xlate/pool/%s/pv/" % pool
    ls = vsx.run_and_check(cmd)
    if not ls:
        return ls
    ret = ReturnCode(False)
    files = ls.message.split('\r\n')
    for fname in files:
        status = vsx.run_and_check("cat %s/status" % fname)
        fields = status.message.split()
        if fields[0] == "single" and fields[5] == pv:
            ret = ReturnCode(False, fields[0])
            break
        elif fields[0] == "mirrored" and fields[5] == pv:
            ret = ReturnCode(True, fields[0])
            break
        else:
            ret.message = str(fields)
    vsx.prompt = tprompt
    vsx.run("exit")
    return ret


@wait_until()
def wait_pv_is_mirrored(vsx, pv):
    ret = pv_is_mirrored(vsx, pv)
    return ret


def pvs_available(vsx, pvs):
    """
    Verify that all pvs passed in are found in aoestat.
    assuming::

        pvs = ['33.3', '35.0', '35.2', '35.3'] and
        >>> v.aoestat.keys()
        ['33.3', '35.2', '35.3', '35.0']
        >>> pvs_available(v, pvs)
        True
        >>> pvs.append('44.8')
        >>> pvs_available(v, pvs)
        False

    """
    vsx.aoeflush()
    vsx.aoediscover()
    targets = set(vsx.aoestat.keys())
    if type(pvs) == str:
        pvs = {pvs}
    if type(pvs) == list:
        pvs = set(pvs)
    return pvs.issubset(targets)


@wait_until()
def wait_pv_available(vsx, pv):
    ret = pvs_available(vsx, pv)
    return ret


def calculate_metaext(total, perblk):
    """
    Given number of total extents and per block, return estimated meta extents.
    Taken from metaextents() in xlate source
    """
    total = total + perblk - 1
    total = total / perblk
    total *= 8192
    total += 8192
    total = total + 4194304 - 1
    return total / 4194304
