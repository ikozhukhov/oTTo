import gzip
from os import environ
from logging import getLogger, NullHandler
from pprint import pformat
from multiprocessing import Process, Value, Array
from time import sleep
import cStringIO

from simplejson import JSONDecodeError, loads

from otto.lib.common import wait_file_exists
from otto.lib.compute import average, standard_dev, median
from otto.lib.decorators import wait_until
from otto.lib.otypes import ReturnCode, InitiatorError, ConnectionError
from otto.utils import now

instance = environ.get('instance') or ''
logger = getLogger('otto' + instance + '.fio')
logger.addHandler(NullHandler())


def calculate_stats(stats):
    """
    processing fio json output as dict to return
    :param stats: a dictionary of the fio format::

        {"fio version" : "fio-2.1.4",
         "jobs" : [
           {
             "jobname" : "results",
             "groupid" : 0,
             "error" : 0,
             "read" : {
               "io_bytes" : 131072,
               "bw" : 0,
               "iops" : 0,
               "runtime" : 0,
               "slat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00
               },
               "clat" : {
                 "min" : 0,
                 "max" : 1684,
                 "mean" : 11.34,
                 "stddev" : 31.27,
                 "percentile" : {
                   "1.000000" : 6,
                   "5.000000" : 7,
                   "10.000000" : 7,
                   "20.000000" : 8,
                   "30.000000" : 8,
                   "40.000000" : 8,
                   "50.000000" : 8,
                   "60.000000" : 9,
                   "70.000000" : 9,
                   "80.000000" : 9,
                   "90.000000" : 10,
                   "95.000000" : 14,
                   "99.000000" : 68,
                   "99.500000" : 93,
                   "99.900000" : 438,
                   "99.950000" : 724,
                   "99.990000" : 1320,
                   "0.00" : 0,
                   "0.00" : 0,
                   "0.00" : 0
                 }
               },
               "lat" : {
                 "min" : 0,
                 "max" : 1684,
                 "mean" : 11.58,
                 "stddev" : 31.32
               },
               "bw_min" : 0,
               "bw_max" : 0,
               "bw_agg" : 0.00,
               "bw_mean" : 0.00,
               "bw_dev" : 0.00
             },
             "write" : {
               "io_bytes" : 0,
               "bw" : 0,
               "iops" : 0,
               "runtime" : 0,
               "slat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00
               },
               "clat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00,
                 "percentile" : {
                   "1.000000" : 0,
                   "5.000000" : 0,
                   "10.000000" : 0,
                   "20.000000" : 0,
                   "30.000000" : 0,
                   "40.000000" : 0,
                   "50.000000" : 0,
                   "60.000000" : 0,
                   "70.000000" : 0,
                   "80.000000" : 0,
                   "90.000000" : 0,
                   "95.000000" : 0,
                   "99.000000" : 0,
                   "99.500000" : 0,
                   "99.900000" : 0,
                   "99.950000" : 0,
                   "99.990000" : 0,
                   "0.00" : 0,
                   "0.00" : 0,
                   "0.00" : 0
                 }
               },
               "lat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00
               },
               "bw_min" : 0,
               "bw_max" : 0,
               "bw_agg" : 0.00,
               "bw_mean" : 0.00,
               "bw_dev" : 0.00
             },
             "trim" : {
               "io_bytes" : 0,
               "bw" : 0,
               "iops" : 0,
               "runtime" : 0,
               "slat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00
               },
               "clat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00,
                 "percentile" : {
                   "1.000000" : 0,
                   "5.000000" : 0,
                   "10.000000" : 0,
                   "20.000000" : 0,
                   "30.000000" : 0,
                   "40.000000" : 0,
                   "50.000000" : 0,
                   "60.000000" : 0,
                   "70.000000" : 0,
                   "80.000000" : 0,
                   "90.000000" : 0,
                   "95.000000" : 0,
                   "99.000000" : 0,
                   "99.500000" : 0,
                   "99.900000" : 0,
                   "99.950000" : 0,
                   "99.990000" : 0,
                   "0.00" : 0,
                   "0.00" : 0,
                   "0.00" : 0
                 }
               },
               "lat" : {
                 "min" : 0,
                 "max" : 0,
                 "mean" : 0.00,
                 "stddev" : 0.00
               },
               "bw_min" : 0,
               "bw_max" : 0,
               "bw_agg" : 0.00,
               "bw_mean" : 0.00,
               "bw_dev" : 0.00
             },
             "usr_cpu" : 0.00,
             "sys_cpu" : 0.00,
             "ctx" : 24,
             "majf" : 0,
             "minf" : 0,
             "iodepth_level" : {
               "1" : 100.00,
               "2" : 0.00,
               "4" : 0.00,
               "8" : 0.00,
               "16" : 0.00,
               "32" : 0.00,
               ">=64" : 0.00
             },
             "latency_us" : {
               "2" : 0.01,
               "4" : 0.00,
               "10" : 81.63,
               "20" : 14.22,
               "50" : 1.86,
               "100" : 1.83,
               "250" : 0.29,
               "500" : 0.06,
               "750" : 0.05,
               "1000" : 0.02
             },
             "latency_ms" : {
               "2" : 0.03,
               "4" : 0.00,
               "10" : 0.00,
               "20" : 0.00,
               "50" : 0.00,
               "100" : 0.00,
               "250" : 0.00,
               "500" : 0.00,
               "750" : 0.00,
               "1000" : 0.00,
               "2000" : 0.00,
               ">=2000" : 0.00
             }
           }
         ]
        }


    returns::

        { 'bw': {'average': 900.0, 'deviation': 900.0, 'median': 900.0},
          'iops': {'average': 1010.1, 'deviation': 10.1, 'median': 1010.0},
          'lat': {'average': 0.2, 'deviation': 0.5, 'median': 0.1}
        }
    """

    iops = list()
    bw = list()
    lat = list()
    for s in stats:
        bw.append(s[0])
        iops.append(s[1])
        lat.append(s[2])

    report = dict()
    report['iops'] = {'median': median(iops), 'average': average(iops), 'deviation': standard_dev(iops)}
    report['bw'] = {'median': median(bw), 'average': average(bw), 'deviation': standard_dev(bw)}
    report['lat'] = {'median': median(lat), 'average': average(lat), 'deviation': standard_dev(lat)}
    logger.debug(pformat(report))
    return report


