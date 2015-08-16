#!/usr/bin/env python
"""
tests for the ethdrv-stat command
"""
import unittest
from textwrap import dedent
from StringIO import StringIO

from json import JSONDecoder
# pylint: disable=import-error,too-many-public-methods,global-statement


# noinspection PyUnresolvedReferences
from otto.lib.ethdrvstat import AoEStat, int2bitmask, bitmask2index

# the 3 is the bitmask of local ports that can see the mac address
# and the 1 is a boolean on whether or not the mac is an active(good) mac

ETHDRV_TARGETS_FILE = dedent("""\
                    185.0 002590c7671e 3 1
                    185.0 002590c7671f 3 1
                    185.1 002590c7671e 3 1
                    185.1 002590c7671f 3 1
                    185.3 002590c7671e 3 1
                    185.3 002590c7671f 3 1
                    185.35 002590c7671e 3 1
                    185.35 002590c7671f 3 1
                    185.34 002590c7671e 3 1
                    185.34 002590c7671f 3 1
                    185.33 002590c7671e 3 1
                    185.33 002590c7671f 3 1
                    185.32 002590c7671e 3 1
                    185.32 002590c7671f 3 1
                    185.31 002590c7671e 3 1
                    185.31 002590c7671f 3 1
                    185.30 002590c7671e 3 1
                    185.30 002590c7671f 3 1
                    185.29 002590c7671e 3 1
                    185.29 002590c7671f 3 1
                    185.28 002590c7671e 3 1
                    185.28 002590c7671f 3 1
                    185.27 002590c7671e 3 1
                    185.27 002590c7671f 3 1
                    185.26 002590c7671e 3 1
                    185.26 002590c7671f 3 1
                    185.25 002590c7671e 3 1
                    185.25 002590c7671f 3 1
                    185.24 002590c7671e 3 1
                    185.24 002590c7671f 3 1
                    185.23 002590c7671e 3 1
                    185.23 002590c7671f 3 1
                    185.22 002590c7671e 3 1
                    185.22 002590c7671f 3 1
                    185.21 002590c7671e 3 1
                    185.21 002590c7671f 3 1
                    185.20 002590c7671e 3 1
                    185.20 002590c7671f 3 1
                    185.19 002590c7671e 3 1
                    185.19 002590c7671f 3 1
                    185.18 002590c7671e 3 1
                    185.18 002590c7671f 3 1
                    185.17 002590c7671e 3 1
                    185.17 002590c7671f 3 1
                    185.16 002590c7671e 3 1
                    185.16 002590c7671f 3 1
                    185.15 002590c7671e 3 1
                    185.15 002590c7671f 3 1
                    185.14 002590c7671e 3 1
                    185.14 002590c7671f 3 1
                    185.13 002590c7671e 3 1
                    185.13 002590c7671f 3 1
                    185.12 002590c7671e 3 1
                    185.12 002590c7671f 3 1
                    185.11 002590c7671e 3 1
                    185.11 002590c7671f 3 1
                    185.10 002590c7671e 3 1
                    185.10 002590c7671f 3 1
                    185.9 002590c7671e 3 1
                    185.9 002590c7671f 3 1
                    185.8 002590c7671e 3 1
                    185.8 002590c7671f 3 1
                    185.7 002590c7671e 3 1
                    185.7 002590c7671f 3 1
                    185.6 002590c7671e 3 1
                    185.6 002590c7671f 3 1
                    185.5 002590c7671e 3 1
                    185.5 002590c7671f 3 1
                    185.4 002590c7671e 3 1
                    185.4 002590c7671f 3 1
                    185.2 002590c7671e 3 1
                    185.2 002590c7671f 3 1
                    53.100 003048661704 1 1
                    """)

ETHDRV_DEVICES_FILE = dedent("""\
                            3:0:185:0 185.0 480.103GB
                            3:0:185:1 185.1 480.103GB
                            3:0:185:3 185.3 480.103GB
                            3:0:185:35 185.35 299.999GB
                            3:0:185:34 185.34 3000.592GB
                            3:0:185:33 185.33 299.999GB
                            3:0:185:32 185.32 299.999GB
                            3:0:185:31 185.31 299.999GB
                            3:0:185:30 185.30 299.999GB
                            3:0:185:29 185.29 299.999GB
                            3:0:185:28 185.28 299.999GB
                            3:0:185:27 185.27 299.999GB
                            3:0:185:26 185.26 299.999GB
                            3:0:185:25 185.25 1000.204GB
                            3:0:185:24 185.24 1000.204GB
                            3:0:185:23 185.23 600.127GB
                            3:0:185:22 185.22 299.999GB
                            3:0:185:21 185.21 600.127GB
                            3:0:185:20 185.20 600.127GB
                            3:0:185:19 185.19 500.107GB
                            3:0:185:18 185.18 299.999GB
                            3:0:185:17 185.17 600.127GB
                            3:0:185:16 185.16 299.999GB
                            3:0:185:15 185.15 299.999GB
                            3:0:185:14 185.14 299.999GB
                            3:0:185:13 185.13 299.999GB
                            3:0:185:12 185.12 299.999GB
                            3:0:185:11 185.11 299.999GB
                            3:0:185:10 185.10 299.999GB
                            3:0:185:9 185.9 299.999GB
                            3:0:185:8 185.8 299.999GB
                            3:0:185:7 185.7 299.999GB
                            3:0:185:6 185.6 299.999GB
                            3:0:185:5 185.5 299.999GB
                            3:0:185:4 185.4 299.999GB
                            3:0:185:2 185.2 480.103GB
                            """)

