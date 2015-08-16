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
.. autoclass:: otto.initiators.linux.LinuxSsh
    :members:
    :inherited-members:

Windows
-------
.. autoclass:: otto.initiators.windows.Windows
    :members:

Solaris
-------

.. autoclass:: otto.initiators.solaris.SolarisSsh
    :members:
        :inherited-members:
        :exclude-members: run, close, exec_command, get_host_keys, invoke_shell, load_host_keys, load_system_host_keys,
                          save_host_keys, set_log_channel, set_missing_host_key_policy, open_sftp

Esx
---
.. autoclass:: otto.initiators.esx.Esx
    :members:
