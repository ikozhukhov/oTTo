# -*- coding: utf-8 -*-

"""
    utils
    -----

    Utility functions and classes for QA scripts

"""
from __future__ import print_function
import os
import logging
import time
import shutil
import filecmp
import argparse
import subprocess
import ConfigParser

from collections import OrderedDict

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.utils')


def unique(seq):
    """
    a simple fast uniq using dicts
    """
    keys = OrderedDict()
    for e in seq:
        keys[e] = 1
    return keys.keys()


def mkcmdstr(*args):  # TODO convert to string formatter
    return ' '.join([str(arg) for arg in args])


def random_string(length):
    """
    Generates a random string of a given length
    consisting of only the set of::

        abcdefghijklmnopqrstuvwxyz
        ABCDEFGHIJKLMNOPQRSTUVWXYZ
        0123456789

    """
    from random import sample
    from string import ascii_letters, digits

    chars = ascii_letters + digits
    while len(chars) < length:
        chars += ascii_letters + digits
    r = ''.join(sample(chars, length))
    return r


def write_bytes(filename, num, pattern=None, offset=None):
    """
    Write a given number of bytes to filename.
    """
    f = open(filename, buffering=0, mode='w+b')
    if offset:
        f.seek(offset)
    if not pattern:
        pattern = 0x00
    for x in range(num):
        f.write(chr(pattern))


def read_bytes(filename, size=8192):
    # TODO: add offset and count
    """
    Read a given number of bytes from filename.
    """
    with open(filename, "rb") as f:
        while True:
            chunk = f.read(size)
            if chunk:
                for b in chunk:
                    yield b
            else:
                break


def aoetostr(addr):
    """
    Convert var of type aoeaddress or dict to a string.
    """

    if type(addr) == dict:
        addr = str(addr['shelf']) + "." + str(addr['slot'])
    return addr


def strtoaoe(addr):
    """
    Convert a variable of string to AoE
    """
    if type(addr) == str:
        shelf, slot = addr.split('.')
        addr = {'shelf': shelf, 'slot': slot}
    return addr


def compare(a, b, expectation=True):
    """
    compare two arbitrary items logging results
    """
    # TODO: is this useful?
    logger.info("comparing %s, %s, expectation: %s" % (a, b, expectation))
    result = (a == b)
    logger.info("result is %s" % result)
    if result is not expectation:
        logger.info("%s is not equal to %s" % (result, expectation))
        raise ValueError('compare failed')


def md5sum(fname):
    """
    Calculate md5 checksum of a file.
    """
    import hashlib

    mdsum = hashlib.md5()
    mdsum.update(open(fname, "rb").read())
    checksum = mdsum.hexdigest()
    logger.info("checksum of %s: %s" % (fname, checksum))
    return checksum


def now():
    """
    Return current epoch time
    """
    return time.time()


def since(start):
    """
    Return the number of seconds since input time
    """
    return now() - start


def timefmt(secs):
    """
    Nicely format number of secs given secs or µsecs for output.
    """
    from datetime import timedelta

    if secs < 1:
        secs *= 10 ** 6
        secs = timedelta(microseconds=secs)
    else:
        secs = timedelta(seconds=secs)
    return str(secs)


def timestamp():
    from datetime import datetime

    t = datetime.now().today()
    return "%02d%02d%02d-%02d%02d:%02d" % (
        int(t.year) - 2000, int(t.month), int(t.day), int(t.hour), int(t.minute), int(t.second))


def write_data(fname, offset, length, char):
    """
    Write data to a file.
    """
    logger.info("write_data %s offset:%s len:%s char:%s" % (fname, offset, length, char))
    block_size = 4096
    block_len = int(length / block_size)
    block_pattern = char * block_size
    leftover_len = length % block_size
    leftover_pattern = char * leftover_len
    if not os.path.isfile(fname):
        f = open(fname, "a")
        f.close()
    f = open(fname, "r+")
    f.seek(offset)
    i = 0
    try:
        while i < block_len:
            f.write(str(block_pattern))
            i += 1
        f.write(str(leftover_pattern))
    except IOError:
        raise
    f.close()


def copy_file(src, dest, background=False):
    """
    Copy the source file to the destination.
    """
    logger.info("copy file: %s %s" % (src, dest))
    shutil.copy(src, dest)


def remove_file(f):
    """
    Remove a file from the system.
    """
    logger.info("remove_file: %s" % f)
    os.remove(f)


