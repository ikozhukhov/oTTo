import subprocess
import re


class Ctl(object):
    """
    A class for interacting ctl program under *nix. There are no checks for bad ctl parameters.
    write and verify methods return a Popen if successful, None if already in use or raise an
    exception generally - errors return None.  Exceptions are not caught. Spawn failures are
    raised as OSError or ValueError.

    """

    def __init__(self, device, size, pattern=None, skip=None):
        self.complete = False
        self.ctlproc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.ctlproc = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.ctlproc = None  # mark as closed so we can't do this again
        self.device = device  # filename/path
        self.size = size  # size in bytes (## KMGT)
        self.ctlpid = None
        self.output = None  # where to stash the cmd output if we get it
        if pattern:
            self.pattern = pattern  # in ctl, 'key' is an unsigned long long
        else:
            self.pattern = 0
        if skip:
            self.skip = skip
        else:
            self.skip = 0

    def write(self):
        """
        Perform write test with Ctl
        """
        cmd = "ctl -q -s %s -w -t -T %s -k %s %s" % (self.skip, self.size, self.pattern, self.device)
        self.ctlpid = self.ctlproc.pid

    def verify(self):
        """
        Perform write/verify test with Ctl
        """
        if self.ctlpid:
            return None
        cmd = "ctl -q -s %s -rw -t -T %s -k %s %s" % (self.skip, self.size, self.pattern, self.device)
        self.ctlpid = self.ctlproc.pid

    @property
    def status(self):
        """
        Return status of Ctl Popen - returns exit code or None (if still running)
        """
        if not self.ctlproc:
            return 'NoProcess'
        return self.ctlproc.poll()

    def getresult(self):
        """
        Retieve output of Ctl - blocks for completion
        """
        if not self.ctlproc:
            return None, None
        (o, e) = self.ctlproc.communicate()  # this will block for completion
        self.output = o
        return o, e

    def parse_rate_msg(self, txt=None):
        """
        Parse the output message from ctl, return list of tuple of direction and rate
        """
        if not txt:
            txt = self.output
        res = re.findall(r'Avg (\w+) rate: ([\-0-9.]+)', txt)
        if res:
            return res
        else:
            return []

# below is debug/test code

if __name__ == "__main__":

    #    bar = r"Write rate:   0.0 MiB/s   \rWrite rate:  87.5 MiB/s   \rWrite rate:  79.8 MiB/s   \rWrite rate:  79.4 MiB/s   \rAvg write rate: 137.4 MiB/s    \n"
    #    bar = r"\rAvg read rate: 123.45 MiB/s"
    fu = Ctl('/mnt/qwer', '100m')

    from datetime import datetime
    import time

    print 'starting ', datetime.now()
    fu = Ctl('/mnt/qwer', '100m')

    print 'write ', datetime.now()
    fu.write()

    while fu.status is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status

    print 'output ', datetime.now()
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate (txt from object)', fu.parse_rate_msg()

    print 'again  ', datetime.now()
    print 'result ', fu.getresult()

    print 'starting verify', datetime.now()
    fu = Ctl('/mnt/qwer', 'XX100m')

    print 'verify w/ bad size', datetime.now()
    fu.verify()

    while fu.status is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate', fu.parse_rate_msg(o)

    print 'starting verify', datetime.now()
    fu = Ctl('/mnt/qwer', '100m')

    print 'verify ', datetime.now()
    fu.verify()

    while fu.status is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate', fu.parse_rate_msg(o)
