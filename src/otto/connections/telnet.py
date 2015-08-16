import logging
import os

from otto.lib.pexpect import spawn

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.connections')
logger.addHandler(logging.NullHandler())


class Telnet(spawn, object):
    """
    Connect via telnet.  This spawns a process running the
    installed telnet client to interact with an appliance.
    """

    def __init__(self, username, hostname, password, prompt, port=None):
        self.username = username
        self.hostname = hostname
        self.password = password
        self.prompt = prompt
        self.port = port

    def connect(self, timeout=60, skip_login=False):
        """
        Connect to and authenticate with host.

        *timeout* how long to wait for connect

        """

        cmd = "telnet"
        args = list()
        args.append(self.hostname)
        if self.port:
            args.append(self.port)
        logger.debug(args)

        spawn.__init__(self, cmd, args, timeout)
        if not skip_login:
            self.expect([r"(?i)User.*", "(?i)User"])
            self.send(self.username)
            self.send("\r")
            self.expect(self.username)
            self.expect([r"(?i)Password.*", "Password:"])
            self.send(self.password)
            self.send("\r")
        self.expect(self.prompt)
        return True

    def run(self, cmd):
        """
        This is the main command only real operation.  It runs a command
        and returns the result.
        """
        logger.info(cmd)
        self.send(cmd)
        self.send("\r\n")
        self.expect(cmd)
        self.expect(self.prompt)
        response = self.before.strip()
        return response