def compare_files(file1, file2, expectation=True):
    logger.info("comparing files %s, %s, expectation: %s" % (file1, file2, expectation))
    result = filecmp.cmp(file1, file2, shallow=False)
    logger.info("result is %s" % result)
    if result != expectation:
        logger.info("not equal")
        raise ValueError('compare_files failed')


def get_size(fname):
    """
    Return the size in bytes of the file
    """
    file_size = os.path.getsize(fname)
    logger.info("%s: %s bytes" % (fname, file_size))
    return file_size


def fill_volume(fname, offset=None, char=None):
    """
    Write a repeating character at to a file. Defaults to '0' and no offset.
    """
    if not char:
        char = 0x00
    if not offset:
        offset = 0
    logger.info("fill_volume %s offset:%s char:%s" % (fname, char, offset))
    block_size = 4096
    block_pattern = char * block_size

    if os.path.isfile(fname):
        f = open(fname, "a")
        f.close()
    f = open(fname, "r+")
    f.seek(offset)
    i = 0
    try:
        while True:
            f.write(str(block_pattern))
            i += 1
    except IOError:
        pass
    f.close()


def parse_args(required_args, optional_args=None):
    """
    Returns a dict of args to a script obtained from either a config file or the command line.
    Any argument on the command line will override its value in the config file.

    arguments:
        required_args: list of arguments that a script requires
        optional_args: list of optional arguments

    example:
        This example is for a script that requires the args: 'srx1_shelf', 'srx1_lun1', and 'vsx1_hostname'
        and has an optional arg: raid_type

        To use this function, place the following 3 lines in your script::

            args = utils.parse
            _args(['srx1_shelf', 'srx1_lun1', 'vsx1_hostname'],['raid_type'])
            for arg in args:
                vars()[arg] = args[arg]

        The last 2 lines above are optional, 
        but make it cleaner to use arguments in your script 
        e.g. you can use vsx1_hostname instead of args['vsx1_hostname']

        then, you can call your script either of the following 2 ways:

            1. python yourscript.py --srx1_shelf 99 --srx1_lun1 99.1 --vsx1_hostname VSX_NAME

        or

            2. python yourscript.py --config your_config.cfg

        in which your config file contains the following::

            [General]
            srx1_shelf = 99
            srx1_lun1 = 99.0
            vsx1_hostname = VSX_NAME

        In your script, arguments can be called by their name.
        e.g. print(vsx1_hostname)

    tip:
    If you want your script to have a default value for some arg (e.g. raid_type ), you can do the following:
    raid_type = args.get('raid_type') or 'raid5'

    Note: please see: https://twiki.coraid.com/cgi-bin/twiki/view/EngDev/OttoTestConfigFile
    for suggested naming conventions for arguments.

    """

    script_args = {}
    args_from_config_file = {}
    pyunit_options = ['verbose', 'quiet', 'failfast', 'catch', 'buffer']
    pyunit_args = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--config")
    # 1.  Create a dictionary (cli_args) of args from the command line
    # 1a. Add required script options to argparse object
    for required_arg in required_args:
        parser.add_argument("--%s" % required_arg)
        # 1b. Add optional options to argparse object
    if optional_args:
        for optional_arg in optional_args:
            parser.add_argument("--%s" % optional_arg)
            # 1c. Add pyunit specific options to argparse object
    for pyunit_option in pyunit_options:
        parser.add_argument("--%s" % pyunit_option, default=False, action='store_true')
        # 1d. Get command line args from argparse object into a dictionary ( cli_args )
    args = parser.parse_args()
    cli_args = vars(args)
    # 2. If a config file is specified, then
    # create a dictionary ( args_from_config_file ) of args from the config file.
    if cli_args['config']:
        logger.debug("config file: " + str(cli_args['config']))
        config_file = cli_args['config']
        cfg = ConfigParser.ConfigParser()
        cfg.read(config_file)
        for required_arg in required_args:
            args_from_config_file[required_arg] = cfg.get('General', required_arg)
        if optional_args:
            for optional_arg in optional_args:
                try:
                    args_from_config_file[optional_arg] = cfg.get('General', optional_arg)
                except:
                    pass  # since this arg is optional, we don't care if it's in config file
                    # 3. Fill script_args dictionary using command line args if available, otherwise using config file values
                    # 3a. Add required args
    for required_arg in required_args:
        if cli_args.get(required_arg):
            script_args[required_arg] = cli_args[required_arg]
        elif args_from_config_file.get(required_arg):
            script_args[required_arg] = args_from_config_file[required_arg]
        else:
            raise AssertionError("missing argument: %s" % required_arg)
            # 3b. Add optional args
    if optional_args:
        for optional_arg in optional_args:
            if cli_args.get(optional_arg):
                script_args[optional_arg] = cli_args[optional_arg]
            elif args_from_config_file.get(optional_arg):
                script_args[optional_arg] = args_from_config_file[optional_arg]
                # 4. Add pyunit specific args to script_args['pyunit_args'] so that pyunit script
                # can use them if needed.
    for pyunit_option in pyunit_options:
        if cli_args[pyunit_option]:
            pyunit_args.append("--%s" % pyunit_option)
    logger.debug("This script was called with the following arguments")
    for arg in script_args:
        logger.debug(arg + " = " + script_args[arg])
    if len(pyunit_args):
        script_args['pyunit_args'] = pyunit_args
        logger.debug("The following pyunit arguments were specified")
        for arg in pyunit_args:
            logger.debug(arg)
    return script_args


