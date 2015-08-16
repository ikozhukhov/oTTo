import unittest

from otto.lib.otypes import AoEAddress, AoEError


class TestAoEAddress(unittest.TestCase):
    def setUp(self):
        self.x = AoEAddress(1, 4)

    def test_can_instantiate(self):
        typ = type(AoEAddress(1, 4))
        self.assertIs(typ, AoEAddress)

    def test_can_cast_to_string(self):
        self.assertEquals(str(self.x), "1.4")

    def test_can_coerse_to_string(self):
        self.x.major = 1
        self.x.minor = 4
        self.assertEquals(self.x, "1.4")

    def test_iadd(self):
        self.x += 1
        self.assertEquals(self.x.shelf, 1)
        self.assertEquals(self.x.slot, 5)
        self.assertEquals(self.x.major, 1)
        self.assertEquals(self.x.minor, 5)

    def test_exception_max_minor_with_iadd(self):
        self.x.slot = 255
        with self.assertRaises(AoEError):
            self.x += 1

    def test_exception_max_minor_with_add(self):
        self.x.slot = 255
        with self.assertRaises(AoEError):
            self.x += 1

    def test_exception_max_minor_with_assignment(self):
        with self.assertRaises(AoEError):
            self.x.slot = 256

    def test_exception_min_minor_with_assignment(self):
        with self.assertRaises(AoEError):
            self.x.minor = -1

    def test_exception_min_major_with_assignment(self):
        with self.assertRaises(AoEError):
            self.x.major = -2

    def test_exception_invalid_instatiation(self):
        with self.assertRaises(AoEError):
            AoEAddress("1")

        with self.assertRaises(AoEError):
            AoEAddress(1)

        with self.assertRaises(AoEError):
            AoEAddress("a")

        with self.assertRaises(AoEError):
            AoEAddress("[]")

    def test_dict_instantiation(self):
        s = {'shelf': '1', 'slot': '7'}
        x = AoEAddress(s)
        assert (x.major == 1 and x.minor == 7)

    def test_str_dict_instantiation(self):
        s = {'shelf': '1', 'slot': '7'}
        x = AoEAddress(s)
        assert (x.major == 1 and x.minor == 7)

    def test_int_dict_instantiation(self):
        s = {'shelf': 4, 'slot': 9}
        x = AoEAddress(s)
        assert (x.major == 4 and x.minor == 9)


if __name__ == '__main__':
    unittest.main()
