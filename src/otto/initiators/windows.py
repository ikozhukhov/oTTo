#!usr/bin/env python2.7
"""
Windows

These are classes for interacting with Windows hosts.
Logging has to be configured from the script that instantiates
the class.  Currently mostly only methods for provisioning are
available.

To use this module Openssh needs to be installed on the remote machine

Basic Usage::

        from otto.appliances import esx

        s = Windows(uname, host, passwd)
        s.connect()
        logger.info(s.release)
        s.disconnect()

"""

import re
import time
import logging
import os
import csv
from StringIO import StringIO
from string import ascii_letters
from collections import defaultdict

from otto.connections.ssh_pexpect import Ssh
from otto.utils import lun_bytes
from otto.lib.otypes import ReturnCode, InitiatorError, InitiatorUsage, Namespace
import otto.lib.pexpect
from otto.lib import server_constants

ethdrvadm = '"C:\Program Files\Coraid\HBA Tools\ethdrvadm.exe"'
ethdrvctl = '"C:\Program Files\Coraid\HBA Tools\ethdrvctl.exe"'
devcon = "c:\\softwares\\amd64\\devcon.exe"
wmic = 'wmic'
instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.initiators')
logger.addHandler(logging.NullHandler())


class Initiator(object):
    def __init__(self, coraid_module):
        self.coraid_module = coraid_module
        self._aoeversion = None

    def aoediscover(self):  # STUB
        """
        Call the driver's discover command.  Returns ReturnCode object
        """
        ret = ReturnCode(False)
        return ret

    def aoeflush(self, aflag=True):  # STUB
        """
        call the driver's flush command and return a ReturnCode object.
        """
        ret = ReturnCode(False)
        return ret

    def aoerevalidate(self, shelf_lun):  # STUB
        """
        Calls aoe-revalidate e{shelf}.{lun} on initiator
            Accept a string e.g. 'e4.1' or AoEAddress
            Returns ReturnCode object
        """
        ret = ReturnCode(False)
        return ret

    @property  # STUB
    def aoestat(self):
        """
        Returns a dictionary of either the 'aoe-stat' output, or
        the 'ethdrv-stat' output (based on self.coraid_module) in the
        following format::

                {'38.34': {'claim': None, 'iounit': None, 'file': '38.34', 'device': None, 'path': None, 'port': [],
                           'size': '1000.204GB', 'paths': None, 'target': '38.34', 'ifs': None, 'state': [],
                           'targpath': defaultdict(<function <lambda> at 0x10e421c80>, {})}

        """
        return {}

    @property  # STUB
    def aoeversion(self):
        """
        Returns the driver version as a dict::

            {   'major': 6,
                'minor': 0,
                'revision' : 1,
                'release': 'R5'
                }
        """
        ret = {'major': None,
               'minor': None,
               'revision': None,
               'release': str()}
        self._aoeversion = ret
        return ret

    def claim(self, lun):  # STUB
        """
        claim a LUN
        accept string or AoEAddress type
        Return : ReturnCode
        """
        ret = ReturnCode(False)
        return ret

    def loadaoe(self):  # STUB
        """
        Loads the AoE driver module defined in self.coraidmodule:
        either the HBA driver 'ethdrv', or the software initiator 'aoe'.
        """

        ret = ReturnCode(False)
        return ret

    def unloadaoe(self):  # STUB
        """
        Unload the AoE driver module defined in self.coraid_module

        Returns a ReturnCode object
        """
        ret = ReturnCode(False)
        return ret