def next_lun(lun):
    """
    This is a utility function to increment lun numbers.
    e.g. given 32.3, it returns 32.4
         given 32.255, it returns 33.0
    """
    [major, minor] = lun.split(".")
    minor = int(minor) + 1
    if minor == 255:
        major = int(major) + 1
        minor = 0
    next_lun = str(major) + "." + str(minor)
    return next_lun


def dd(path, size):
    block_size = 4096
    num_blocks = int(size / block_size)
    remainder = size % block_size
    cmd = "dd if=/dev/urandom count=%s bs=%s count=%s of=%s" % (num_blocks, block_size, num_blocks, path)
    pid = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    pid.wait()
    offset = num_blocks * block_size
    cmd = "dd if=/dev/urandom bs=1 count=%s seek=%s of=%s" % (remainder, offset, path)
    pid2 = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    pid2.wait()


# These functions are for SRX perf testing
def map_controllers(chassis, controllers):
    # populate the elements in controllers with
    # the drives are connected to them
    for slot in chassis.keys():
        controllers[chassis[slot] - 1].append(slot)

    return chassis, controllers


def balance_across(controllers, initiators):
    # balance the initiators
    # disk access across controllers
    # rr-ing the initiators
    ikeys = initiators.keys()
    index = 0
    last = len(ikeys) - 1
    for controller in controllers:
        while len(controller) > 0:
            for drive in controller:
                initiators[ikeys[index]].append(drive)
                controller.pop(controller.index(drive))
                if index == last:
                    index = 0
                else:
                    index += 1
    return initiators


def print_map(initiators):
    for i in initiators.keys():
        print("%s : %s" % (i, initiators[i]))


def print_distribution(initiators, chassis):
    # todo: this should just return the distribution not print it
    for i in initiators.keys():
        k = initiators[i]
        print("%s : " % i, end='')
        print("[", end='')
        for j in k:
            print("%s," % chassis[j])
            print("]")


def calc_distribution(initiators, chassis, controller_list):
    # display balance of initiators across controllers
    controllers = list()
    num_controllers = range(len(controller_list))
    for _ in num_controllers:
        controllers.append([])  # num of initiators attached
    for i in initiators.keys():
        curr_init = initiators[i]
        for targ in curr_init:
            cntlr = chassis[targ]
            controllers[cntlr - 1].append(i)
    r = []
    for controller in controllers:
        r.append(len(unique(controller)))
    return r


def lun_bytes(sze):
    """
    Converts a string like '5T' to a base 10 byte count
    """
    m = sze[-1].lower()
    if m.isdigit():
        return sze
    v = int(sze[:-1])
    if m == 'k':
        return v * 1000
    if m == 'm':
        return v * 1000 * 1000
    if m == 'g':
        return v * 1000 * 1000 * 1000
    if m == 't':
        return v * 1000 * 1000 * 1000 * 1000
    if m == 'p':
        return v * 1000 * 1000 * 1000 * 1000 * 1000
    return None


def overlay_dicts(dict1, dict2):
    """
    Recursively create a dictionary which contains all the values of both dict1 and
    dict2.  If any keys overlap which are not dictionaries dict2 takes precedence. If
    keys overlap and they are dictionaries this function will recurse.

    Note: This function will destroy dict2.
    """
    ret = {}
    for k, v in dict1.iteritems():
        if k in dict2:
            if isinstance(dict2[k], dict):
                ret[k] = overlay_dicts(v, dict2.pop(k))
        else:
            ret[k] = v
    for k, v in dict2.iteritems():
        ret[k] = v
    return ret

