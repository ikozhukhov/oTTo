"""

A collection of functions to simplfy common SRX operations

"""
import logging
import os
import re
import socket
from time import sleep, time
from random import sample

from otto.lib.py9p.py9p import Sock, Client
from otto.lib.otypes import ReturnCode, ApplianceError, ApplianceUsage, AoEAddress, LibraryError
from otto.lib.pexpect import spawn, TIMEOUT, EOF
from otto.lib.decorators import wait_until


# Import groupby and itemgetter for list to range
from operator import itemgetter
from itertools import groupby

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.lib')
logger.addHandler(logging.NullHandler())


def get_sec(hhmmss):
    """
    turn hh:mm:ss into seconds
    """
    if hhmmss is None:
        return 0
    l = hhmmss.split(':')
    return int(l[0]) * 3600 + int(l[1]) * 60 + int(l[2])


def get_disks(sr, ndisks):
    """
    Get a list of a number of disks from the sr.  If the use_slots attribute
    is set only those disks from that set will be returned.

    :param sr: an srx object
    :param ndisks: number of disks
    :return: a list of disks
    """
    disks = sr.disks
    if len(disks) < ndisks:
        logger.critical("Too few disk %s: %d < %d", sr.shelf, len(disks), ndisks)
        return None
    return sample(disks, ndisks)


def get_luns(sr):
    """
    get a list of available lun numbers
    """
    luns = set(range(255))
    used = set()
    for lun in sr.luns.keys():
        used.add(int(lun))
    available = luns.difference(used)
    return list(available)


def is_inited(sr, lun):
    """
    check if a lun's parity is built

    :param sr: an srx object
    :param lun: a lun number as int or str

    :return: return code with number of seconds until done in message field
    """
    result = ReturnCode(False)
    lun = str(lun)
    l = sr.list.get(lun)
    if not l:
        raise ApplianceUsage("lun not found '%s'" % lun)
    if l.get('state') == 'initing':
        t = sr.when.get(lun)
        if t:
            t = t['time']  # mmmmm
        result = ReturnCode(False, get_sec(t))

    if l.get('state') == 'normal':
        result.status = True
    for component in l.get('raids'):  # SRX 6
        if component.get('state') == 'initing':
            result.status = False
            lc = "%s.%s" % (lun, component['number'])
            wt = sr.when.get(lc)
            if wt:
                t = wt['time'] or '0:0:0'
            else:
                t = '0:0:0'
            result.message = get_sec(t)
            break
        elif component.get('state') == 'normal':
            result.status = True
    return result


@wait_until()
def wait_is_inited(sr, lun, usetime=False):
    """
    Wait until a lun's parity is built

    :param sr: an srx object
    :param lun: a lun number as int or str
    :param usetime: if True this will sleep for (remaining time/10)
    """
    ret = is_inited(sr, lun)
    if usetime:
        if type(ret.message) is int:
            st = ret.message / 10
            if st < 1:
                st = 1
            logger.info("sleeping %s secs for lun %s", st, lun)
            sleep(st)
    return ret


def is_recovering(sr, lun):
    """
    Is this lun recovering?

    :param sr: an srx object
    :param lun: a lun number as str
    :return: returnCode with lun state as message
    """
    result = ReturnCode(False)
    l = sr.list.get(lun)
    if l:
        if sr.version >= 7:
            if l['state'].find('recovering') != -1:
                result.status = True
                result.message = l['state']
        else:
            for component in l.get('raids'):
                if component['state'].find('recovering') != -1:
                    result.status = True
                    result.message = component['state']
    else:
        raise ApplianceError('trying to query status of a non-existing lun: %s' % lun)
    return result


@wait_until(sleeptime=60)
def wait_is_recovering(sr, lun):
    """
    Wait until this lun is recovering

    :param sr: an srx object
    :param lun: a lun number as str
    :return: returnCode with lun state as message
    """
    return is_recovering(sr, lun)


def is_degraded(sr, lun):
    result = ReturnCode(False)
    l = sr.list.get(lun)
    if l:
        if sr.version >= 7:
            if l['state'].find('degraded') != -1:
                result.status = True
                result.message = l['state']
        else:
            for component in l.get('raids'):
                if component['state'].find('degraded') != -1:
                    result.status = True
                    result.message = component['state']
    else:
        raise ApplianceError('trying to query status of a non-existing lun: %s' % lun)
    return result


