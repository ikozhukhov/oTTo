#!/usr/bin/python

from __future__ import print_function
import unittest

import paramiko

paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)

# Srx
host = '10.220.72.106'  # shelf 184
user = 'admin'
passwd = 'admin'
cmd1 = 'release'
cmd2 = 'model'

# Linux
# host = "node6.eng-ath.coraid.com"
# user = 'root'
# passwd = ''
# cmd1 = 'uname -s'
# cmd2 = 'uname -n'


class AllowAnythingPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self, client, hostname, key):
        return


@unittest.skip
class TestClient(unittest.TestCase):
    def setUp(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    def test_client_connect(self):
        print("Connect")
        self.client.connect(host,
                            username=user,
                            password=passwd,
                            allow_agent=False,
                            look_for_keys=False)

        self.assertTrue(self.client.get_transport())
        print("Connected")

    def test_client_execute_one_command(self):
        print("\nExecute One Command")
        self.client.connect(host,
                            username=user,
                            password=passwd,
                            allow_agent=False,
                            look_for_keys=False)

        _, stdout, stderr = self.client.exec_command(cmd1)
        err = stderr.read()
        status = stdout.channel.recv_exit_status()
        out = stdout.read()
        print("One:\t%s\t%s\t%s" % (err, status, out))

    def test_client_execute_two_commands(self):
        print("\nExecute Two Commands")
        self.client.connect(host,
                            username=user,
                            password=passwd,
                            allow_agent=False,
                            look_for_keys=False)

        _, stdout, stderr = self.client.exec_command(cmd2)
        err = stderr.read()
        status = stdout.channel.recv_exit_status()
        out = stdout.read()
        print("One\t%s\t%s\t%s" % (err, status, out))
        _, stdout, stderr = self.client.exec_command(cmd2)
        err = stderr.read()
        status = stdout.channel.recv_exit_status()
        out = stdout.read()
        print("Two\t%s\t%s\t%s" % (err, status, out))


if __name__ == '__main__':
    unittest.main()
