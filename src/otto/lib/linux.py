#!/usr/bin/env python2.7

from logging import getLogger, NullHandler
from os import environ
import re
from time import time

# these are included here to simply script imports

from otto.lib.contextmanagers import cd

from otto.lib.otypes import AoEAddress, ReturnCode, InitiatorError
from otto.lib.decorators import wait_until

instance = environ.get('instance') or ''
logger = getLogger('otto' + instance + '.lib')
logger.addHandler(NullHandler())


def updatesr(sr, fname, initiator, lun="0"):
    """
    Update this SR(X) with the desired tarc fname, then reconnect.
    """
    import subprocess

    logger.write("updating SR(X) %s to %s" % (sr.shelf, fname))
    sr.remove(lun, force=True)
    ret = sr.make(lun, "update")
    if not ret:
        return ret
    sr.online(lun)
    stat = initiator.verifytarget(AoEAddress(sr.shelf, lun))
    bdev = stat['path']
    cmd = 'dd if=%s of=%s' % (fname, bdev)  # this only works locally
    if subprocess.call(cmd.split()) != 0:
        return ReturnCode(False, 'dd failed')
    sr.update()
    sr.reconnect()
    return ret


def lunisnotavailable(initiator, pattern):
    """
    Returns True if the patters is found as a result of the command execution.
    """

    regExp = re.compile(pattern, re.M)
    cmd = 'ethdrv-stat'
    result = initiator.run_and_check(cmd)
    for line in result.message.splitlines():
        srch = regExp.search(line)
        if srch:
            return True
        else:
            return False


@wait_until(sleeptime=5, timeout=120)
def wait_lunisnotavailable(initiator, pattern):
    return lunisnotavailable(initiator, pattern)


def get_ellisten(elstats):
    if not elstats.get('Listen'):
        raise InitiatorError('Listen entry was not found')
    for k in elstats['Listen']:
        for item in elstats['Listen'][k]:
            if re.match('[0-9a-fA-F]+![0-9a-fA-F]+', item):
                if item.find('0000000000000000!0') == -1:
                    return item
    raise InitiatorError('Listen entry was bad')


@wait_until(timeout=300, sleeptime=5)
def verifylun(obj, lun):
    obj.lnx1.aoeflush(aflag=False)
    aoestat = obj.lnx1.aoestat
    shelflun = '{0}.{1}'.format(obj.srx1_shelf, lun)
    if shelflun in aoestat and not re.search('init', aoestat[shelflun]['path']):
        result = ReturnCode(True)
        result.message = aoestat[shelflun]['path']
        # DEBUG
        obj.log.write("VERIFY LUN: Success for {0}".format(shelflun))
        return result
    # DEBUG PRINT
    obj.log.write(
        "VERIFY LUN: Did not find {0} yet, sleeping {1} seconds to retry...".format(shelflun, verifylun.sleeptime))
    return False


def install_driver(initiator, url, fname):
    """
    Install the HBA driver on initiator a linux box
    """
    rpms = list()
    temp_dir = '/tmp/%s' % int(time())
    initiator.mkdir(temp_dir)
    with cd(initiator, temp_dir):
        initiator.run_and_check('wget --timeout=0 %s/%s -P %s' % (url, fname, temp_dir))
        initiator.untar_package('%s/%s' % (temp_dir, fname), temp_dir)
    initiator.ls(temp_dir)
    for f in initiator.ls(temp_dir):
        if f.endswith(".rpm"):
            p = '%s/%s' % (temp_dir, f)
            rpms.append(p)

    if 1 > len(rpms) > 3:
        initiator.run_and_check('rm -rf %s' % temp_dir)
        return False

    args = ' '.join(rpms)
    ret = initiator.install_rpm('%s' % args, timeout=120)
    if not ret:
        return ret

    ret = initiator.load_module(initiator.coraid_module)
    if not ret:
        return ret
    return initiator.run_and_check('rm -rf %s' % temp_dir)


def uninstall_driver(initiator, dtype='ethdrv'):
    pkgs = [x for x in initiator.packages if '%s' % dtype in x]
    if 1 <= len(pkgs) <= 3:
        pkgs = " ".join(pkgs)
        ret = initiator.uninstall_package(pkgs, timeout=60)
        if not ret:
            return ret

        return initiator.unload_module('%s' % dtype)