@wait_until(sleeptime=60)
def wait_is_degraded(sr, lun):
    return is_degraded(sr, lun)


def is_online(sr, lun):
    result = ReturnCode(False)
    l = sr.list.get(lun)
    if l:
        result = ReturnCode(l['online'])
    return result


@wait_until(sleeptime=60)
def wait_is_online(sr, lun):
    return is_online(sr, lun)


def is_failed(sr, lun):
    result = ReturnCode(False)
    l = sr.list.get(lun)
    if l:
        if sr.version >= 7:
            if l['state'].find('failed') != -1:
                result.status = True
                result.message = l['state']
        else:
            for component in l.get('raids'):
                if component['state'].find('failed') != -1:
                    result.status = True
                    result.message = component['state']
    else:
        raise ApplianceError('trying to query status of a non-existing lun: %s' % lun)
    return result


@wait_until(sleeptime=60)
def wait_is_failed(sr, lun):
    return is_failed(sr, lun)


def make_lun(sr, luns, fcenable=False, cache=False):
    """
    Creates one or a series of luns based on a dictionary containing their details.

    :param luns: a dictionary of lun descriptions are created based on a dictionary
    :param fcenable: enable flashcache on the lun after making it
    :param cache:  sent to slot_is_available to mean it is ok to only read the disks command once
                and assume they didn't change in this function. This rate limits log messages and
                is much faster, especially with cec.

    example::

        {
         '0':{'num_disks':2,'type':'raid1','size':'-c','version':'1','iomode':'random'},
         '1':{'num_disks':3,'type':'raid5','size':'2G','version':'0','clean':'False'},
         '2':{'num_disks':4,'type':'raid6rs','size':'-c','version':'0','iomode':'sequential'},
         '3':{'num_disks':4,'type':'raid10','size':'10G','version':'1'},
         '4':{'num_disks':2,'type':'raid0','size':'-c','version':'1'},
         '5':{'num_disks':1,'type':'jbod','size':'4G','version':'1'}
         }

    The dictionary should contain the details of the luns to create and the following categories are mandatory:
        - num_disks: how many disks in the lun
        - type: raid type, or jbod or raw are also valid
        - version: either 0 or 1 are valid


    The following categories are optional in the dictionary:
        - iomode: the default value is based on the lun type
        - clean : if you want the lun to avoid parity initialization, default is to do parity initialization
        - size: the usable size of the disk using the setsize command; if not specified, the current size,
                'setesiz'd or not, of the disk will be used;
                -c is valid and will indicate restore the disk to its actual size.

    """
    # pylint: disable=R0912
    result = ReturnCode(False)

    all_nil = False not in [lun.get('type') in ['nil', 'fnil'] for lun in luns.values()]

    if all_nil:
        for lunid, cfg in luns.items:
            result = sr.make(lunid, cfg.get('type'))
            if not result:
                break
            else:
                result = sr.online(lunid)
        return result

    else:

        disks = ["%s" % x for x in range(sr.slots)]

        # Lets get a list of drives available inside the shelf.
        available_disks = ["%s.%s" % (sr.shelf, x) for x in disks if slot_is_available(sr, x, cache=cache)]

        for lun in luns.keys():

            l = luns[lun]  # Creating a reference to make the code more readable

            # Check if we have enough disk to create the lun
            if len(available_disks) >= l['num_disks']:

                if 'size' in l:  # if size is provided, each disk on that lun will be resized to that size
                    for d in available_disks[:l['num_disks']]:
                        if l['size']:
                            sr.setsize(l['size'], d)
                        else:
                            sr.setsize('-c', d)
                            # Should we skip or not the lun initialization
                if 'clean' in l:
                    skipInit = l['clean']
                else:
                    skipInit = False

                sr.make(lun, l['type'], available_disks[:l['num_disks']], l['version'], skipInit)

                # if iomode has been specified also, we set the mode next
                if 'iomode' in l:
                    sr.setiomode(l['iomode'], lun)
                sr.online(lun)

                if fcenable is True:
                    sr.fcenable(lun)
                    # Remove used disks from the available list
                available_disks = available_disks[l['num_disks']:]
            else:
                result.message = 'Not enough disks to complete creation of lun: %s' % lun
                result.status = False
                return result
        result.status = True
        return result


