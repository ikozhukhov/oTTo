import subprocess
import re


class Ddt(object):
    """
    A class for interacting ddt program under *nix
    There are no checks for bad parameters.
    read and write methods return a Popen if successful, None if already in use,
      or raise an exception
    generally- errors return None
    exceptions are not caught
    """

    # spawn failures - raised as OSError or ValueError

    def __init__(self, device, bsize, count, threads=1, sleep=5):
        self.device = device  # filename/path
        self.bsize = bsize  # block size in bytes (## KMGT)
        self.count = count  # number of blocks to read/write
        self.threads = threads  # number of threads to use
        self.sleeptime = sleep  # time to sleep between write and read
        self.ddtpipe = None  # pipe ID of running ddt
        self.output = None  # where to stash the cmd output if we get it
        self.cmd = ""  # the command we will/have used to start ddt

    # ddt options
    #
    # -rw combined option--
    # to simplify code, combining write and read is not implimented, but as
    # an explicit filename is required for filesystem-based tests (below), this
    # should not be a problem. Do one, then do the other.
    #
    # The -f option--
    # from the man page:
    #       Ddt  takes  an  argument,  the directory to use as the base for throughput
    #       tests.  Ddt will create a file in this directory,  ddt.$pid,  and  immedi-
    #       ately  unlink  it  to  cause the file to be lost when ddt exits.  The file
    #       extension $pid is the process id of the running instance of ddt.
    #
    # because the only real difference between allowing ddt to name the output file
    # and explicitly spec'ing a name is the unlink, we will always use the -f flag.
    # this can cause a failure if the name is a directory on a mounted file system.
    # Don't do that.

    # Ignored options:
    # -U (see above)
    # -t total io (not needed, internally = count*bsize)
    # -d debug output
    # -v
    # -?

    def write(self):
        """Perform write test with ddt"""
        if self.ddtpipe:
            return None
        self.cmd = "ddt -w -n %s -c %s -b %s -s %s -f %s" % (
            self.threads, self.count, self.bsize, self.sleeptime, self.device)
        self.ddtpipe = subprocess.Popen(self.cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return self.ddtpipe

    def read(self):
        """Perform read test with ddt"""
        if self.ddtpipe:
            return None
        self.cmd = "ddt -r -n %s -c %s -b %s -s %s -f %s" % (
            self.threads, self.count, self.bsize, self.sleeptime, self.device)
        self.ddtpipe = subprocess.Popen(self.cmd.split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return self.ddtpipe

    def status(self):
        """Return status of ddt Popen - returns exit code or None (if still running)"""
        if not self.ddtpipe:
            return 'NoProcess'
        return self.ddtpipe.poll()

    def getresult(self):
        """Retieve output of ddt - blocks for completion"""
        if not self.ddtpipe:
            return None, None
        (o, e) = self.ddtpipe.communicate()  # this will block for completion
        self.ddtpipe = None  # mark as closed so we can't do this again
        self.output = o
        return o, e

    # we are not attempting to parse out the extended/debug info as it largely
    #  duplicates calling data
    def parse_rate_msg(self, txt=None):
        """Parse the output message from ddt, return a tuple of direction, rate, cpu%"""
        if not txt:
            txt = self.output
        res = re.search(r'(Read|Write) +([\d]+) +([\d]+)', txt)
        if res:
            return res.groups()
        else:
            return ()

# below is debug/test code

if __name__ == "__main__":

    from datetime import datetime
    import time

    print 'starting ', datetime.now()
    fu = Ddt('/dev/sdb', '1m', 300, 1, 5)

    print 'write ', datetime.now()
    fu.write()

    while fu.status() is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status()

    print 'output ', datetime.now()
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate (txt from object)', fu.parse_rate_msg()

    print 'again  ', datetime.now()
    print 'result ', fu.getresult()

    print 'starting read', datetime.now()
    fu = Ddt('/mnt/qwer', 'XX100m', 300)

    print 'read w/ bad size', datetime.now()
    fu.read()

    while fu.status() is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status()
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate', fu.parse_rate_msg(o)

    print 'starting read', datetime.now()
    fu = Ddt('/dev/sdb', '1m', 300)

    print 'read ', datetime.now()
    fu.read()

    while fu.status() is None:
        print "snooze"
        time.sleep(1)
    print 'status ', fu.status()
    (o, e) = fu.getresult()
    print 'o ', o
    print 'rate', fu.parse_rate_msg(o)
