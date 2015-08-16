==========
appliances
==========

.. toctree::
    :maxdepth: 5

**structure**

The appliance modules are broken up into separate classes by appliance type.  Within each appliance type there
is a distinct class for each type of connection used::

    otto.appliances.vsx.ssh

This is intended to allow alternate connection types such as EL, REST etc, while ensuring the libraries code is clear
and well organized.


srx
---

.. autoclass:: otto.appliances.srx.Srx
    :members:
    :undoc-members:
    :inherited-members:
    :exclude-members: compile_pattern_list, eof, expect, expect_exact, expect_list, expect_loop,
                        fileno, flush, getecho, getwinsize, interact, isalive, isalive, kill, read, isatty,
                        read_nonblocking, readline, readlines, send, sendcontrol, sendeof,sendintr,
                        sendline, setecho, setwinsize, terminate, wait, write, writelines, run_and_check

.. autoclass:: otto.appliances.srx.SrxSsh
    :members:
    :undoc-members:
    :inherited-members:
    :exclude-members: compile_pattern_list, eof, expect, expect_exact, expect_list, expect_loop,
                        fileno, flush, getecho, getwinsize, interact, isalive, isalive, kill, read, isatty,
                        read_nonblocking, readline, readlines, send, sendcontrol, sendeof,sendintr,
                        sendline, setecho, setwinsize, terminate, wait, write, writelines, run_and_check

vsx
---
.. autoclass:: otto.appliances.vsx.Vsx
    :members:
    :undoc-members:
    :inherited-members:
    :exclude-members: compile_pattern_list, eof, expect, expect_exact, expect_list, expect_loop,
                        fileno, flush, getecho, getwinsize, interact, isalive, isalive, kill, read, isatty,
                        read_nonblocking, readline, readlines, send, sendcontrol, sendeof,sendintr,
                        sendline, setecho, setwinsize, terminate, wait, write, writelines, run_and_check, lvs2