def make_spare(sr, num_spares=1, min_size=None):
    """
    This function will create any numbre of spare drives in the specified appliance, provided drives are available.

    :param sr: it's an appliance.srx.Srx object
    :param num_spares: the number of spare drives you want to create, by default 1 will be created.

    :returns: ReturnCode indicating if successful.
    """
    d = sr.disks
    slots = d.keys()

    availableDisks = list()
    for x in slots:
        if min_size:
            if d[x]['size'] == 'missing' or not int(d[x]['size'].strip('*').split('.')[0]) >= int(min_size):
                continue
        if slot_is_available(sr, x):
            availableDisks.append(str(sr.shelf) + '.' + x)

    if len(availableDisks) >= num_spares:
        for i in range(num_spares):
            try:
                # sr.run_and_check('spare %s' % availableDisks[i])
                sr.spare(availableDisks[i])
            except ApplianceError as e:
                logger.error('Failed to create spare drive: %s', e)
    else:
        return ReturnCode(False, 'Not enough disk to complete request to create %d spare drives' % num_spares)
    return ReturnCode(True, 'Spare drives were created successfully')


def slot_is_available(sr, slot, cache=False):
    """
    check slots' role as part of a lun, or if is marked as an spare or cache disk or if it missing.

    :param slot: the slot we want to check, it's a str or int in the form: '3', '12' or '34'.
    :param cache: is it ok to assume that sr.disks is unchanged while we are in this function?

    :return: a ReturnCode object, message contains the output of disks command for the specified slot

    """
    # !!this is a surprisingly complicated function!! You have been warned.

    if sr.use_slots and slot not in sr.use_slots:
        return ReturnCode(status=False, message="masked by use_slots")

    t = sr.use_slots

    sr.use_slots = [slot]
    diskcache = sr.cache.get('disks')

    if not ((cache and diskcache) and diskcache.get(slot)):

        disk = getattr(sr, "s%s" % slot)
        if not disk.get('model'):
            sr.use_slots = t
            return ReturnCode(status=False, message=str(disk))
    else:
        disk = diskcache.get(slot)

    sr.use_slots = t

    if disk['role'] in ['', None]:
        if disk['size'] != 'missing':
            status = True
        else:
            status = False
    else:
        status = False
    return ReturnCode(status=status, message=disk)


def _kfscmd(sr, cmd):
    """
     Kfs is a local user-level file server for a Plan 9 terminal
          with a disk.  Kfscmd transmits commands to the kfs server
          (see kfs(4)). The -n option changes the name of the kfs ser-
          vice to kfs.name (by default, full name is just kfs).

    :param cmd: allow turns off permission checking (to simplify administration)

    """
    cmd = 'disk/kfscmd %s' % cmd
    return sr.run_and_check(cmd)


def rdfail_preboot(sr, lun, disk=None):
    """
    **WARNING: usage of rdfail can cause an un-responsive appliance.**

    Set the rdfail flag on a drive.  Values stored inside /rc/bin/srlocalpreboot,
    to prevent shield errors during boot.

    :param lun: the lun id we want to affect, we will select an element from that lun and fail it

    :param disk: if we are looking to fail a particular element inside the lun

    :return: a ReturnCode object, status of True if successful with message indicating which device
             in the appliance was affected otherwise a False value will be returned.

    """

    result = ReturnCode(False)

    # The following command will allow us to modify content inside files in the SRX
    if not _kfscmd(sr, 'allow'):
        return result

    # Lets get the info from the lun we want to fail a disk
    l = sr.list.get(lun)

    for c in l['raids'][0]['components']:
        regExp = re.search(r'd+.(d+)', c['device'])

        if regExp and (regExp.group(1) == disk or disk is None):
            disk2fail = regExp.group(1)
            if sr.version >= 7:
                cmd = "echo \'echo rdfail on > /n/raiddev/%s/ctl\' > /n/kfs/srx/srlocal0" % disk2fail
            else:
                cmd = "echo \'echo rdfail on > /raiddev/%s/ctl\' > /rc/bin/srlocalpreboot" % disk2fail
            try:
                result = sr.run_and_check(cmd)
                result.message = '/raiddev/%s/ctl' % disk2fail
            except ApplianceError as e:
                result.messsage = e
            break

    return result


