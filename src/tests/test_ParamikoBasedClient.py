from unittest import TestCase, skip

from otto.initiators._linux import LinuxSsh
from otto.lib.otypes import ConnectionError
from otto.utils import random_string
from otto.lib.contextmanagers import env

user = ''
hostname = ''
password = ''


@skip('add your client info above and comment skip out')
class TestClient(TestCase):
    def setUp(self):
        self.host = LinuxSsh(user, hostname, password)

    def test_connect(self):
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)
        chan = self.host.get_transport().open_channel('session')
        self.assertIsInstance(chan.getpeername()[0], str)

    def test_run(self):
        self.assertTrue(self.host.connect().status)
        ret = self.host.run_and_check('echo $((2*3*7))')
        self.assertEqual(ret.status, True)
        self.assertEqual(ret.message, '42', msg='{0} = {1}'.format(ret.message, 42))
        self.assertTrue(self.host.disconnect())

    def test_reconnect(self):
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)

        self.assertTrue(self.host.disconnect())
        self.assertFalse(self.host.connected)

        self.assertTrue(self.host.reconnect(after=1))
        self.assertTrue(self.host.connected)

    def test_ls(self):
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)

        lsout = self.host.ls('/')
        self.assertIsInstance(lsout, list)
        for entry in lsout:
            self.assertIsInstance(entry, basestring)

    def test_mkdir(self):
        """
        can make a dir.  making a dir that exists raises
        """
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)

        dirname = "%s%s" % (self.host.run_and_check('mktemp -p /tmp'), 'test_dir')
        self.assertIs(self.host.mkdir(dirname), None)
        self.assertRaises(ConnectionError, self.host.mkdir, dirname)
        self.assertIsInstance(self.host.ls(dirname), list)

    def test_rm_rmdir_open_stat(self):
        """
        can remove a directory
        can't remove a directory that's not empty
        """
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)

        dirname = "%s%s" % (self.host.run_and_check('mktemp -p /tmp'), 'test_dir')
        filepath = "%s/%s" % (dirname, 'file')

        self.host.mkdir(dirname)
        chars = 10000

        data = random_string(chars)
        fhandle = self.host.open(filepath, mode='rw')
        fhandle.write(data)
        fhandle.close()

        fhandle = self.host.open(filepath, mode='r')
        self.assertEquals(fhandle.read(), data)
        stat = self.host.stat(filepath)
        self.assertEqual(stat.get('size'), chars)

        self.assertRaises(ConnectionError, self.host.rmdir, dirname)
        self.host.rm(filepath)
        self.host.rmdir(dirname)

    def test_disconnect(self):
        """
        ensure we set connected to False
        """
        self.assertTrue(self.host.connect().status)
        self.assertTrue(self.host.connected)

        self.assertTrue(self.host.disconnect())
        self.assertFalse(self.host.connected)

    def test_env_context_manager(self):
        """
        tests that we apply environment variables correctly
        """
        self.host.connect()
        value1 = random_string(8)
        with env(self.host, 'TESTVAR', value1):
            self.assertEqual(self.host.run('printenv TESTVAR').message.strip(), value1)

    def test_nested_env_context_manager(self):
        """
        tests that we apply environment variables correctly
        """
        self.host.connect()
        value1 = random_string(8)

        with env(self.host, 'TESTVAR', value1):
            self.assertEqual(self.host.run('printenv TESTVAR').message.strip(), value1)

            value2 = random_string(8)
            with env(self.host, 'TESTVAR', value2):
                self.assertEqual(self.host.run('printenv TESTVAR').message.strip(), value2)

            self.assertEqual(self.host.run('printenv TESTVAR').message.strip(), value1)

    @skip
    def test_cd_contextmanager(self):
        """
        tests that we observe the cwd value and that it gets reset
        upon exit of context
        :return:
        :rtype:
        """
        self.assertTrue(False)
