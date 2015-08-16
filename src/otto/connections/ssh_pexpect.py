import os
import logging
from time import sleep

from otto.lib.otypes import ConnectionError, ReturnCode
from otto.lib.pexpect import spawn, EOF, TIMEOUT
from otto.utils import now, since, timefmt

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.connections')
logger.addHandler(logging.NullHandler())


class Ssh(spawn, object):
    """
    Connect via ssh.  This spawns a process running the
    installed ssh client to interact with an appliance.
    """

    def __init__(self, user, host, password, prompt, timeout=10):
        self.user = user
        self.host = host
        self.password = password
        self.prompt = prompt
        self.timeout = timeout
        self.connected = False

    def connect(self, timeout=10, args=None, nolog=False):
        """Connect to and authenticate with host."""

        cmd = "ssh"

        if args is None:
            args = ["-q", "-o PubkeyAuthentication no",
                    "-o UserKnownHostsFile=/dev/null",
                    "-o UserKnownHostsFile2=/dev/null",
                    "-o StrictHostKeyChecking=no"]

        args.append("-l" + self.user)
        args.append(self.host)
        if not nolog:
            logger.debug("%s %s" % (cmd, str(args)))

        try:
            spawn.__init__(self, cmd, args, timeout)

            prompt = self.expect(["(?i)password: ", "(?i)password"])

            if prompt in [0, 1]:
                self.sendline(self.password)

            else:
                self.close()
                return False
            try:
                if self.prompt == ':\>':
                    self.expect_exact(self.prompt)
                else:
                    self.expect(self.prompt)
            except TIMEOUT:
                raise ConnectionError(
                    "Connected but didn't find prompt '%s'\n instead self.before was:\n%s" % (self.prompt, self.before))
            self.connected = True
        except KeyError as e:
            if not nolog:
                logger.critical("Couldn't complete connection")
                if e.message:
                    logger.error(e.message)
            return False
        except (EOF, TIMEOUT) as e:
            if not nolog:
                logger.critical("Couldn't complete connection to %s@%s" % (self.user, self.host))
                if e.message:
                    logger.error(e.message)
            return ReturnCode(False, message=e.message)

        return ReturnCode(True, message=self.before)

    def disconnect(self):
        """
        Disconnect from host.  This is mostly a formality.
        """
        cmd = "exit"

        self.sendline(cmd)
        index = self.expect([EOF, self.prompt])
        if index == 1:
            self.sendline("exit")
            self.expect(EOF)
        self.connected = False
        return True

    def run(self, cmd, wait=True, timeout=10):
        """
        This is the main command only real operation.  It runs a command
        and returns the result.
        """
        logger.debug(cmd)
        if not self.connected:
            raise ConnectionError("not connected")
        # To handle long commands greater than 50 chars long, change winsize
        if len(cmd) >= 50:
            winsize = self.getwinsize()
            self.setwinsize(winsize[0], len(cmd) + 80)
            self.sendline(cmd)
        else:
            self.sendline(cmd)
        if not wait:
            if len(cmd) >= 50:
                self.setwinsize(winsize[0], winsize[1])
            logger.debug("**didn't wait for a response**")
            return self.before.strip()
        self.expect_exact(cmd)  # read until you see the command just entered
        self.expect(self.prompt, timeout)
        response = self.before.strip()  # remove the prompt
        if len(cmd) >= 50:
            self.setwinsize(winsize[0], winsize[1])
        logger.debug(response)
        return response

    def reconnect(self, after=10, timeout=None, nolog=False):
        """
        reconnect to the host::

            after how long to wait for the first attempt
            timeout how long to wait for each attempt

        """
        # default to this instance's current value
        if timeout is None:
            timeout = self.timeout

        self.close()
        start = now()
        while 1:
            sleep(after)
            try:
                if self.connect(timeout=timeout, nolog=nolog):
                    break
            except (TIMEOUT, EOF) as e:
                self.close()
                if not nolog:
                    logger.debug(str(e))
        logger.debug("reconnected after %s" % timefmt(since(start)))
        return True
