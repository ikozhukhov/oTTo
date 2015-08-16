#!/usr/bin/env python
# encoding: utf-8

import os
import re
import logging
from time import sleep
from exceptions import KeyError

from otto.lib.pexpect import spawn, EOF, TIMEOUT, ExceptionPexpect
from otto.lib.otypes import ReturnCode, ConnectionError

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.connections')
logger.addHandler(logging.NullHandler())


class Cec(spawn, object):
    """
    Connect via cec.  This spawns a process running the
    installed cec client to interact with an appliance.
    """

    def __init__(self, shelf, iface, password=None, prompt=None):
        self.version = None
        self.password = password
        self.prompt = prompt
        self.shelf = shelf
        self.iface = iface
        self.cpl = None
        self.amsg = None
        self.closed = True
        self.amsgs = [
            "Warning: (ps[0-9]+) missing",
            "Warning: can not sync with ntp server ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
            "Warning: model ([0-9A-Za-z]+\-[0-9A-Za-z]+) missing [0-9]+ fan",
            "building parity complete: ([0-9]+\.[0-9]+)",
            "building parity aborted: ([0-9]+\.[0-9]+)",
            "beginning recovery of disk ([0-9]+\.[0-9]+\.[0-9]+)",
            "beginning recovery of (disk [0-9]+\.[0-9]+ [\(]?device [0-9]+\.[0-9]+\.[0-9]+[\)]?)",
            "recovery complete: ([0-9]+\.[0-9]+\.[0-9]+)",
            "recovery complete: ((disk|drive) [0-9]+\.[0-9]+ [\(]?device [0-9]+\.[0-9]+\.[0-9]+[\)]?)\n?",
            "aborted recovery of disk ([0-9]+\.[0-9]+\.[0-9]+)",
            "aborted recovery of disk ([0-9]+\.[0-9]+\.[0-9]+[ \t]*[\(]?device [0-9]+\.[0-9]+\.[0-9]+\.*[\)]?)",
            "recover failed",
            "unrecoverable failure on raid ([0-9]+\.[0-9]+)",
            "no spare large enough for ([0-9]+\.[0-9]+\.[0-9]+)",
            "no spare large enough for (disk 0-9]+\.[0-9]+ [\(]?device 0-9]+\.[0-9]+\.[0-9]+[\)]?)",
            "no spare large enough for disk \d+\.\d+ (device \d\.\d\.\d)",
            "recovery suspended: (disk [0-9]+\.[0-9]+ [\(]?device [0-9]+\.[0-9]+\.[0-9]+[\)]?)",
            "growing raid to accomodate additional space provided by replacing"
            " (disk [0-9]+\.[0-9]+ device [0-9]+\.[0-9]+\.[0-9]+)",
            "[0-9]{,2}\:[0-9]{,2}\s\[rdodin[0-9]\.[0-9]\].*",
        ]

    def connect(self, timeout=10, expectation=True):
        """
        Connect to and authenticate with host.
        """
        cmd = "cec"
        args = list()
        args.append("-s%s" % self.shelf)
        args.append(self.iface)
        logger.debug("%s %s" % (cmd, str(args)))
        connectstr = re.compile('Escape is.*')
        try:
            if hasattr(self, 'closed'):
                self.close()  # this may break if this is interrupted
                spawn.__init__(self, cmd, args=args, timeout=timeout)
            else:
                logger.debug("object had no attribute closed ... hmm")
                spawn.__init__(self, cmd, args=args, timeout=timeout)
            # tricky because cec doesn't return a prompt
            # it just connects
            try:
                self.expect(connectstr)

            except EOF:
                emesg = self.before.strip().splitlines()[0]

                if "can't netopen" in self.before:
                    if expectation:
                        raise ConnectionError("%s:\n try something like 'sudo chmod u+s /usr/sbin/cec'" % emesg)
                    return False
                elif "none found" in self.before:
                    if expectation:
                        raise ConnectionError("%s\n could not reach shelf address %s" % (emesg, self.shelf))
                    return False
            self.sendline()
            self.sendline()
            # must now account for possible login prompt
            i = self.expect(["Password", self.prompt], timeout=3)
            if i == 0:
                if self.password is None:
                    self.password = "admin"
                self.sendline(self.password)
                self.expect(self.prompt)
            elif i == 1:
                pass
        except KeyError as e:
            logger.critical("CEC couldn't complete connection")
            if e.message:
                logger.error(e.message)
            if e.args:
                logger.debug(e.args)
            if expectation:
                raise ConnectionError(str(e))
            return False
        except ExceptionPexpect as e:
            if "The command was not found or was not executable" in e:
                raise ConnectionError("%s:\n is cec installed at /usr/sbin/cec?" % e)
            else:
                raise e
        return True

    def disconnect(self):
        """
        Disconnect from host.  This is mostly a formality.
        """
        cmd = chr(28)  # ctl-\ or ASCII File separator
        origp = self.prompt
        self.prompt = '>>> '
        self.sendline(cmd)
        index = self.expect([EOF, self.prompt])
        if index == 1:
            self.sendline("q")
            self.expect(EOF)
        self.close()
        self.prompt = origp
        return True

    def run(self, cmd, wait=True, force=False, ans='y', timeout=60):
        """
        This is the main command/only real operation.
        It runs a command and returns the result.
        """
        logger.debug("%s\n\twait %d force %d ans %s timeout %d" % (cmd, wait, force, ans, timeout))
        if self.closed:
            raise ConnectionError("Not connected to shelf %s" % self.shelf)
        self.sendline(cmd)

        if not wait:
            return self.before.strip()  # async messages could appear in here
        try:
            self.expect_exact(cmd, timeout)
        except TIMEOUT:
            r = self.__checkasync(self.before, cmd)
            if not r:
                raise ConnectionError("looking for: %s in %s" % (cmd, self.before))
        # We only compile this regex once per instance
        if not self.cpl:
            self.cpl = self.compile_pattern_list([
                r"\[n\]",
                r"\[N\]",
                r"Continue\? \(y/n\) (.*)",
                r"(.*)" + self.prompt,
                r"Would you like to update the LUN format, or quit\? y/n/q\? \[q\]",
                r"'y' to update to new format, 'n' to create LUN with old format, "
                "or 'q' to quit\[Q\]:",
                r"'n' to cancel, 'a' for all, or 'y' to .*:",
                r"IPv4 destination address .*:",
                r"IPv4 source address .*:",
                r"Local syslog interface .*:",
            ])

        response = None
        if force:
            while 1:
                i = self.expect_list(self.cpl, timeout)
                if i == 0 or i == 1:
                    if force:
                        self.sendline(ans)
                if i == 2:
                    if force:
                        self.sendline(ans)
                    response = ""
                    break
                elif i == 3:
                    response = self.match.group(1).strip()
                    break
                elif i == 4 or i == 5:
                    self.sendline(ans)
                    response = ""
                # Adding the following to handle syslog -c in srx 6.x to input destination_ip
                elif i == 7:
                    self.sendline(ans)
                    response = ""
                    break
                # Adding the following to handle syslog -c in srx 6.x to input source_ip
                elif i == 8:
                    self.sendline(ans)
                    response = ""
                    break
                # Adding the following to handle syslog -c in srx 6.x to input interface
                elif i == 9:
                    self.sendline(ans)
                    self.expect(self.prompt, timeout)
                    response = self.before
                    break
        else:
            self.expect(self.prompt, timeout)
            response = self.before

        ret = response
        for msg in self.amsgs:
            match = re.search(r"(%s)(\r\n)*" % msg, response)
            if not match:
                continue
            logger.debug("CHECKASYNC: FOUND MATCH: '%s'" % msg)
            start = response.find(match.group(1))
            end = len(match.group(1))
            if match.lastindex == 3:
                # include the matched newline
                end += len(match.group(3))

            # what surrounds the match (hopefully the expected cmd)
            ret = response[:start] + response[start + end:]

            # the matched async message
            # aysncmsg = response[start:start + end]
            break
        ret = ret.strip().replace('\r\r\n', '\r\n')
        return ret

    def reconnect(self, after=10, timeout=None):
        self.disconnect()
        sleep(after - 1)
        x = 0

        # default to this instance's current value
        if timeout is None:
            timeout = self.timeout

        while 1:
            x += 1
            try:
                try:
                    if not self.closed:
                        break
                    if self.connect(timeout=timeout, expectation=False):
                        break
                except TIMEOUT as e:
                    self.close()
                    logger.debug(str(e))
            except EOF:
                self.close()
                # sleep(2)
        return True

    def __checkasync(self, buf, cmd):
        """
        __checkasync checks pexpect buffers for async CEC
        messages which often cause timeouts.  If found, 
        the function returns a ReturnCode which is True and 
        consists of the async message.  If an expected async 
        message is not found, the ReturnCode is False and its 
        message is the pexpect buffer.
        """
        logger.debug("CHECKASYNC: '%s'\nbuf:\n'%s'" % (cmd, buf))
        ret = ""
        msg = buf

        for msg in self.amsgs:
            match = re.search(r"(%s)(\r\n)*" % msg, buf)
            if not match:
                continue
            logger.debug("CHECKASYNC: FOUND MATCH: '%s'" % msg)
            start = buf.find(match.group(1))
            end = len(match.group(1))
            if match.lastindex == 3:
                # include the matched newline
                end += len(match.group(3))

            # what surrounds the match (hopefully the expected cmd)
            ret = buf[:start] + buf[start + end:]

            # the matched async message
            msg = buf[start:start + end]
            break

        if not ret:
            # prevent infinite recursion
            return ReturnCode(False)

        if ret.find(cmd) != -1:
            logger.debug("CHECKASYNC: successfully matched and removed '%s'" % msg)
            return ReturnCode(True, msg)

        # we have had instances where two async msgs were output while pexpect
        # was waiting for the echo of a cmd ... recurse to handle any multiples
        r = self.__checkasync(ret, cmd)
        if r:
            return r
        e = "CHECKASYNC: '%s' timed-out, but no asynchronous output found in:\n" \
            "'%s'\nret: '%s'" % (cmd, buf, ret)
        logger.error(e)
        return ReturnCode(False, e)
