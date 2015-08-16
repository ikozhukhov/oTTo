initiators
==========
.. toctree::
    :maxdepth: 5

Ethdrv
------
.. autoclass:: otto.initiators.ethdrv.Ethdrv
:members:

Linux
-----


Paramiko Class
^^^^^^^^^^^^^^
.. autoclass:: otto.initiators._linux.LinuxSsh
:members:
            :inherited-members:
            :exclude-members: run, close, exec_command, get_host_keys, invoke_shell, load_host_keys, load_system_host_keys,
                              save_host_keys, set_log_channel, set_missing_host_key_policy, open_sftp

Windows
-------
.. autoclass:: otto.initiators.windows.Windows
:members:

Solaris
-------

Pexpect Remote
^^^^^^^^^^^^^^
.. autoclass:: otto.initiators.solaris.Solaris
:members:
                :inherited-members:
                :exclude-members: interact, compile_pattern_list, expect, expect_exact,expect_exact, expect_list, expect_loop
                                  file_no, flush, is_alive, is_tty, read, read_nonblocking, readline, run, send, sendcontrol,
                                  sendoeof, sendintr, sendlines, setecho, setwinsize, terminate, wait, write, writelines
Paramiko class
^^^^^^^^^^^^^^
.. autoclass:: otto.initiators.solaris.SolarisSsh
:members:
        :inherited-members:
            :exclude-members: run, close, exec_command, get_host_keys, invoke_shell, load_host_keys, load_system_host_keys,
                              save_host_keys, set_log_channel, set_missing_host_key_policy, open_sftp
        Esx
    ---
.. autoclass:: otto.initiators.esx.Esx
:members:
