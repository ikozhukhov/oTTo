# -*- coding: utf-8 -*-
"""
Paramiko based ssh module
"""
import os
import logging
import socket
from time import sleep, time
from multiprocessing import Process, Value, Array

import paramiko

from otto.lib.contextmanagers import ignored
from otto.lib.otypes import ReturnCode, ConnectionError, Data, Namespace

instance = os.environ.get('instance') or ''
logger = logging.getLogger('otto' + instance + '.connections')
logger.addHandler(logging.NullHandler())


# pylint: disable=R0903,R0902,R0904
class AllowAnythingPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        return


# noinspection PyMethodOverriding
class Client(paramiko.SSHClient):
    """
    Connect to a host using paramiko, a Python interface to the SSH2 protocol. Transport compression
    is enabled by default now.

    Client.environmentals is a dictionary of environment variables to be set.  They can be manipulated
    on the fly with care or using the env context manager, otto.lib.contextmanager.env().
    """
    # pylint: disable=R0913,R0921
    def __init__(self, host, user, password, port=22, compress=True):
        self.cwd = str()
        self.environmentals = dict()
        self.host = host
        self.user = user
        self.port = port
        self.password = password
        super(Client, self).__init__()
        self.compression = compress
        self.set_log_channel('otto' + instance + '.connections')
        self.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.connected = False

    # pylint: disable=W0221
    def connect(self, timeout=10, key_file=None):
        """
        Currently this method will return False if we can't connect.  If the script
        ignores this return and proceeds the traceback might not be obvious as to
        where the problem was.

        """

        # Policy for automatically adding the hostname and new host key to the local HostKeys
        try:
            # Calling the base class connect method.
            super(Client, self).connect(hostname=self.host,
                                        port=self.port,
                                        username=self.user,
                                        password=self.password,
                                        timeout=timeout,
                                        key_filename=key_file,
                                        compress=self.compression)

        except paramiko.BadHostKeyException as e:
            message = "Server's host key could not be verified"
            logger.critical(message)
            logger.error(e)
            return ReturnCode(False, message=message)
        except paramiko.AuthenticationException as e:
            message = "Authentication with the server failed"
            logger.critical(message)
            logger.error(e)
            return ReturnCode(False, message=message)
        except paramiko.SSHException as e:
            message = "Couldn't complete connection"
            # when stacking Exceptions superclasses will catch subclasses
            logger.critical(message)
            logger.error(e)
            return ReturnCode(False, message=message)
        except socket.timeout as e:
            message = "No response from host"
            logger.critical(message)
            logger.error(e)
            return ReturnCode(False, message=message)
        except socket.error as e:
            message = "Connection refused"
            logger.critical(message)
            logger.error(e)
            return ReturnCode(False, message=message)

        self.connected = True
        return ReturnCode(True, message=self.connected)

    def run(self, cmd, timeout=None, bufsize=-1):
        """
        :param cmd: command to run on remote host
        :type cmd: str

        :param timeout: timeout on blocking read/write operations when exceeded socket error will be raised
        :type timeout: float
        :param bufsize: byte size of the buffer for the filehandle returned
        :type bufsize: int
        :rtype: ReturnCode
        """
        ret = ReturnCode(False)
        if not self.connected:
            raise ConnectionError("Run was called on an unconnected host. Did you check the result of connect()?")
        try:
            if self.environmentals:
                envstring = str()
                for var, value in self.environmentals.items():
                    statement = "%s=%s " % (var, value)
                    envstring += statement
                cmd = "%s%s" % (envstring, cmd)
            if self.cwd:
                cmd = "cd %s && %s" % (self.cwd, cmd)
            self._log(logging.DEBUG, 'running command: "%s"' % cmd)
            stdin, stdout, stderr = self.exec_command(command=cmd, timeout=timeout, bufsize=bufsize)
        except paramiko.SSHException as e:
            err = "Couldn't complete the command: %s" % str(e)
            logger.critical(err)
            ret.message = err
            return ret

        # we must read stderr _before_ stdout
        # otherwise paramiko losses the stdout data
        try:
            ret.raw = Data(ret.raw.status, ret.raw.stdout, stderr.read())
        except socket.timeout:
            ret.message = "Timeout"
            return ret

        status = stdout.channel.recv_exit_status()
        ret.raw = Data(status, stdout.read(), ret.raw.stderr)

        if status != 0:
            ret.message = ret.raw.stderr
        else:
            ret.status = True
            ret.message = ret.raw.stdout

        stdin.close()

        return ret

    def disconnect(self):
        """
        Disconnect from the host.
        """
        self.close()
        self.connected = False
        return self._transport is None

    def reconnect(self, after=10, timeout=10, key_file=None, conn_attempts=10):
        """
        This method will attempt to reconnect with the host, maybe after a reboot action.

        The method will have a limit of 10 attempts to connect by default, for a total
        of 300 seconds before it gives up with the reconnection.

        """
        self.close()
        sleep(after)

        if conn_attempts:
            for i in range(conn_attempts):
                with ignored(ConnectionError):
                    logger.debug('Attempt %d of %d to re-connect to the host', i, conn_attempts)
                    self.connect(timeout=timeout, key_file=key_file)
                    self.connected = True
                    return True
        else:
            down = True
            i = 1
            while down:
                with ignored(ConnectionError):
                    logger.debug('Attempt %d of inf to re-connect to the host', i)
                    if self.connect(timeout=timeout, key_file=key_file):
                        down = False
                        self.connected = True
                    i += 1
            return True

        logger.error("Giving up, no attempts left to re-connect to host")
        return False

    def ls(self, path=None, expectation=True):
        """
        return a list of files in path.  If path is not specified cwd will be used.  If
        path does not exist an exception will be raised unless expectation is False. Works
        in conjunction with the cd context manager.
        """
        sftp = self.open_sftp()
        if not path:
            path = ""
        try:
            if path:
                if path[0] == '/':
                    return sftp.listdir(path=path)
                else:
                    return sftp.listdir(path="%s%s" % (self.cwd, path))
            else:
                if self.cwd:
                    return sftp.listdir(path=self.cwd)
                else:
                    return sftp.listdir()
        except IOError as e:
            if not expectation:
                return []
            else:
                raise ConnectionError("ls %s failed: %s" % (path, e))

    def mkdir(self, dirname, mode=511, expectation=True):
        sftp = self.open_sftp()

        try:
            if dirname[0] == '/':
                return sftp.mkdir(path=dirname, mode=mode)
            else:
                return sftp.mkdir(path="%s%s" % (self.cwd, dirname), mode=mode)

        except IOError as e:
            if not expectation:
                return []
            else:
                raise ConnectionError("mkdir %s failed: %s" % (dirname, e))

    def rmdir(self, dirname, expectation=True):
        """
        remove a directory named by a string
        """
        sftp = self.open_sftp()

        try:
            if dirname[0] == '/':
                return sftp.rmdir(path=dirname)
            else:
                return sftp.rmdir(path="%s%s" % (self.cwd, dirname))

        except IOError as e:
            if not expectation:
                return []
            else:
                raise ConnectionError("rmdir %s failed: %s" % (dirname, e))

    def rm(self, path, expectation=True):
        """
        remove a file named by a string
        """
        sftp = self.open_sftp()

        try:

            if path[0] == '/':
                return sftp.remove(path=path)
            else:
                return sftp.remove(path="%s%s" % (self.cwd, path))

        except IOError as e:
            if not expectation:
                return []
            else:
                raise ConnectionError("rm %s failed: %s" % (path, e))

    def open(self, fname, mode='r', bufsize=-1, expectation=True):
        """
        return a file-like object of fname on the remote
        """
        sftp = self.open_sftp()
        try:
            ret = sftp.file(fname, mode, bufsize, )
        except IOError as e:
            if not expectation:
                ret = ReturnCode(False, "file failed: %s" % e)
            else:
                raise ConnectionError(str(e))
        return ret

    def stat(self, path):
        """
        returns a namespace of::

                {'size' : st.st_size,
                 'uid': st.st_uid,
                 'gid': st.st_gid,
                 'mode': st.st_mode,
                 'atime': st.st_atime,
                 'mtime': st.st_mtime,
                 }

        this can accessesed like so::

            fstat= init.stat('/etc/passwd')
            fstat.flags

        :param path:
        :type path: str
        :return:
        :rtype: Namespace
        """
        sftp = paramiko.SFTPClient.from_transport(self.get_transport())
        st = sftp.stat(path)
        dstat = {'size': st.st_size,
                 'uid': st.st_uid,
                 'gid': st.st_gid,
                 'mode': st.st_mode,
                 'atime': st.st_atime,
                 'mtime': st.st_mtime, }

        ret = Namespace(dstat)
        return ret


