def lun_bytes(sze, base=1000):
    """
    Converts strings like '5T' to a base ten byte count.  Base two
    byte count can be calculated by setting the base to 1024. This
    is primarily for use with output from appliances.
    """
    m = sze[-1].lower()
    if m.isdigit():
        return sze

    v = float(sze[:-1])

    if base == 1000:
        multi = {'k': 1000,
                 'm': 1000000,
                 'g': 1000000000,
                 't': 1000000000000,
                 'p': 1000000000000000,
                 'e': 1000000000000000000,
                 'z': 1000000000000000000000,
                 'y': 1000000000000000000000000, }
    elif base == 1024:
        multi = {'k': 1024,
                 'm': 1048576,
                 'g': 1073741824,
                 't': 1099511627776,
                 'p': 1125899906842624,
                 'e': 1152921504606846976,
                 'z': 1180591620717411303424,
                 'y': 1208925819614629174706176, }
    else:
        multi = {'k': base ** 1,
                 'm': base ** 2,
                 'g': base ** 3,
                 't': base ** 4,
                 'p': base ** 5,
                 'e': base ** 6,
                 'z': base ** 7,
                 'y': base ** 8, }

    try:
        tenbytes = int(v) * multi.get(m)
    except (ArithmeticError, KeyError, TypeError):
        tenbytes = float('nan')
    return tenbytes


if __name__ == "__main__":
    from collections import OrderedDict

    names = OrderedDict([('k', ["kibibyte", "kilobyte"]),
                         ('m', ["mebibyte", "megabyte"]),
                         ('g', ["gibibyte", "gigabyte"]),
                         ('t', ["tebibyte", "terabyte"]),
                         ('p', ["pebibyte", "petabyte"]),
                         ('e', ["exbibyte", "exabyte"]),
                         ('z', ["zebibyte", "zetabyte"]),
                         ('y', ["yobibyte", "yotabyte"]),
                         ('n', ["notabyte", "notabyte"]), ])
    x = 0
    for base in (1024, 1000):

        for unit, name in names.iteritems():
            num = 89
            val = "%s%s" % (num, unit)
            print ("%s %8s (%s) is %s bytes" % (num, name[x], val, lun_bytes(val, base)))
        x += 1
