#!/usr/bin/env python
# encoding: utf-8
# Created by Vaibhawi Pasalkar on 2012-06-05.
"""
initiators
----------

These are classes for interacting with ESXi hosts.
Logging has to be configured from the script that instantiates
the class.  Currently mostly only methods for provisioning are
available.

Basic Usage::

        from otto.appliances import esx

        s = esx(uname, host, passwd)
        s.connect()
        logger.info(s.release)
        s.disconnect()

"""

import os
import re
import logging

from otto.connections.ssh_pexpect import Ssh
from otto.lib.otypes import ReturnCode, ApplianceError, ApplianceUsage
from otto.utils import mkcmdstr

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.initiators')
logger.addHandler(logging.NullHandler())


class Esx(Ssh):
    """
    A class for interacting with the esx using ssh.

    extended parameters::

        expectation     (Boolean) if False the library will not raise exceptions for error: or usage:
        force           (Boolean) if True the method walks through the acceptance dialog

    """

    def __init__(self, user, host, password, prompt=None):
        self.user = user
        self.host = host
        self.password = password
        self.prompt = prompt
        if prompt is None:
            self.prompt = '~ #'
        self.os = 'esx'
        self.nsdir = '/proc/ethdrv'

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

        if result.message.startswith('Error:'):
            logger.error(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = ApplianceError(failmsg)

        elif result.message.startswith('Usage:'):
            logger.critical(result.message)
            result.status = False
            failmsg = cmd + " failed: " + result.message
            e = ApplianceUsage(failmsg)
            result.status = False

        if not expectation:
            return result
        elif not result.status:
            raise e
            # logger.info( result)
        return result

    @property
    def release(self):
        """
        The release command returns a string containing
        the currently running ESX release.
        """
        result = self.run_and_check('vmware -v')
        rel = result.message
        if rel.startswith('RELEASE'):
            rel = rel.split('\r\n')[1].strip()
        return rel

    @property
    def aoedevices(self):
        """
        Get the list of the AOE devices
        """
        ret = self.run_and_check('esxcli ethdrv devices list')
        return ret

    @property
    def get_aoedevices(self):
        return self.aoedevices

    def claim_targets(self, target_list):
        """
        Claim the luns
        """
        lun_list = target_list.split(' ')
        result = ReturnCode(False, message="empty target list")
        for lun in lun_list:
            cmd = mkcmdstr('esxcli ethdrv claim -t', lun)
            logger.info(lun)
            result = self.run_and_check(cmd)
        return result

    def hba_driver_install(self, path):
        """
          Install the specified HBA driver
        """
        cmd = mkcmdstr('esxcli software vib install -d', path)
        # logger.info( cmd )
        result = self.run_and_check(cmd)
        if result.message.find('Reboot Required: true') != -1:
            logger.info("Driver is installed. The system needs to be rebooted")
        else:
            logger.info("Driver is installed. System need not be rebooted")
        return result

    def get_vm_list(self):
        """
        Get the list of the VMs on the ESX
        """
        cmd = mkcmdstr('vim-cmd vmsvc/getallvms')
        result = self.run_and_check(cmd)
        lines = result.message.split('\n')
        vmids = []
        for l in lines:
            vmid = l.split(' ')
            if vmid[0] != 'Vmid':
                vmids.append(vmid[0])
            return vmids

    def power_on_vm(self, vm_list):
        """
            Power on the VM(s)
        """
        result = ReturnCode(False, message="empty vm_list")
        for vm in vm_list:
            cmd = mkcmdstr('vim-cmd vmsvc/power.getstate', vm)
            result = self.run_and_check(cmd)
            if result.message.find('Powered off') != -1:
                cmd = mkcmdstr('vim-cmd vmsvc/power.on', vm)
                result = self.run_and_check(cmd)
        logger.info("All vms are powered on")

        return result

    def power_down_vm(self, vm_list):
        """
            Power off the VM(s)
        """
        result = ReturnCode(False, message="empty vm_list")

        for vm in vm_list:
            cmd = mkcmdstr('vim-cmd vmsvc/power.getstate', vm)
            result = self.run_and_check(cmd)
            if result.message.find('Powered on') != -1:
                cmd = mkcmdstr('vim-cmd vmsvc/power.off', vm)
                result = self.run_and_check(cmd)
        logger.info("All vms are powered down")

        return result

    def shut_down_vm(self, vm_list):
        """
            Shut down/power off the VM(s)
        """
        errmsg = 'Cannot complete operation because VMware Tools is not running in this virtual machine'
        result = ReturnCode(False, message="empty vm_list")

        for vm in vm_list:
            cmd = mkcmdstr('vim-cmd vmsvc/power.getstate', vm)
            result = self.run_and_check(cmd)
            if result.message.find('Powered on') != -1:
                cmd = mkcmdstr('vim-cmd vmsvc/power.shutdown', vm)
                result = self.run_and_check(cmd)
                if result.message.find(errmsg) != -1:
                    cmd = mkcmdstr('vim-cmd vmsvc/power.off', vm)
                    result = self.run_and_check(cmd)

                else:
                    logger.info("VM is already powered off")
        return result

    def check_vm_status(self, vm_list):
        """
            Checks if the VM(s) status is green/normal
        """
        result = ReturnCode(False, message="empty vm_list")

        for vm in vm_list:
            cmd = mkcmdstr('vim-cmd vmsvc/get.summary', vm)
            result = self.run_and_check(cmd)
            if result.message.find('overallStatus = \"green\"') != -1:
                logger.info("VM is in normal state")
            else:
                logger.info("VM is not in normal state")
        return result

    def reboot(self):
        """
            Reboots the ESX
        """
        self.run_and_check('reboot')

    def check_hba_version(self, release):
        """
            Checks if correct HBA version is installed
        """
        result = self.run_and_check('cat /proc/ethdrv/release')
        if release.find(result.message) != -1:
            logger.info("Correct HBA driver version is installed")
            return 1
        else:
            logger.info("The driver version is not the same as installed")
            return 0

    def rescan_hba(self):
        """
            Rescans the AOE HBA
        """
        cmd = mkcmdstr('esxcfg-scsidevs -a | grep -i coraid')
        result = self.run_and_check(cmd)
        hba_details = result.message.split(' ')
        hba_name = hba_details[0]
        logger.info(hba_name)
        cmd = mkcmdstr('esxcfg-rescan', hba_name)
        result = self.run_and_check(cmd, expectation=False)
        return result