class parallelCmd(object):
    """
    a non-blocking remote command running object ::

        c = Cmd(init, params)
        c.run()
        # do other things
        c.wait() # or use an 'if not c.done:' control struct
        c.result.status
        c.result.message

    When the remote job has completed it will set::

        .done to True
        .message with the dict version of the fio output
        .status with the exit code as a boolean

    and try to store the json data as a dict in .dict .

    """

    def __init__(self, user, hostname, password, command, port=22):

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.command = command
        self.time = float()
        self.dict = dict()  # fio output in dict format
        self.started = False

        # synchonization varaibles
        self.__status = Value('i')
        self.__stdout = Array('c', 1000000)  # 1 MB
        self.__stderr = Array('c', 1000000)  # 1 MB

        self.p = None
        self.user = user
        self.hostname = hostname
        self.password = password
        self.port = port

    @staticmethod
    def _read(channelobj):
        """read until EOF"""
        buf = channelobj.readline()
        output = str(buf)
        while buf:
            buf = channelobj.readline()
            output += buf
        return output

    def _runcmd(self, status, stdout, stderr):
        """
        this private method is executed as a thread

        :type status: c_int representing a bool
        :type stdout: c_array of char
        :type stderr: c_array of char

        """

        self.started = True
        start = time()
        self.client.connect(self.hostname, self.port, self.user, self.password)
        stdin, sout, serr = self.client.exec_command(self.command)
        err = serr.read()
        for i in range(len(err)):
            stderr[i] = str(err[i])

        # we must read stderr _before_ stdout
        # otherwise paramiko loses the stdout data
        status = sout.channel.recv_exit_status()
        out = sout.read()
        status += int(status)

        # copy stdout into shared memory
        for i in range(len(out)):
            stdout[i] = str(out[i])
        self.client.close()
        self.time = time() - start

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
        Return the result as a NamedTuple this means that result can be sliced or
        referenced by name:

            status or 0: exitcode as int
            stdout or 1: stdout as str
            stderr or 2: stderr as str

        so upon completion the following:

            cmd.result[0]
            cmd.status

        are equivilent. *If the process is not complete this will block.*
        """
        if not self.done:
            self.wait()
        else:
            return Data(self.__status.value, str(self.__stdout.value), str(self.__stderr.value))

    def run(self):
        """
        start the job on the remote host
        """
        self.p = Process(target=self._runcmd, args=(self.__status, self.__stdout, self.__stderr))
        self.p.start()
        while not self.p.is_alive():
            sleep(.1)
            logger.debug("slept not started")
        else:
            self.started = True

    def wait(self):
        """
        This is basicaly a join.  It blocks untill the job is done.
        :return: a dictionary version of the json output
        :rtype: dict
        """
        then = time()
        while not self.done:
            sleep(.01)
        else:
            logger.debug("waited for {:10.4f} sec".format(time() - then))
        return self.result