def rdfail(sr, lun, disk=None):
    """
    **NOTE: the usage of rdfail can produce  an un-responsive appliance.**
    set the rdfail flag of a drive to 'on'

    :param lun: the lun id we want to affect, we will select an element from that lun and fail it
    :param disk: if passed, the drive we want to set the rdfail flag.

    :return: a return code of True if the flag was reset back to on; False otherwise.


    """

    result = ReturnCode(False)

    # Lets get the info from the lun we want to fail a disk
    l = sr.list.get(lun)

    if not l:
        result.message = "Seems like lun %s does not exist" % lun
        return result

    for c in l['raids'][0]['components']:
        regExp = re.search(r'd+.(d+)', c['device'])

        if regExp and (regExp.group(1) == disk or disk is None):
            disk2fail = regExp.group(1)
            cmd = "echo rdfail on > /raiddev/%s/ctl" % disk2fail

            if sr.version >= 7:
                result = sr.expert_run(cmd)
            else:
                result = sr.run_and_check(cmd)

            result.message = '/raiddev/%s/ctl' % disk2fail
            return result
    return result


def rdunfail(sr, disk):
    """
    unset the rdfail flag on a drive

    :param sr: an srx object
    :param disk: drive on which to set the rdfail flag, we test the flag to verify it is on, before setting it

    Return: a ReturnCode True if flag was set to off False if failed (drive was already off or missing.
    """

    result = ReturnCode(False)

    d = sr.disks.get(disk)

    if d and d['rdfail'] == 'on':  # Let's test for the result of sr.disks.get, just in case that disk is missing.
        cmd = "echo rdfail off > /raiddev/%s/ctl" % disk
        try:
            if sr.version >= 7:
                result = sr.expert_run(cmd)
            else:
                result = sr.run_and_check(cmd)
        except ApplianceError, e:
            logger.error('A problem was found trying to rdunfail disk %s: %s', disk, e)

    return result


def fail_disk(sr, lun, element=None, raid='0'):
    """
    Fail a single disk on a lun, if not specified, the function will choose one for you.

    :param sr: an srx object
    :param lun: this is the lun id from which we want to fail an element
    :param element: if this is passed, the element we want to fail, it's in the form '1','3' or '5'
    :param raid: this value was for concat raids and is not used anymore the default value is 0

    :returns: A ReturnCode object the message contains the disk that was failed or if no disk was failed at all.
    """

    result = ReturnCode(False, 'err: No disk was failed in lun %s' % lun)

    # get a list of disks for lun
    luns = sr.list

    # We search among the components of the lun for one to fail.
    for l in luns[lun]['raids'][int(raid)]['components']:
        if element is None or element == l['position']:
            if l['stat'] == 'normal':
                try:
                    drive = '%s.%s.%s' % (lun, raid, l['position'])
                    result = sr.fail(drive)
                    result.message = drive
                    return result
                except ApplianceError as e:
                    result.message = e
                    return result
    return result


def unfail_disk(sr, lun, element, raid='0', replace_slot=None):
    """
    Unfail a disk belonging to a lun and specified in the form: lun.raid.slot

    :param sr: an srx object
    :param lun: this is the lun id from which we want to unfail an element
    :param element: the element, inside the lun, we want to unfail
    :param raid: deprecated with concatenated RAID the default value is 0

    :return: a ReturnCode object True if the disk was unfailed, otherwise False with the error in message.
    """
    try:
        if sr.version >= 7:
            return sr.replacedrive('%s.%s.%s' % (lun, raid, element), slot='%s.%s' % (sr.shelf, replace_slot))
        elif sr.version < 7:
            return sr.unfail('%s.%s.%s' % (lun, raid, element))
    except ApplianceError as e:
        result = ReturnCode(False, e)
        return result


def save_sos(sr, loc='.'):
    """
    Save a copy of sos output into a local file

    :param sr: an srx object
    :param loc: file destination drectory

    filename will be in the following format::

        sos_1521_15_1387393873.113084.txt

    """
    result = ReturnCode(False)

    sos_output = sr.sos

    # File name will be a combination of model+shelfID+time
    file_name = 'sos_%s_%s_%s.txt' % (sr.model, sr.shelf, str(time()))

    # full path + file name where sos will be saved.
    sos_file = '%s/%s' % (loc, file_name)

    try:
        f = open(sos_file, 'w')
        for line in sos_output.split('\r\n'):
            f.write('%s\n' % line)
        f.close()
        result.status = True
        result.message = 'sos output stores in %s' % sos_file
    except IOError as e:
        result.message = e

    return result