ETHDRV_DEV_DIR = dedent("""\
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.0 -> ../sdb
                        lrwxrwxrwx. 1 root root 7 Aug 26 13:18 e185.1 -> ../sdak
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.10 -> ../sdab
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.11 -> ../sdaa
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.12 -> ../sdz
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.13 -> ../sdy
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.14 -> ../sdx
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.15 -> ../sdw
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.16 -> ../sdv
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.17 -> ../sdu
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.18 -> ../sdt
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.19 -> ../sds
                        lrwxrwxrwx. 1 root root 7 Aug 26 13:18 e185.2 -> ../sdaj
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.20 -> ../sdr
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.21 -> ../sdq
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.22 -> ../sdp
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.23 -> ../sdo
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.24 -> ../sdn
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.25 -> ../sdm
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.26 -> ../sdl
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.27 -> ../sdk
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.28 -> ../sdj
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.29 -> ../sdi
                        lrwxrwxrwx. 1 root root 7 Aug 26 13:18 e185.3 -> ../sdah
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.30 -> ../sdh
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.31 -> ../sdg
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.32 -> ../sdf
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.33 -> ../sde
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.34 -> ../sdd
                        lrwxrwxrwx. 1 root root 6 Aug 25 19:53 e185.35 -> ../sdc
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.4 -> ../sdai
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.5 -> ../sdag
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.6 -> ../sdaf
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.7 -> ../sdae
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.8 -> ../sdad
                        lrwxrwxrwx. 1 root root 7 Aug 25 19:53 e185.9 -> ../sdac
                        """)

OUTPUT = dedent("""\
                e185.0     sdb         480.103GB    0,1
                e185.1     sdak        480.103GB    0,1
                e185.3     sdah        480.103GB    0,1
                e185.35    sdc         299.999GB    0,1
                e185.34    sdd        3000.592GB    0,1
                e185.33    sde         299.999GB    0,1
                e185.32    sdf         299.999GB    0,1
                e185.31    sdg         299.999GB    0,1
                e185.30    sdh         299.999GB    0,1
                e185.29    sdi         299.999GB    0,1
                e185.28    sdj         299.999GB    0,1
                e185.27    sdk         299.999GB    0,1
                e185.26    sdl         299.999GB    0,1
                e185.25    sdm        1000.204GB    0,1
                e185.24    sdn        1000.204GB    0,1
                e185.23    sdo         600.127GB    0,1
                e185.22    sdp         299.999GB    0,1
                e185.21    sdq         600.127GB    0,1
                e185.20    sdr         600.127GB    0,1
                e185.19    sds         500.107GB    0,1
                e185.18    sdt         299.999GB    0,1
                e185.17    sdu         600.127GB    0,1
                e185.16    sdv         299.999GB    0,1
                e185.15    sdw         299.999GB    0,1
                e185.14    sdx         299.999GB    0,1
                e185.13    sdy         299.999GB    0,1
                e185.12    sdz         299.999GB    0,1
                e185.11    sdaa        299.999GB    0,1
                e185.10    sdab        299.999GB    0,1
                e185.9     sdac        299.999GB    0,1
                e185.8     sdad        299.999GB    0,1
                e185.7     sdae        299.999GB    0,1
                e185.6     sdaf        299.999GB    0,1
                e185.5     sdag        299.999GB    0,1
                e185.4     sdai        299.999GB    0,1
                e185.2     sdaj        480.103GB    0,1
                """)

# Partitioned drives case
ETHDRV_DEV_DIR += dedent("""\
                        lrwxrwxrwx 1 root root 6 Sep 10 09:38 e53.100 -> ../sdg
                        lrwxrwxrwx 1 root root 7 Sep 10 09:38 e53.100p1 -> ../sdg1
                        lrwxrwxrwx 1 root root 7 Sep 10 09:38 e53.100p2 -> ../sdg2
                        """)
OUTPUT += dedent("""\
                e53.100    sdg        2000.409GB    0
                """)

