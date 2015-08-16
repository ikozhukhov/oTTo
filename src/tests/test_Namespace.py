import unittest

from otto.lib.otypes import Namespace


class TestNamespace(unittest.TestCase):
    def setUp(self):
        self.general = {'initos': 'solaris'}
        cfg = {'General': self.general,
               'sol_host_1': {'type': 'host',
                              'hostname': '172.16.170.136',
                              'username': 'root',
                              'password': 'omnom',
                              },
               'lnx_host_1': {'type': 'host',
                              'hostname': '172.16.170.139',
                              'username': 'root',
                              'password': 'omnom',
                              },
               'win_host_1': {'type': 'host',
                              'hostname': '172.16.170.128',
                              'username': 'root',
                              'password': 'omnom',
                              },
               'srx_1': {'shelf': 181,
                         'cec_if': 'em1',
                         'password': 'omnom',
                         'lunconfig': {
                             '0': {'num_disks': 2, 'type': 'raid1', 'size': '-c', 'version': '1', 'iomode': 'random'},
                             '1': {'num_disks': 3, 'type': 'raid5', 'size': '2G', 'version': '0', 'clean': 'False'},
                             '2': {'num_disks': 4, 'type': 'raid6rs', 'size': '-c', 'version': '0', 'iomode': 'random'},
                             '3': {'num_disks': 4, 'type': 'raid10', 'size': '10G', 'version': '1'},
                             '4': {'num_disks': 2, 'type': 'raid0', 'size': '-c', 'version': '1'},
                             # can't use '5' format for test_dictsBecomeNamespaces
                             'five': {'num_disks': 1, 'type': 'jbod', 'size': '4G', 'version': '1'}, },
                         },
               }

        self.ns = Namespace(cfg)

    def test_getOneDeep(self):
        self.assertNotEquals(id(self.ns.General), id(self.general))
        self.assertEquals(self.ns.General, self.general)

    def test_getDeeperThanOne(self):
        self.assertEquals(self.ns.srx_1.lunconfig['1']['num_disks'], 3)

    def test_dictsBecomeNamespaces(self):
        self.assertEquals(self.ns.srx_1.lunconfig.five.num_disks, 1)


if __name__ == '__main__':
    unittest.main()
