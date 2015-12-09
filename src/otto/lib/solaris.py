#!/usr/bin/env python2.7

from os import environ
import re
from logging import getLogger, NullHandler
import time

import simplejson

from otto.lib.otypes import InitiatorError, ReturnCode
from otto.lib.contextmanagers import cd
from otto.lib.common import wait_file_exists, exists
from otto.lib.decorators import wait_until




# these are included here to simplify script imports

instance = environ.get('instance') or ''
logger = getLogger('otto' + instance + '.lib')
logger.addHandler(NullHandler())

loads = None


def wait_nofiorunning(initiator, expectation=False, timeout=60 * 60):
    return initiator.run_and_check('wait', expectation=expectation, timeout=timeout)


def pkgadd(initiator, package='CORDethdrv', location='.'):
    result = initiator.run_and_check('pkgadd -d %s %s' % (location, package))
    if result.message.count('Installation of <%s> was successful.' % package):
        return ReturnCode(True)
    return ReturnCode(False, 'pkgadd failed: %s' % result.message)


def nofiorunning(initiator):
    """
    Return True if fio is not running
    """
    return not fio_is_running(initiator)


def fio_is_running(initiator):
    """
    Return True if fio is running
    """
    result = initiator.run_and_check("pgrep fio")
    if not result:
        raise InitiatorError(result.message)
    return bool(result.message.splitlines())


def fio(init1, args):
    """
    Pull out fio configuration options from fc and execute
    """
    init1.run_and_check('set +m; rm -f *out *err')
    cmd = 'fio --output-format=json %s> out 2> err &' % args
    logger.info(cmd)
    init1.run(cmd, wait=False)
    for i in range(10):
        n = nofiorunning(init1)
        if not n:
            return ReturnCode(True)
        time.sleep(1)
    return fioresult(init1)


@wait_until(sleeptime=0.2, timeout=10)
def wait_file_exists(initiator, fname):
    return exists(initiator, fname)


def file_exists(initiator, fname):
    return initiator.run_and_check('ls %s' % fname, expectation=False)


def fioresult(initiator, check=True, expectation=False):
    """
    Return the fio result. True: fio stdout. False: fio stderr.
    """
    wait_nofiorunning(initiator, expectation=expectation)
    wait_file_exists(initiator, 'out')
    result = initiator.run_and_check('cat out', expectation=expectation)
    if not result:
        return result
    if not result.message:
        result = initiator.run_and_check('cat err', expectation=expectation)
        if not result:
            return result
        if not result.mesage:
            return ReturnCode(False, 'err: no output')
        else:
            return ReturnCode(False, 'err: %s' % result.message)
    logger.info('fio result:\n%s' % result.message)
    j = simplejson.loads(result.message)
    if check:
        for i in range(len(j['jobs'])):
            if j['jobs'][i]['error'] != 0:
                return ReturnCode(False, 'fio[%d] error code: %s' % (i, j['jobs'][i]['error']))
    return ReturnCode(True, j)


def targ2dev(initiator, targ):
    """
    Return the device name for the TARG.
    """
    if not targ:
        return targ
    n = initiator.lun_exists(targ)
    if not n:
        return ''
    return n.message.device


def dev2disk(initiator, dev):
    """
    Return the sd name for the device name.
    """
    if not dev:
        return dev
    cmd = "iostat -nl 1 " + dev + "|head -n1"
    result = initiator.run_and_check(cmd)
    if result:
        s = result.message.split()
        if len(s) == 3:
            return s[1]
    return ''


def targ2disk(initiator, targ):
    """
    Return the device name for the TARG.
    """
    n = targ2dev(initiator, targ)
    if not n:
        return ''
    return dev2disk(initiator, n)


def get_ellisten(initiator):
    elarp = initiator.ethdrv.elstats.elarp
    for e in elarp:
        if elarp[e].state == 'Listen':
            return elarp[e].local
    return False


def continueUntil(obj, cmd, pattern, tout=300):  # this should probably be rewritten
    starttime = time.time()
    regExp = re.compile(pattern, re.M)
    while True:
        result = obj.run(cmd)
        for line in result.split('\n'):
            srch = regExp.search(line)
            if srch:
                return True
            elif time.time() - starttime > tout:
                return False
            else:
                pass
        time.sleep(30)


def install_driver(initiator, url, fname):
    """
    Install the HBA driver a Solaris system
    """
    temp_folder = "/tmp/%s" % int(time.time())
    initiator.mkdir(temp_folder)
    try:
        with cd(initiator, temp_folder):
            initiator.run_and_check('wget --timeout=0 %s/%s' % (url, fname))
            initiator.run_and_check('tar -zxvf %s' % fname)
            pkgadd(initiator, 'CORDethdrv')
    except InitiatorError as e:
        logger.warning('Something happened during module installation: %s' % e)
    except Exception as e:
        logger.error('Something happened during module installation: %s' % e)
    try:
        initiator.rmdir(temp_folder)
    except:
        initiator.run_and_check('rm -rf %s' % temp_folder)


def uninstall_driver(initiator):
    """
    This function will remove the current installed Coraid module.
    """

    cmd = 'pkgrm -n CORDethdrv'
    try:
        return initiator.run_and_check(cmd)
    except InitiatorError as e:
        logger.warning('Something happened during module installation: %s' % e)
    except Exception as e:
        logger.error('Something happened during module installation: %s' % e)


def wget(initiator, path, fname, loops=10, sleeptime=1):
    initiator.run_and_check('rm %s' % fname, expectation=False)
    initiator.run('wget -q %s/%s' % (path, fname), wait=False)
    for i in range(loops):
        if exists(initiator, fname):
            return ReturnCode(True)
        time.sleep(sleeptime)
    return ReturnCode(False, 'wget: %s/%s not available' % (path, fname))


def release_parse(r):
    r = r.split('.')
    r[2:3] = r[2].split('-')
    head = ['major', 'minor', 'revision', 'release']
    return dict(zip(head, r))
