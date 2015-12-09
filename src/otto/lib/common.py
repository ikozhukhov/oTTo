from collections import OrderedDict
from time import sleep, time
import re

import otto.connections.ssh
from otto.lib.otypes import ReturnCode
from otto.lib.decorators import wait_until


def get_elstats(initiator):
    """
    This function will translate data from /dev/ethdrv/elstat into a dictionary.
    """
    elstat = OrderedDict()

    if initiator.os == 'solaris':
        fname = '/dev/ethdrv/elstats'
    elif initiator.os == 'linux':
        fname = '/proc/ethdrv/elstats'
    else:
        raise (NotImplementedError('%s does not support elstats' % initiator.os))

    if isinstance(initiator, otto.connections.ssh.Client):
        sftpsession = initiator.open_sftp()
        try:
            fh = sftpsession.open(fname)

            result = ReturnCode(True)
            result.message = fh.read()
        except Exception as e:
            result = ReturnCode(False)
            result.message = str(e)
            return result

    else:
        cmd = 'cat %s' % fname
        result = initiator.run_and_check(cmd)

    if result:
        for line in result.message.splitlines():
            if line:
                if line.startswith('Listen'):
                    if not elstat.get('Listen'):
                        elstat['Listen'] = dict()
                    k = line.split()[1].strip('[]')  # This will extract just the number from [0]
                    v = line.split()[2:]
                    elstat['Listen'][k] = v
                elif line.startswith('Closed'):
                    if not elstat.get('Closed'):
                        elstat['Closed'] = dict()
                    k = line.split()[1].strip('[]')  # This will extract just the number from [0]
                    v = line.split()[2:]
                    elstat['Listen'][k] = v
                else:
                    kvpair = line.split(':')
                    k = kvpair[0]
                    if len(kvpair) < 2:
                        continue
                    v = kvpair[1].strip()
                    elstat[k] = v
    return elstat


@wait_until(sleeptime=1, timeout=15)
def wait_lun_exists(initiator, lun):
    return initiator.lun_exists(lun)


def exists(initiator, fname, expectation=False):
    """
    Check the precence of a path or filename. Setting expectation to
    True will cause an exception to be raised if the name does not exist.
    """
    return initiator.run_and_check('test -e %s' % fname, expectation=expectation)


@wait_until(sleeptime=0.2, timeout=10)
def wait_file_exists(initiator, fname):
    return exists(initiator, fname)


def log_result(l, status, mesg):
    l.info('status: %s, value: %s' % (status, mesg))
    result = {'status': status, 'value': mesg}
    return result


def continueUntil(obj, cmd, pattern, tout=150):
    starttime = time()
    regExp = re.compile(pattern, re.M)
    while True:
        result = obj.run(cmd)
        for line in result.split('\n'):
            srch = regExp.search(line)
            if srch:
                return True
            elif time() - starttime > tout:
                return False
            else:
                pass
        sleep(2)
