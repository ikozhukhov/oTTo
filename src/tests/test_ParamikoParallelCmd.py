from json import loads
from unittest import TestCase
import time

import vagrant
import paramiko

from otto.connections.ssh import parallelCmd as Cmd

paramiko.common.logging.basicConfig(level=paramiko.common.DEBUG)


class TestCmd(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vm = vagrant.Vagrant()
        cls.vm.up()
        c = cls.vm.conf()
        cls.ip = c.get('HostName')
        cls.port = c.get('Port')
        cls.password = 'vagrant'
        cls.user = 'vagrant'
        cls.many = 100

    @classmethod
    def tearDownClass(cls):
        cls.vm = vagrant.Vagrant()
        cls.vm.destroy()

    def test_paramiko_works(self):
        cmd = Cmd(self.user, self.ip, self.password, 'uname', int(self.port))
        cmd.client.connect(cmd.hostname, cmd.port, cmd.user, cmd.password)
        self.assertEqual(cmd.client.exec_command('uname')[1].read().strip(), 'SunOS')

    def test_run(self):
        cmd = Cmd(self.user, self.ip, self.password, 'uname', int(self.port))
        cmd.run()
        while not cmd.done:
            time.sleep(1)

        self.assertEqual(cmd.result[1].strip(), 'SunOS')

    def test_fio(self):
        cmd = Cmd(self.user, self.ip, self.password, 'sudo mkdir -p /ramfs', int(self.port))
        cmd.run()
        cmd.wait()

        cmd = Cmd(self.user, self.ip, self.password, 'sudo mount -t tmpfs -o size=3G -F tmpfs /ramfs/', int(self.port))
        cmd.run()
        cmd.wait()

        for _ in range(self.many):
            cmd = Cmd(self.user,
                      self.ip,
                      self.password,
                      "sudo /opt/csw/bin/fio --output-format=json --ioengine=solarisaio "
                      "--end_fsync=1 --direct=0 --fadvise_hint=0 "
                      "--thread --norandommap --randrepeat=0 --refill_buffers "
                      "--rwmixread=70 --runtime=35 --time_based --ramp_time=5 "
                      "--group_reporting --output-format=json --size=2G "
                      "--name='run5;1;randwrite;64k;64' "
                      "--sync=1 --rw=randwrite --bs=64k --iodepth=64",
                      port=int(self.port))
            cmd.run()
            cmd.wait()
            print cmd.command
            print cmd.result

            self.assertIsInstance(loads(cmd.result[1]), dict)

    def test_Manyloops(self):
        for _ in range(self.many):
            cmd = Cmd(self.user, self.ip, self.password, 'cat /usr/dict/words', int(self.port))
            cmd.run()
            cmd.wait()
            self.assertEqual(len(cmd.result[1]), 206695)  # TODO: calculate size then check against that

    def test_ManyConnections(self):
        connections = []
        for x in range(10):
            connections.append(Cmd(self.user, self.ip, self.password, 'cat /usr/dict/words', int(self.port)))
            print x

        for cmd in connections:
            cmd.run()

        while False in [cmd.done for cmd in connections]:
            time.sleep(.01)

        for cmd in connections:
            self.assertEqual(len(cmd.result[1]), 206695)  # TODO: calculate size then check against that