ETHDRV_DEVICES_FILE += dedent("""\
                            3:0:53:100 53.100 2000.409GB
                            """)

# extra fields case ( vhba )
ETHDRV_TARGETS_FILE += dedent("""\
                    33.92 00259064a7de 1 1 345
                    178.5 0025900860ca 1 1 345
                    """)


def mock_open_file(fname):
    """
    return a file-like object containing content of
    the appropriate file
    """
    mockmap = {"/proc/ethdrv/devices": ETHDRV_DEVICES_FILE,
               "/proc/ethdrv/targets": ETHDRV_TARGETS_FILE,
               "/dev/ethdrv": ETHDRV_DEV_DIR}
    return StringIO(mockmap[fname])


def mock_mk_map(fname):
    """
    return a dict that represents the relationship
    between an aoe target and a scsi device
    """
    mockmap = dict()
    if fname == "/dev/ethdrv":
        for line in ETHDRV_DEV_DIR.splitlines():
            line = line.split()
            target = line[-3]
            dev = line[-1].split('../')[-1]  # I'm sorry for your eyes
            mockmap[target] = dev
    else:
        raise ValueError("Unknown path %s" % fname)
    return mockmap


class TestAoestat(unittest.TestCase):
    """
    tests for the etherdrv-stat command
    """

    def setUp(self):
        self.aoestat = AoEStat()
        self.aoestat.open_file = mock_open_file
        self.aoestat.mk_map = mock_mk_map

    def test_get_devices(self):
        """
        we can read /proc/ethdrv/devices
        """
        self.aoestat.get_devices()
        self.assertIsInstance(self.aoestat.devices, list)

        devfile = ETHDRV_DEVICES_FILE.splitlines()
        self.assertEqual(len(devfile), len(self.aoestat.devices))

        for device in self.aoestat.devices:
            self.assertRegexpMatches(device.target, r"[0-9]*\.[0-9]*")
            self.assertRegexpMatches(device.size, r"[0-9]*\.[0-9]*GB")

    def test_get_targets(self):
        """
        we can read /proc/ethdrv/targets
        """
        self.aoestat.update()
        for device in self.aoestat.devices:
            self.assertIsInstance(device.macs, list)
            self.assertNotEqual(len(device.macs), 0)
            self.assertIsInstance(device.ports, set)

    def test_str_output(self):
        """
        can output a string
        """
        self.aoestat.update()
        self.assertIsInstance(self.aoestat.output(), str)

    def test_json_output(self):
        """
        output is a string containing json that transforms cleanly to a dict
        """
        self.aoestat.update()
        joutput = self.aoestat.output(json=True)
        doutput = JSONDecoder().decode(joutput)

        self.assertIsInstance(doutput, dict)

    def test_update_with_no_targets(self):
        """
        if /dev/ethdrv is empty we report the target as 'init'
        """
        global ETHDRV_DEV_DIR
        backup = ETHDRV_DEV_DIR
        ETHDRV_DEV_DIR = ''
        self.aoestat.update()
        for targ in self.aoestat.devices:
            self.assertEqual(targ.file, 'init')
        ETHDRV_DEV_DIR = backup

    def test_compare_outputs(self):
        """
        compare .output to the sample 'OUTPUT'
        captured from previous version of ethdrv-stat
        """
        self.aoestat.update()
        self.assertEqual(self.aoestat.output(), OUTPUT)

    def test_paths_list_length(self):
        """
        test that the -a output is the right length
        it should be more than without -a
        """
        self.aoestat.update()
        output = self.aoestat.output()
        output_a = self.aoestat.output(paths=True)

        targets = 0
        ports = 0
        numlines = len(output_a.splitlines())

        for target in self.aoestat.devices:
            targets += 1
            ports += len(target.ports)

        expected_len = targets + ports
        output_len = len(output.splitlines())

        self.assertGreater(numlines, output_len)
        self.assertEqual(numlines, expected_len)

    def test_int2bitmask(self):
        self.assertEqual(int2bitmask(15903), '11111000011111')
        self.assertEqual(int2bitmask(16383), '11111111111111')
        self.assertEqual(int2bitmask(1), '1')
        self.assertEqual(int2bitmask(2), '10')
        self.assertEqual(int2bitmask(3), '11')

    def test_bitmask2index(self):
        ones = '11111111111111'
        self.assertEqual(bitmask2index(ones), list(range(len(ones))))
        self.assertEqual(bitmask2index('1'), [0])
        self.assertEqual(bitmask2index('10'), [1])
        self.assertEqual(bitmask2index('11'), [0, 1])
        self.assertEqual(bitmask2index('111'), [0, 1, 2])
        self.assertEqual(bitmask2index('11111000011111'), [0, 1, 2, 3, 4, 9, 10, 11, 12, 13])


if __name__ == '__main__':
    unittest.main()
