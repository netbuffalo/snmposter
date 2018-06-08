=============================================================================
snmposter
=============================================================================

SNMP Agent Simulator

This tool allows you to take the output of an snmpwalk command and then pretend
to be the agent that it was gathered from. This can be useful when you're
developing SNMP management tools.

Requirements
=============================================================================

Twisted, TwistedSNMP, PySNMP-SE and Tornado Web Server.

Twisted is available from PyPI and will be automatically installed if you go
the route of easy_install or pip. TwistedSNMP and PySNMP-SE are not currently
available from PyPI and should be individually downloaded from sourceforge
and installed from source.

Installation
=============================================================================

Follow the basic guidelines to use snmposter on CentOS.

  https://github.com/cluther/snmposter


Ubuntu 14.04
-----------------------------------------------------------------------------


1. Install Python development tools.

   .. sourcecode:: bash

      $ sudo apt-get install gcc python-dev python-setuptools python-tornado git-core

2. Install TwistedSNMP dependency.

   .. sourcecode:: bash

      $ wget http://downloads.sourceforge.net/project/twistedsnmp/twistedsnmp/0.3.13/TwistedSNMP-0.3.13.tar.gz
      $ tar -xzf TwistedSNMP-0.3.13.tar.gz
      $ cd TwistedSNMP-0.3.13
      $ sudo python setup.py install
      $ cd ..

3. Install PySNMP-SE dependency.

   .. sourcecode:: bash

      $ wget http://downloads.sourceforge.net/project/twistedsnmp/pysnmp-se/3.5.2/pysnmp-se-3.5.2.tar.gz
      $ tar -xzf pysnmp-se-3.5.2.tar.gz
      $ cd pysnmp-se-3.5.2
      $ sudo python setup.py install
      $ cd ..

4. Install my snmposter.

   .. sourcecode:: bash

      $ git clone https://github.com/netbuffalo/snmposter.git
      $ cd snmposter
      $ sudo python setup.py install
      $ cd ..


Basic Usage
=============================================================================

Installing will create a command line tool called `snmposter`. This tool
requires root access because it listens on 161/udp and creates loopback aliases
to support emulating multiple SNMP agents simultaneously.

The `snmposter` command takes a single command line argument: -f or --file.
The file passed to this option must contain one or more rows with two columns
each. The first column should be the absolute or relative path to a file
containing the output of an snmpwalk command. The second column should contain
an IP address that this snmpwalk data will be exposed on.

Example usage:

.. sourcecode:: bash

   $ sudo snmposter -f /path/to/agents.csv

Example contents of `/etc/snmposter/agents.csv`::

    /path/to/Cisco_2811.snmpwalk,127.0.1.11
    /path/to/NetApp_Filer_FAS3020.snmpwalk,127.0.1.12

This example usage will cause snmposter to run in the background, create two
new IP aliases on the loopback interface (127.0.1.11 and 127.0.1.12), and
expose the contents of each snmpwalk file as an SNMP agent on UDP port 161 of
the appropriate IP address. If you're going to be using this frequently I
would recommend adding some entries to your `/etc/hosts` file to make it even
easier.

Example additions to `/etc/hosts`::

    127.0.1.11      cisco-2811
    127.0.1.12      netapp-filer-fa3020


**Important Note**: The snmpwalk output file that snmposter consumes must be
generated with very specific snmpwalk command line options. These options allow
snmposter to get the most raw data possible and provides the most accurate
simulation.

Example snmpwalk command to generate the above `Cisco_2811.snmpwalk` file:

.. sourcecode:: bash

   # SNMPv1
   $ snmpwalk -v1 -c public -OQsbenU cisco2811-address .1 > Cisco_2811.snmpwalk

   # SNMPv2c
   $ snmpbulkwalk -v2c -c public -OQsbenU cisco2811-address .1 > Cisco_2811.snmpwalk

   $ head Cisco_2811.snmpwalk
   .1.3.6.1.2.1.1.1.0 = STRING: "Cisco Internetwork Operating System Software IOS (tm)..."
   .1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.9.1.317
   .1.3.6.1.2.1.1.3.0 = Timeticks: (880537345) 101 days, 21:56:13.45
   .1.3.6.1.2.1.1.4.0 = STRING: "netbuffalo"
   .1.3.6.1.2.1.1.5.0 = ""
   .1.3.6.1.2.1.1.6.0 = ""
   .1.3.6.1.2.1.1.7.0 = INTEGER: 12
   .1.3.6.1.2.1.2.1.0 = INTEGER: 5746
   .1.3.6.1.2.1.2.2.1.1.1 = INTEGER: 1
   .1.3.6.1.2.1.2.2.1.1.2 = INTEGER: 2

The important command line options are `-m none -O enU` to get the raw output and '-C c' 
to ignore out of sequence responses from the switch. (Sometimes this validation error is 
triggered when walking routing MIBS on some switches)

Don't worry if you get an error like `Cannot find module (none): At line 0 in
(none)` as this is expected and a result of us trying to load a non-existent
MIB.


WebAPI Usage
=============================================================================


.. sourcecode:: bash

    # start snmposter (WebAPI port: 8888).
    $ sudo snmposter -f agents.csv -w 8888

    # update mib objects.
    $ curl -v -H "Content-type: application/json" -X POST --data @/path/to/data.json \
      http://snmposter-host:8888/mib/oper/update

    # json format.
    $ cat /path/to/data.json
    {
    "127.0.1.11": [ # agent address.
    # {OID, Data Type, Object Value}
    { "oid":".1.3.6.1.2.1.1.1.0" , "type":"STRING", "value":"UPDATED DESCRIPTION." },
    { "oid":".1.3.6.1.2.1.1.3.0" , "type":"Timeticks", "value":"0" }
    ]
    }
    
    # updated?
    $ snmpget -v1 -c public 127.0.1.11 .1.3.6.1.2.1.1.1.0
    iso.3.6.1.2.1.1.1.0 = STRING: "UPDATED DESCRIPTION."

Check here for details: http://netbuffalo.doorblog.jp/archives/5133720.html