def verifyNoFioError(initiator, fname):
    r = False
    result = initiator.run('cat %s' % fname)
    for line in result.split('\n'):
        fioOutput = line.split(';')
        if len(fioOutput) > 4:
            if int(fioOutput[4]) != 0:
                return False
            else:
                r = True
    return r


def check_margins(curr, prev, delta):
    ret = ReturnCode(True, 'All parameters are under the expected error margin of %s' % delta)
    for value in ['iops', 'bw', 'lat']:
        for stat in ['deviation', 'average', 'median']:
            logger.info('value: %s stat: %s', value, stat)
            currstat = curr[value][stat]
            prevstat = prev[value][stat]
            newdelta = (abs(currstat - prevstat) * 100) / prevstat
            logger.info('current: %f previous: %f delta: %f', currstat, prevstat, newdelta)

            if newdelta > delta:
                ret.status = False
                ret.message = 'Margin on %s: current: %f previous: %f outside of margin: %f' % \
                              (value, currstat, prevstat, delta)
                logger.info(ret.message)
    return ret


def fio_config(initiator, luns, shelf, tlen=None, mode='rw', size='1G'):
    args = str()

    if not len(size) ^ len(tlen):
        raise NotImplementedError("fio needs either time or size")

    if initiator.os == 'solaris':
        engine = 'solarisaio'
        find_target = initiator.targ2sd
    elif initiator.os == 'linux':
        engine = 'libaio'
        find_target = initiator.targ2dev
    else:
        raise NotImplementedError("fio_config only supports solaris and linux")
    if tlen:
        args = '-time_based '
    else:
        args += '--size=%s ' % size
    args += '--ioengine=%s ' % engine
    args += '--iodepth=64 '
    args += '--norandommap '
    args += '--group_reporting '
    if tlen:
        args += '--runtime=%s ' % tlen
    for i in luns:
        targ = '%s.%s' % (shelf, i)
        s = find_target(targ)
        if not s:
            raise InitiatorError('fio lun %s not found' % targ)
        args += '--name=rw-128-_%s ' % i
        args += '--bs=128k '
        args += '--rw=%s ' % mode
        if initiator.os == 'solaris':
            args += '--filename=/dev/rdsk/%sp0 ' % s
        elif initiator.os == 'linux':
            args += '--filename=/dev/%s ' % s
    return args


def nofiorunning(initiator):
    """
    Return True if fio is not running
    """
    return not fio_is_running(initiator)


@wait_until(sleeptime=5)
def wait_nofiorunning(initiator):
    return nofiorunning(initiator)


def fio(initiator, devnam=None, secs=None, rw=None, bs=None):
    """
    Pull out fio configuration options from fc and execute
    """
    if secs is None:
        cmd = 'fio --output-format=json %s> out 2> err &' % devnam
    else:
        cmd = "time (fio --minimal --output-format=json --runtime=%d --time_based " \
              "--rw=%s --bs=%s --ioengine=solarisaio --filename=/dev/rdsk/%sp0" \
              " --name=n0 >out 2>err) 2>time &" % (secs, rw, bs, devnam)
    initiator.run_and_check('set +m; rm -f *out *err')

    logger.info(cmd)
    initiator.run_and_check(cmd)
    for i in range(10):
        n = nofiorunning(initiator)
        if not n:
            return ReturnCode(True)
        sleep(1)
    return fioresult(initiator)


def run_fio(init1, args):
    """
    Pull out fio configuration options from fc and execute and block
    """
    init1.run_and_check('set +m; rm -f *out *err')
    cmd = 'fio --output-format=json %s> out 2> err &' % args
    logger.info(cmd)
    init1.run(cmd, wait=False)

    wait_nofiorunning(init1)

    return fioresult(init1)  # this should not be processing the results