class Windows(Ssh, Initiator):  # todo: this class should be named otto.initiators.windows.Ssh
    """
    A class for interacting with the windows using ssh.

    extended parameters::

        expectation     (Boolean) if False the library will not raise exceptions for error: or usage:
        force           (Boolean) if True the method walks through the acceptance dialog

    """

    def __init__(self, user, host, password, prompt='>'):
        super(Windows, self).__init__(user, host, password, prompt)
        self.logger = logging.getLogger('otto.initiators')
        self.prompt_exact = False
        self.volume_name = None
        self.os = 'windows'

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
        # ToDo: this is non-sense for a windows host fix it
        if result.message.startswith('Error:'):
            logger.error(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = InitiatorError(failmsg)

        elif result.message.startswith('Usage:'):
            logger.critical(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = InitiatorUsage(failmsg)
            result.status = False

        if not expectation:
            return result
        elif not result.status:
            raise e
        return result

    def claim(self, lun):
        """
        This function claims the LUN
        Return : False (Failure)
                 True (Sucess)
        """
        cmd = "%s claim %s" % (ethdrvadm, lun)
        message = "Claiming LUN : %s" % lun
        self.logger.info(message)
        output = self.run(cmd)
        self.logger.info(output)

        if output.find("target not applicable for operation") > -1:
            message = "LUN : %s is already claimed. Please release it or try Claiming for another LUN" % lun
            self.logger.info(message)
            return False

        if output == "":
            message = "CMD:%s failed to execute" % cmd
            self.logger.error(message)
            return False

        return True

    def wmic_query(self, query):
        """
        This method should be use where possible to execute wmic queries.
        """
        cmd = "%s %s /Format:csv" % (wmic, query)
        res = list()
        t = self.timeout
        self.timeout = 300
        try:
            ret = self.run_and_check(cmd)
            if query == 'PRODUCT GET NAME':
                reader = csv.DictReader(StringIO(ret.message), fieldnames=['Host', 'Name'])
            else:
                reader = csv.DictReader(StringIO(ret.message))
            for row in reader:
                res.append(row)
        finally:
            self.timeout = t
        return res

    @property
    def bios(self):
        query = "BIOS Get"
        res = self.wmic_query(query)
        return res[0]

    @property
    def cpu(self):
        query = "cpu get"
        res = dict()
        cpus = self.wmic_query(query)
        for c in cpus:
            res[c.get('DeviceID')] = c
        return res

    def release_lun(self, lun):
        logger.info("deprecated")
        return self.release(lun)

    def release(self, lun_id, force=None):
        """
        This function will release the claim:
        Argument : LUN_ID
                   force = None :
                   force = 'force' : force release
        Return : False Failure
                 True Success
        """
        if force == 'force':
            cmd = "%s release /force %s" % (
                ethdrvadm, lun_id)
        else:
            cmd = "%s release %s" % (ethdrvadm, lun_id)

        message = "Releasing LUN : %s" % lun_id
        self.logger.info(message)

        output = self.run(cmd)
        self.logger.info(output)

        if output == "":
            message = "CMD : %s Failed" % cmd
            self.logger.error(message)
        if output.find("invalid target") > -1:
            message = "LUN %s is Invalid" % lun_id
            self.logger.info(message)

        return True

    def get_list_of_disks(self):
        logger.info("deprecated")
        return self.disks

    @property
    def disks(self):
        """
        return a list of disk on the system
        """
        disk_list = []  # todo this should return all the data in a dict see volumes

        t = self.prompt
        self.prompt = ">"

        self.run('diskpart')
        output = self.run('list disk')
        self.prompt = t
        self.run('exit')

        if output == "":
            message = "List of Disks could be retrieved"
            self.logger.error(message)
            raise InitiatorError("no disks?")

        output = output.split('\r\r\n  ')[2:]
        for element in output:
            disk_list.append(element.split()[1])

        return disk_list

    def get_list_of_volume(self):
        logger.info("deprecated")
        return self.volumes

    @property
    def volumes(self):
        """
        return the volumes on the system
        """
        v = {}
        t = self.prompt
        self.prompt = ">"

        self.run('diskpart')
        output = self.run('list volume')
        self.prompt = t
        self.run('exit')

        if output == "":
            message = "List of Volume cannot be retrieved"
            self.logger.error(message)
            return False
        output = output.split('\r\r\n  ')[1:]

        hdr = output.pop(0)
        hdr = hdr.split()

        for i, _ in enumerate(hdr):
            hdr[i] = len(hdr[i]) + 2

        for line in output:
            l = []
            line = line.lstrip()
            for field in hdr:
                l.append(line[0:field])
                line = line[field:]  # cutting field
            for i, _ in enumerate(l):
                l[i] = l[i].strip()
            vdict = dict(zip(['volume', 'letter', 'label', 'fs', 'type', 'size', 'status', 'info'], l))
            vdict['volume'] = vdict['volume'].split()[1]
            vdict['size'] = lun_bytes(vdict['size'][:-1])
            v[vdict['volume']] = vdict
        return v

    def create_volume(self, disk_number, size=None, volume_type=None, disk_type=None):
        """
        creates the volume(Volume Simple or Partition Primary).
        """
        self.volume_name = self.get_driveLetter()[0]
        t = self.prompt
        self.prompt = ">"
        self.run_and_check('diskpart')
        self.run_and_check('select disk=%s' % disk_number)
        self.run_and_check('online disk')
        self.run_and_check('ATTRIBUTES DISK CLEAR READONLY')
        if (disk_type is not None) and (disk_type.lower() == ('gpt' or 'mbr')):
            self.run_and_check('convert %s' % (disk_type.lower()))
        if volume_type == ('simple' or 'Simple' or 'SIMPLE'):
            self.run('convert dynamic')

        if size is not None:
            if volume_type == ('simple' or 'Simple' or 'SIMPLE'):
                cmd = 'create volume simple SIZE=%s' % size
            else:
                cmd = 'create partition primary SIZE=%s' % size
        else:
            if volume_type == ('simple' or 'Simple' or 'SIMPLE'):
                cmd = 'create volume simple'
            else:
                cmd = 'create partition primary'
        output = self.run(cmd)
        if (output.find("It may be that there is insufficient") > -1) and (size is not None):
            message = "Volume Size provided is too large, exceeding the size of the disk."
            self.logger.error(message)
            return False
        else:
            pattern1 = re.compile('success')
            pattern2 = re.compile("DiskPart succeeded in creating the specified partition")

            if not (pattern1.search(output) or pattern2.search(output)):
                message = "Volume Creation failed on Disk: %s" % disk_number
                self.logger.error(message)
                return False
        self.run_and_check('assign LETTER=%s' % self.volume_name)
        self.prompt = t
        self.run_and_check('exit')

        return True

    def create_stripe_volume(self, disk_numbers, disk_type, size=None):
        """
        This function creates volume of stripe type.

        Arguments: disk_numbers(list eg: [1,2,3]) - volume across which needs to be created.
                   size - size of the volume
                   disk_type = 'MBR' or 'GPT'

        Return : True - Successful
                 False - Failure

        """
        if type(disk_numbers) is list:
            if len(disk_numbers) < 1:
                message = "Please pass more than 1 disk numbers to create Stripe Volume" % disk_numbers
                self.logger.error(message)
                return False
            else:
                if disk_type.lower() not in ['mbr', 'gpt']:
                    message = "disk_type passed should be 'MBR' or 'GPT' type"
                    self.logger.info(message)
                    return False
                disk_option = ','.join(disk_numbers)
        else:
            message = "Please pass disk numbers as list"
            self.logger.info(message)
            return False

        self.volume_name = self.get_driveLetter()[0]
        t = self.prompt
        self.prompt = ">"
        self.run_and_check('diskpart')
        for element in disk_numbers:
            self.run_and_check('select disk=%s' % element)
            self.run_and_check('online disk')
            self.run_and_check('ATTRIBUTES DISK CLEAR READONLY')
            self.run_and_check('convert %s' % disk_type)
            self.run_and_check('convert dynamic')
        if size is not None:
            cmd = 'create volume stripe SIZE=%s Disk=%s' % (size, disk_option)
        else:
            cmd = 'create volume stripe Disk=%s' % disk_option
        output = self.run(cmd)
        if output.find("DiskPart successfully created the volume.") < 0:
            message = "Creation of stripe volume failed"
            self.logger.error(message)
            return False
        self.run_and_check('assign Letter=%s' % self.volume_name)
        self.prompt = t
        self.run_and_check('exit')

        return True

    def create_mirror_volume(self, disk_numbers, size=None, disk_type=None):
        """
        This function will create mirror volume on two disk.
        Both disk needs to be dynamic to create dynamic volume

        Arguments::
            disk_numbers = [Disk1,Disk2] always in list.
            size = size of the volume to be created
            disk_type = 'mbr' or 'gpt' if None, disk be default

        """
        if type(disk_numbers) is not list:
            message = "Argument - disk_numbers:%s not list type" % disk_numbers
            self.logger.error(message)
            return False

        if len(disk_numbers) != 2:
            message = "Two Disks are required for creating Mirror Volume"
            self.logger.error(message)
            return False
        if disk_type is not None:
            if disk_type.lower() != ('gpt' or 'mbr'):
                message = "Please pass argument disk_type as 'mbr' or 'gpt'"
                self.logger.error(message)
                return False

        self.volume_name = self.get_driveLetter()[0]
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        for disk in disk_numbers:
            self.run_and_check('select disk=%s' % disk)
            self.run_and_check('online disk')
            self.run_and_check('ATTRIBUTES DISK CLEAR READONLY')
            if disk_type is not None:
                self.run_and_check('convert %s' % disk_type)
            self.run_and_check('convert dynamic')

        disk_option = ','.join(disk_numbers)
        if size is not None:
            cmd = 'create volume mirror SIZE=%s Disk=%s' % (size, disk_option)
        else:
            cmd = 'create volume mirror Disk=%s' % disk_option

        output = self.run(cmd)
        if output.find("DiskPart successfully created the volume.") < 1:
            message = "Creation of mirror volume failed"
            self.logger.error(message)
            return False

        self.run_and_check('assign Letter=%s' % self.volume_name)
        self.prompt = t
        self.run_and_check('exit')

        return True

    def create_spanned_volume(self, disk_numbers, size=None, disk_type=None):
        """
        This fuction creates a simple volume and then spanned

        Attributes:

            disk_numbers:   list of disk numbers, should always be 2 eg :: [disk1,disk2]
            disk1: on which the simple volume will be created
            disk2: on which the volume will be spanned accross
            size: size of the volume to be created in MBs
            disk_type: 'MBR' or 'GPT'

        """
        try:
            if type(disk_numbers) is not list:
                message = "Argument - disk_numbers:%s not list type" % disk_numbers
                self.logger.error(message)
                return False

            if len(disk_numbers) != 2:
                message = "Two Disks are required for creating Mirror Volume"
                self.logger.error(message)
                return False
            if disk_type is not None:
                if disk_type.lower() != ('gpt' or 'mbr'):
                    message = "Please pass argument disk_type as 'mbr' or 'gpt'"
                    self.logger.error(message)
                    return False

            self.volume_name = self.get_driveLetter()[0]

            t = self.prompt
            self.prompt = ">"

            self.run_and_check('diskpart')
            for disk in disk_numbers:
                self.run_and_check('select disk=%s' % disk)
                self.run_and_check('online disk')
                self.run_and_check('ATTRIBUTES DISK CLEAR READONLY')

                if disk_type is not None:
                    self.run_and_check('convert %s' % disk_type)
                self.run_and_check('convert dynamic')

            self.run_and_check("select disk=%s" % disk_numbers[0])

            if size is not None:
                cmd = 'create volume simple SIZE=%s ' % size
            else:
                cmd = 'create volume simple'
            output = self.run(cmd)

            if output.find("DiskPart successfully created the volume.") < 1:
                message = "Creation of mirror volume failed"
                self.logger.error(message)
                self.logger(output)
                return False

            self.run_and_check('extend disk=%s' % disk_numbers[1])
            self.run_and_check('assign Letter=%s' % self.volume_name)

        except Exception, e:
            self.logger.error(str(e))
            return False
        finally:
            self.prompt = t
            self.run_and_check('exit')
        return True

    def resize_volume(self, volume, size, wait=True):
        size = int(size)
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select volume=%s' % volume)

        if size < 0:
            self.run_and_check('shrink DESIRED=%s %s' % (size, ('NOWAIT', '')[wait]))
        else:
            self.run_and_check('extend size=%s %s' % size)

        self.prompt = t
        self.run_and_check('exit')

    @property
    def free_letters(self):
        """
        Return drive letter not current used.
        """
        available = set(ascii_letters.upper())
        for v in self.volumes.values():
            if v['letter']:
                available.discard(v['letter'])
        return list(available)

    def get_driveLetter(self):
        logger.info("deprecated")
        return self.free_letters

    def mkfs(self, device, fstype="NTFS", expectation=True):
        return self.format_volume(self, device, fstype=fstype, expectation=expectation)

    def format_volume(self, device, quick=False, fstype="NTFS", expectation=True, timeout=180):
        """
        Format a volume
        """
        t = self.prompt
        self.prompt = ">"
        self.run('diskpart')
        status = self.run('select volume=%s' % device)
        time.sleep(2)
        logger.info(status)
        if quick:
            cmd = 'format fs=%s QUICK' % fstype
        else:
            cmd = 'format fs=%s' % fstype
        status = self.run(cmd, timeout=timeout)  # TODO: convert to run_and_check
        logger.info(status)
        self.prompt = t
        self.run('exit')
        if status.find("successfully") > -1:
            message = "Formatting completed successfully"
            logger.info(message)
            return True
        else:
            message = "Formating failed"
            logger.error(message)
            return False

    def delete_volume(self, volume_number):
        """
        This function deletes the volume
        """

        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select volume=%s' % volume_number)
        self.run_and_check('delete volume')
        self.run_and_check('convert basic')
        self.run_and_check('offline disk')
        self.prompt = t
        self.run_and_check('exit')

        return True

    def aoeflush(self, aflag=True):
        """
        Call the software linux driver's or the HBA's flush command and returns a ReturnCode object.
        """
        cmd = '%s 11 discover' % ethdrvctl
        return self.run_and_check(cmd)

    def aoediscover(self):
        """
        Call the driver's discover command.  Returns ReturnCode object
        """
        cmd = "%s discover" % ethdrvadm
        output = self.run(cmd)
        if output.find("error") > -1:  # I don't think this will ever happen
            status = False
        else:
            status = True
        return ReturnCode(status=status, message=output)

    def discover(self):
        return self.aoediscover()

    @property
    def aoestat(self):
        aoedd = defaultdict(lambda: {'file': None, 'device': None, 'path': None,
                                     'port': None, 'ifs': None, 'target': None, 'size': None,
                                     'iounit': None, 'state': None, 'claim': None, 'paths': None,
                                     'targpath': defaultdict(lambda: {'address': None, 'port': None})})
        cmd = "%s list" % ethdrvadm
        output = self.run_and_check(cmd)
        output = output.message.split('\r\r\n')
        output.pop(0)  # header
        for line in output:
            ls = line.split()  # ['-', 'target', 'size', 'ports', 'claim']
            if len(ls) > 3:
                if ls[3] == 'N/A':
                    ports = list()
                else:
                    ports = ls[3].split(',')
            try:
                if ls[0] == '-':
                    target = ls[1]
                    size = ls[2]
                    for key in aoedd[target]:  # creates default dict
                        if key == 'file':
                            aoedd[target][key] = target
                        elif key == 'port':
                            aoedd[target][key] = ports
                        elif key == 'size':
                            aoedd[target][key] = size
                        elif key == 'state':
                            aoedd[target][key] = list()
                            for _ in ports:
                                aoedd[target][key].append('up')
                        elif key == 'target':
                            aoedd[target][key] = target
                        elif key == 'claim':
                            listlen = len(ls)
                            if listlen > 5:
                                aoedd[target]['claim'] = ls[listlen - 1].split('=')[1]
            except IndexError:
                if aoedd:
                    aoedd = Namespace(aoedd)
                    return aoedd
                else:
                    raise InitiatorError("%s returned unparseable output:\n%s" % (cmd, ls))
        aoedd = Namespace(aoedd)
        return aoedd

    def uninstall_program(self, program_name=None):
        """
        This function will uninstall the product from a windows hosts usind WMI tools.
        Return : True (Successfully installed)
                 False(Failure)
        """
        try:
            if (program_name is None) or (program_name == ""):
                message = "Please provide Program Name to uninstall"
                self.logger.info(message)
            else:
                program_list = self.programs
                if not program_list:
                    message = "No is Progarm is installed on host: %s" % self.host
                    self.logger.info(message)
                if program_name not in program_list:
                    message = "Program name: %s no installed in the host: %s" % (program_name, self.host)
                    self.logger.info(message)
                    message = "Please pass a valid program name to uninstall"
                    self.logger.info(message)
                else:
                    cmd = '%s PRODUCT WHERE NAME="%s" call uninstall /nointeractive' % (
                        server_constants.WMIC, program_name)
                    output = self.run(cmd)
                    if output.find("Win32_Product.IdentifyingNumber") > -1:
                        message = "Program %s Successfully Uninstalled" % program_name
                        self.logger.info(message)
                    else:
                        message = "Program %s Failed to get uninstalled" % program_name
                        self.logger.error(message)
                        return False
        except Exception, e:
            self.logger.error(str(e))
            return False
        return True

    def installed_programList(self):
        logger.info("deprecated")
        return self.programs

    @property
    def programs(self):
        """
        This function will retrive the list of Programs installed on the Windows machine
        """
        query = "PRODUCT GET NAME"
        ret = self.wmic_query(query)
        plist = list()
        for x in ret:
            prog = x.get('Name')
            if prog:
                plist.append(prog)
        return plist

    def copy_file(self, host, user, passwd, src, dest):
        self.logger.info("depricated")
        return self.copy_to_remote(src, user, host, passwd, dest)

    def copy_to_remote(self, src, user, host, passwd, dest):
        """
        SCP a file from a remote host.
        """
        try:
            cmd = "scp %s %s@%s:%s" % (src, user, host, dest)
            child = otto.lib.pexpect.spawn(cmd + '\r')
            self.logger.info(cmd)
            time.sleep(5)
            # child.send('\r')
            pattern1 = '%s@%s\'s password:' % (user, host)
            pattern2 = "Are you sure you want to continue connecting (yes/no)?"
            k = child.expect(['Dummy', pattern1, pattern2])
            if k == 1:
                child.send(passwd)
                child.send('\r')
                time.sleep(5)
            elif k == 2:
                child.send('yes')
                child.send('\r')
                time.sleep(2)
                child.send(passwd)
                child.send('\r')
                time.sleep(5)

        except Exception, e:
            self.logger.error(str(e))
            return False

    def copy_file_from_remote(self, **args):
        self.logger.info("depricated")
        return self.copy_from_remote(**args)

    def copy_from_remote(self, src_host, src_user, src_passwd, src_file_loc, dest_file_loc):
        """
        This function will copy the file from the remote machine to the local machine using scp
        Arguments: src_host - Source host IP Address
                   src_user - Source User name
                   src_passwd - Source Host Password
                   src_file_loc - Source File location
                   dest_file_loc - Destination File Location
        """
        try:
            cmd = "scp %s@%s:%s %s" % (src_user, src_host, src_file_loc, dest_file_loc)
            child = otto.lib.pexpect.spawn(cmd + '\r')
            self.logger.info(cmd)
            time.sleep(5)
            # child.send('\r')
            pattern1 = '%s@%s\'s password:' % (src_user, src_host)
            pattern2 = "Are you sure you want to continue connecting (yes/no)?"
            k = child.expect(['Dummy', pattern1, pattern2])
            if k == 1:
                child.send(src_passwd)
                child.send('\r')
                time.sleep(5)
            elif k == 2:
                child.send('yes')
                child.send('\r')
                time.sleep(2)
                child.send(src_passwd)
                child.send('\r')
                time.sleep(5)
        except Exception, e:
            self.logger.error(str(e))
            return False

    def restart_system(self):
        self.logger.info("depricated")
        return self.reboot()

    def reboot(self):
        """
        This function will restart self.host.
        """
        # shut down command with restart option

        isShutdown = False
        cmd = "%s /r /t 0 /f" % server_constants.SHUTDOWN
        message = "Restarting machine: %s ..." % self.host
        self.logger.info(message)
        self.run_and_check(cmd)
        for eachturn in range(15):
            try:
                self.connect(self.timeout, None)
            except otto.lib.pexpect.TIMEOUT:
                isShutdown = True
                break
        if not isShutdown:
            message = "Machine: %s failed to restart" % self.host
            self.logger.error(message)
            return False
        else:
            for eachturn in range(300):
                try:
                    if self.connect(self.timeout, None):
                        message = "Machine: %s is up again after the desirable restart" % self.host
                        self.logger.info(message)
                        return True
                except otto.lib.pexpect.TIMEOUT:
                    pass
            message = "Machine: %s is taking too long to boot. Please start the machine manually" % self.host
            self.logger.error(message)
        return False

    def homedrive_windows(self):
        self.logger.info("depricated")
        return self.homedrive

    @property
    def homedrive(self):
        """
        This return the Home/System Drive of the windows machine
        """
        cmd = 'set|findstr HOMEDRIVE'
        output = self.run(cmd)
        output = output.split('=')
        output = output[1].split('\r\r\n')[0]
        return output

    def fn_iozone(self, volume):
        logger.info("deprecated")
        return self.iozone(volume)

    def iozone(self, volume):
        """
        perform iozone test on the given volume,vol_name(eg:c:,a:etc)
        """
        t = self.timeout
        t_prompt = self.prompt
        self.prompt = '@~@'  # self.run not catching standard prompt
        self.run('set PROMPT=%s' % self.prompt)
        self.timeout = 300
        cmd = '%s -O -W -+d -t 1 -i 0 -i 1 -r 512b -s 10m -F %s:\\iozone_test.txt' % (
            server_constants.IOZONE_PATH, volume)
        output = self.run(cmd, timeout=120)
        self.logger.info(output)

        self.timeout = t
        self.prompt = t_prompt
        self.run('set PROMPT=%s' % self.prompt)
        if output.find("iozone test complete") < 0:
            return False
        else:
            return True

    def convert_disk(self, disk, dtype):
        return {'gpt': self.convert_disk_gpt(disk),
                'dynamic': self.convert_disk_dynamic(disk),
                'basic': self.convert_disk_basic(disk),
                }[dtype]

    def convert_disk_basic(self, disk_number):
        """
        This fucntion will convert the disk to basic
        """
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select disk=%s' % disk_number)
        self.run_and_check('convert basic')
        self.prompt = t
        self.run_and_check('exit')

    def convert_disk_gpt(self, disk_number):
        """
        This function will convert the disk to GPT type.
        """
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select disk=%s' % disk_number)
        self.run_and_check('convert gpt')
        self.prompt = t
        self.run_and_check('exit')

    def convert_disk_dynamic(self, disk_number):
        """
        This function will convert the disk to Dynamic type
        """
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select disk=%s' % disk_number)
        self.run_and_check('convert dynamic')
        self.prompt = t
        self.run_and_check('exit')

    def offline(self, object_type, object_number):
        """
        offline object_type: : object_type = volume,disk
                             : object_number = number of object_type eg:0,1,2..
        """
        t = self.prompt
        self.prompt = ">"

        self.run_and_check('diskpart')
        self.run_and_check('select %s=%s' % (object_type, object_number))
        self.run_and_check('offline %s' % object_type)
        self.prompt = t
        self.run_and_check('exit')

    def disable_port(self, port):
        logger.info("Disabling Port " + port)
        output = self.run_and_check('{0} disable @\"{1}"'.format(devcon, port))
        logger.info(output.message)
        time.sleep(5)

    def enable_port(self, port):

        logger.info("Enabling Port " + port)
        t = self.timeout
        self.timeout = 300
        output = self.run_and_check('{0} enable @\"{1}"'.format(devcon, port))
        self.timeout = t
        logger.info(output.message)
        time.sleep(10)

    def verify_list_port(self):
        cmd = '%s list-ports' % ethdrvadm
        result = self.run_and_check(cmd)
        logger.info(result)
        port_list = re.findall('\s+(EHBA.*?)\s+', str(result))
        num = len(port_list)
        logger.info("Port list" + str(port_list))
        hba_name = "EHBA"
        if any(hba_name in i for i in port_list):
            logger.info("EtherDrive HBAs found:%d ports found", num)
            return True
        else:
            logger.info("No EtherDrive HBAs found!")
            return False

    def verify_port_type(self):
        cmd = '%s list-ports' % ethdrvadm
        result = self.run_and_check(cmd)
        connector_list = re.findall('\-(RJ45)\s+', str(result))
        num = len(connector_list)
        connector_list = set(connector_list)
        logger.info("Connector list" + str(connector_list))
        connector_name = ['RJ45', 'CX4', 'SFP+']
        found_connectors = []
        for i in connector_list:
            for j in connector_name:
                if i == j:
                    found_connectors.append(i)

        if len(found_connectors) >= 1:
            speed1g = '1000'
            speed10g = '10000'
            logger.info("It is an %s type connector and %d such connectors found", str(found_connectors), num)
            result = self.run_and_check(cmd)
            port_list = re.findall('(\d+)\s+(EHBA.*?)\s+(\w+)\s+(\d+)/\d+', str(result))
            for i in range(len(port_list)):
                if speed1g in port_list[i]:
                    logger.info("Ports have 1G Connection")
                elif speed10g in port_list[i]:
                    logger.info("Ports have 10G Connection")
        else:
            logger.info("No EtherDrive HBAs found!")
            return False
        return True

    @property
    def hba_ports(self):
        """
        Returns a dictionary of the HBA's ports file contents.
        """
        pnum = 0
        s = False
        ports = dict()
        r = self.run('{0} status =SCSIAdapter'.format(devcon))
        if not r:
            return ports
        lines = r.split('\n')
        for l in lines:
            l = l.strip('\r\r')
            if l.find('VEN_8086&DEV_0001') > 0:
                ports[pnum] = dict()
                ports[pnum]['pci'] = l
                ports[pnum]['port'] = l[-1]
                s = True
            elif l.find('Coraid') > 0:
                ports[pnum]['type'] = l.split()[-1]
            elif s:
                s = False
                if l.find('running') > 0:
                    ports[pnum]['state'] = 'enabled'
                elif l.find('disabled') > 0:
                    ports[pnum]['state'] = 'disabled'
                pnum = pnum + 1
        r = self.run('{0} list-ports'.format(ethdrvadm))
        lines = r.split('\n')
        for l in lines:
            l = l.strip('\r\r')
            j = l.split()
            try:
                if int(j[0]) in ports:
                    ports[int(j[0])]['mac'] = j[2]
                    ports[int(j[0])]['link'] = dict()
                    speed = j[-1].split('/')
                    ports[int(j[0])]['link']['speed'] = speed[0]
                    ports[int(j[0])]['link']['max'] = speed[1]
            except:
                continue
        return ports


if __name__ == "__main__":
    from otto.settings import *
    from pprint import pprint as pp

    user, host, password = sys.argv[1:4]
    print user, host, password
    w = Windows(user, host, password, "-bash-3.2\$")
    w.connect(timeout=30)
    print "connected"
    # pp(w.programs)
    # pp(w.bios)
    # pp(w.cpu)
    print w.cpu['CPU0']['Name']
    pp(w.aoestat())
    # print "disks: %s" % w.disks
    # print "volumes: %s" % w.volumes
    # print "freeletters %s" % w.free_letters
    # print "programs installed %s" % w.programs
