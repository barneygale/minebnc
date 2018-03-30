MineBNC: A Minecraft Bouncer
============================

MineBNC is like an IRC bouncer for Minecraft. If you run MineBNC on something
like a VPS, it will keep you in-game when you close your Minecraft client.

This is early alpha software. Testing, feedback and improvements are very
welcome.

Installation
------------

Clone this repository and edit ``minebnc.py`` to configure the proxy. Then:

.. code-block:: console

    $ pip install quarry
    $ cd minebnc
    $ python minebnc.py

To make MineBNC persistent, run it within ``tmux`` or ``screen``.