def sos7x(srx7, loc='./'):
    """
    This is an SRX-7.x specific function.  It takes an instance of the
    otto.appliances.srx7::Srx class, runs it's sos() method, then grabs
    the scp statement, executes it, reads in the scp'd file's contents,
    and returns a ReturnCode with the sos output in the message.

        :param srx7: an srx object
        :param loc: file destination drectory

    """
    # first, execute the sos command on the SRX (not 'sos -t',
    # because pexpect fails to handle all it's output correctly),
    # then find the suggested 'scp' command to run on the local host
    r = srx7.sos
    n = r.rfind('scp')
    if n == -1:
        logger.error("failed to find scp statement from sos")
        return ReturnCode(False, r)

    cmd = r[n:].strip('\r\n')
    args = cmd.split()
    if len(args) < 3:
        logger.error("failed to scp the sos")
        return ReturnCode(False, r)

    fname = args[1].split(':')
    if len(fname) < 2:
        logger.error("failed to identify the scp'd file")
        return ReturnCode(False, r)

    fname = fname[1]
    args[2] = loc
    fname = "{0}/{1}".format(loc, fname)
    cmd = "{0} {1} {2}".format(args[0], args[1], args[2])
    logger.debug(cmd)

    # execute the scp command to copy the file over to the local host
    # try 10 times, b/c sometimes SSH is delayed in coming up after Cec
    # is already able to connect & run commands
    n = 0
    while True:
        pid = spawn(cmd)
        i = pid.expect_exact([r"password:", EOF, TIMEOUT])
        if i == 0:
            pid.sendline(srx7.password)
            pid.expect([EOF], timeout=60)  # wait for xfer to finish!
            pid.close()
            break
        elif i == 1:
            e = "EOF: '%s': %s" % (cmd, pid.before)
        elif i == 2:
            e = "TIMEOUT: '%s'" % cmd
        logger.error(e)
        pid.close()
        n += 1
        if n > 9:
            return ReturnCode(False, e)

    # read in the scp'd file's contents and return them
    f = open(fname, 'r')
    if not f:
        logger.error("failed to open '%s' for reading", fname)
        return ReturnCode(False, r)
    ret = f.read()
    f.close()
    return ReturnCode(True, ret)


def mask(sr, luns, add=None, remove=None, expectation=True):
    """
    Add or remove these masks for these luns in SRX-7.x.
    The arguments 'luns', 'add', & 'remove' can be either a single
    string or a list of strings.  Adding the '+' and '-' symbols is
    handled for the user.

    :param sr: an srx object
    :param luns: luns to mask
    :param add:  either a string or a list of strings
    :param remove: either a string or a list of strings
    :param expectation: set to False to supress Exception

    """
    if type(luns) == list:
        luns = ' '.join(luns)
    if add is None and remove is None:
        raise ApplianceUsage("must either add or remove masks from luns '%s'" % luns)
    if add is None:
        add = str()
    elif type(add) == str:
        if not add.startswith('+'):
            add = '+%s' % add
    elif type(add) == list:
        add = ' +'.join(add)
    if remove is None:
        remove = str()
    elif type(remove) == str:
        if not remove.startswith('-'):
            remove = '-%s' % remove
    elif type(remove) == list:
        remove = ' -'.join(remove)
    cmd = "mask %s %s %s" % (remove, add, luns)
    return sr.run_and_check(cmd, expectation=expectation)


def disable_guard(sr, expectation=True):
    """
    Turn of the guard facility on an SR appliance
    So that a raid will be allowed to fail by failing disks
    """
    return sr.run_and_check("echo guard off > /raid/ctl", expectation=expectation)


def lun_is_available(sr, lun):
    """
    returns a Bool indicating whether or not
    a lun number is available for use

    :param sr: an srx object
    :param lun: target lun
    """
    if type(lun) == AoEAddress:
        lun = str(lun.minor)
    available = True
    if lun in sr.list:
        available = False
    return available