def run_fio_bg(init1, args):
    """
    Pull out fio configuration options from fc and execute nonblocking
    """
    init1.run_and_check('set +m; rm -f *out *err')
    cmd = 'fio --output-format=json %s> out 2> err &' % args
    logger.info(cmd)
    return init1.run_and_check(cmd)


def fioresult(initiator, check=True, expectation=False):
    """
    Return the fio result. True: fio stdout. False: fio stderr.
    """

    wait_nofiorunning(initiator)
    wait_file_exists(initiator, 'out')
    sleep(15)
    result = initiator.run_and_check('cat out', expectation=expectation)
    if not result:
        return result
    if not result.message:
        result = initiator.run_and_check('cat err', expectation=expectation)
        if not result:
            return result
        if not result.message:
            return ReturnCode(False, 'err: no output')
        else:
            return ReturnCode(False, 'err: %s' % result.message)
    logger.info('fio result:\n%s', result.message)
    try:
        j = loads(result.message)
    except JSONDecodeError as e:
        print result.message
        raise e

    if check:
        for i in range(len(j['jobs'])):
            if j['jobs'][i]['error'] != 0:
                return ReturnCode(False, 'fio[%d] error code: %s' % (i, j['jobs'][i]['error']))
    return ReturnCode(True, j)


def fio_is_running(initiator, expectation=False):
    """
    Return True if fio is running
    """
    result = initiator.run_and_check("pgrep fio", expectation)
    if result:
        return True
    if not result and result.message is '':
        return False
    if not result and result.message is not '':
        raise InitiatorError(result.message)


class Fio(object):
    """
    a nonblocking fio object ::

        c = Fio(init, config)
        c.run()
        # do other things
        c.wait() # or use an 'if not c.done:' control struct
        c.result.status
        c.result.message

    When the remote fio job has completed it will set::

        .done to True
        .message with the dict version of the fio output
        .status with the exit code as a boolean

    and try to store the json data as a dict in .dict .

    """

    def __init__(self, connection, config, envvars=''):

        self.p = Process(target=self._runcmd, args=(self.__status, self.__message))
        self.initiator = type(connection)(connection.user, connection.hostname, connection.password)
        self.config = config
        self.envvars = envvars
        self.time = float()
        self.dict = dict()  # fio output in dict format
        self.started = False
        self.__status = Value('i')
        self.__message = Array('c', 10000)

    def _read(self, channelobj):
        """read until EOF"""
        buf = channelobj.readline()
        output = str(buf)
        while buf:
            buf = channelobj.readline()
            output += buf
        return output

    def _runcmd(self, status, message):
        """
        this private method is executed as a thread

        :type status: c_int representing a bool
        :type message: c_array of char
        """
        r = self.initiator.connect()
        if not r:
            logger.critical("connect failed ... enabling paramiko logging")
            import paramiko

            paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)
            r = self.initiator.connect()
            if not r:
                raise ConnectionError("Failed to connect %s" % r.message)

        monitortime = False
        if 'runtime' in self.config:
            config = self.config.split()
            monitortime = 0
            for param in config:
                if 'runtime' in param or 'ramp_time' in param:
                    monitortime += int(param.split('=')[1])
            monitortime += 120
            logger.critical("timeout set to %s" % monitortime)
        cmd = "%s fio --output-format=json %s | gzip" % (self.envvars, self.config)

        self.started = True
        start = now()

        try:
            if monitortime:
                result = self.initiator.run_and_check(cmd, monitortime)
            else:
                result = self.initiator.run_and_check(cmd)
                try:
                    logger.critical(pformat("".join(
                        gzip.GzipFile('', 'r', 0,
                                      cStringIO.StringIO(result.raw.stdout)).read())))
                except IOError as e:
                    logger.critical("couldn't write out result: %s %s", (e, result))
        except InitiatorError, e:
            result = ReturnCode(False, message=str(e))

        self.time = now() - start

        status.value = int(result.status)
        for i in range(len(result.message)):
            message[i] = str(result.message[i])

        self.initiator.disconnect()

    def wait(self):
        """
        This is basicaly join.  It blocks untill the job is done.
        :return: a dictionary version of the json output
        :rtype: dict
        """
        while not self.done:
            sleep(.1)

        return self.result

    def run(self):
        """
        start the fio job on the remote host
        """
        self.p.start()
        self.started = True

    @property
    def done(self):
        """
        :return: whether or not the job is complete
        :rtype: bool
        """
        if self.started and not self.p.is_alive():
            return True
        else:
            return False

    @property
    def result(self):
        """
        :return: a dictionary version of the json output
        :rtype: dict
        """
        if not self.done:
            return ReturnCode(False, message="Not done yet")
        else:
            message = str()
            try:
                message = "".join(gzip.GzipFile('', 'r', 0, cStringIO.StringIO(self.__message.raw)).read())
                message = loads(message)
            except (JSONDecodeError, IOError):
                message = message

            return ReturnCode(bool(self.__status.value), message)