def is_ssd(sr, disk):
    """
    determine if a drive is an SSD by rotation rate
    :param sr: an srx object
    :param disk: disk
    """
    # SSDs have a rotational rate of 0
    ret = sr.run_and_check("drives -R %s" % disk)
    if not ret:
        return ret
    cline = ret.message.strip().split(sr.lineterm)
    cline = cline[1].split()
    if cline[1] == '0':
        return True


def add_ssd_to_fc(sr, nssds=1):
    """
    Add SSD a number to flashcache pool

    :param sr: an srx object
    :param nssds: number of drives ot add
    """

    ret = ReturnCode(False)

    disks = sr.disks.keys()
    available_disks = ["%s.%s" % (sr.shelf, x) for x in disks if slot_is_available(sr, x, cache=True)]

    ssds = ["%s" % d for d in available_disks if is_ssd(sr, d)]

    if not ssds or len(ssds) < nssds:
        ret.message = 'No more ssds to add to flashcache'
        ret.status = False
        return ret
    ssds.reverse()  # implicitly sorts ssds wrt slot numbers
    for _ in range(nssds):
        ret = sr.fcconfig(ssds.pop())
        if not ret:
            break
    return ret


def elproxyna(sr, elp=None):
    """
    Use elproxy with no authentication on an SRX to connect to an EL 9P server.
    Return a py9p.Client given an SRX and EL server address!port
    (e.g. '5100001004013368!17007').

    :param sr: an srx object
    :param elp: el address and port of namespace target
    """
    sr.expert_run("aux/listen1 -t 'tcp!*!17771' /bin/elproxy &")
    s = socket.create_connection((sr.host, 17771))
    if not elp:
        elp = sr.expert_run("cat /net/el/addr").message + '!17007'
    a = 'el!' + elp + '\n'

    s.sendall('%4.4d\n' % len(a))  # send request
    s.sendall(a)
    s.recv(5)  # get response length
    r = s.recv(512)  # get response
    if r.find('OK ') == -1:
        raise ApplianceError('elproxyna: %s' % r)
    ns = Client(Sock(s, chatty=0), user='nobody')
    return ns


def list_to_range(ilist, shelf=None):
    """
    Converts a list of drives in the form shelf.slot or slot to a list of contiguous
    ranges. When provided a value for shelf, it returns a list with the elements prepended
    with shelf number.

    For Example::

        slots = ['1', '2', '5', '6', '7', '8', '11', '22', '23']
        shelf_slots = ['1.1', '1.2', '1.5', '1.6', '1.7', '1.8', '1.11', '1.22', '1.23']
        [1]: a = list_to_range(slots)
        [2]: b = list_to_range(shelf_slots)
        [3]: c = list_to_range(slots, shelf='2')
        [4]: d = list_to_range(shelf_slots, shelf='2')

    Returns::

        a = ['1-2', '5-8', '11', '22-23']
        b = ['1.1-2', '1.5-8', '1.11', '1.22-23']
        c = ['2.1-2', '2.5-8', '2.11', '2.22-23']
        d = ['1.1-2', '1.5-8', '1.11', '1.22-23']

    Note here that a change in shelfid did not matter

    """
    # pylint: disable= W0141
    rlist = list()
    olist = list()
    for d in ilist:
        sd = d.split('.')
        if len(sd) == 2:
            shelf = sd[0]
            slot = sd[1]
        elif len(sd) == 1:
            slot = sd[0]
        else:
            raise LibraryError("for %s could identify slot in %s" % (d, sd))
        rlist.append(int(slot))
    rlist = [map(itemgetter(1), g) for _, g in groupby(enumerate(rlist), lambda (i, x): i - x)]
    for i in rlist:
        if len(i) > 1:
            olist.append("{0}-{1}".format(i[0], i[0] + (len(i) - 1)))
        else:
            olist.append("{0}".format(i[0]))
    if shelf:
        for i in range(len(olist)):
            olist[i] = "{0}.{1}".format(shelf, olist[i])
    return olist


def fourk_drives(sr):
    """
    locate drives in the appliance that have 4K sectors
    :return list of slots
    """

    fourk_slots = list()
    disks = sr.disks
    for d in disks.keys():
        if disks[d]['physectorsize'].find('4096') > -1:
            fourk_slots.append(d)

    return fourk_slots
