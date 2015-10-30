#######################################################################
#
# Copyright (C) 2010, Chet Luther <chet.luther@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#######################################################################

from twisted.internet import reactor
from twistedsnmp import agent, agentprotocol, bisectoidstore, datatypes
from twistedsnmp.pysnmpproto import v2c, rfc1902

import sys
import os
import re
import csv

# netbuffalo - for WebAPI
import threading
import tornado.web
import tornado.ioloop
from tornado.escape import json_encode

ip2faker = {}

# twistedsnmp has a bug that causes it to fail to properly convert
# Counter64 values. We workaround this by retroactively fixing datatypes
# mappings.
fixed_v2Mapping = []
for datatype, converter in datatypes.v2Mapping:
    if datatype == v2c.Counter64:
        fixed_v2Mapping.append(
            (datatype, datatypes.SimpleConverter(v2c.Counter64)))
    else:
        fixed_v2Mapping.append((datatype, converter))

datatypes.v2Mapping = fixed_v2Mapping

fixed_v1Mapping = [(rfc1902.Counter64, datatypes.SimpleConverter(v2c.Counter64))]
for datatype, converter in datatypes.v1Mapping:
    if datatype != rfc1902.Counter64:
        fixed_v1Mapping.append((datatype, converter))

datatypes.v1Mapping = fixed_v1Mapping


def sanitize_dotted(string):
    '''
    Return dotted decimal strings with non-numerics replaced with 1.

    This is necessary because some snmpwalk output files have had IP
    addresses obscured with non-numeric characters.
    '''

    return re.sub(r'[^ \.\da-fA-F]', '1', string)


class SNMPosterFactory:
    agents = []
    webport = 8888 # netbuffalo

    def configure(self, options):
        self.webport = int(options.webport)
        reader = csv.reader(open(options.filename, "rb"))
        for row in reader:
            if row[0].startswith('#'):
                continue

            self.agents.append({
                'filename': row[0],
                'ip': row[1]})

    def start(self):
        for a in self.agents:
            print "Starting %s on %s." % (a['filename'], a['ip'])
            if os.uname()[0] == 'Darwin':
                os.popen("ifconfig lo0 alias %s up" % (a['ip'],))
            elif os.uname()[0] == 'Linux':
                os.popen("/sbin/ip addr add %s dev lo" % (a['ip'],))
            else:
                print "WARNING: Unable to add loopback alias on this platform."

            faker = SNMPoster(a['ip'], a['filename'])
            ip2faker[a['ip']] = faker # netbuffalo
            faker.run()

        # netbuffalo - start tornado web server when reactor run.
        webapi = WebAPI(self.webport)
        reactor.callWhenRunning(webapi.start)

        daemonize()
        reactor.run()


class SNMPoster:
    oidData = {}
    sortedOids = []

    def __init__(self, ip, filename):
        self.ip = ip
        self.oids = {}
        self.snmp_agent = None # netbuffalo

        oid = ''
        type_ = ''
        value = []

        snmpwalk = open(filename, 'r')
        for line in snmpwalk:
            line = line.rstrip()

            match = re.search(r'^([^ ]+) = ([^\:]+):\s*(.*)$', line)
            if not match:
                match = re.search(r'^([^ ]+) = (".*")$', line)

            if match:
                if len(value) > 0:
                    self.add_oid_value(oid, type_, value)

                    oid = ''
                    type_ = ''
                    value = []

                groups = match.groups()
                if len(groups) == 3:
                    oid, type_, value1 = groups
                else:
                    oid, type_, value1 = (groups[0], 'STRING', groups[1])

                oid = sanitize_dotted(oid)

                if type_ == 'Timeticks':
                    value1 = re.search(r'^\((\d+)\) .*$', value1).groups()[0]

                value.append(value1.strip('"'))
            else:
                value.append(line.strip('"'))

        snmpwalk.close()

        if oid and type_:
            self.add_oid_value(oid, type_, value)

    def add_oid_value(self, oid, type_, value):
        if type_ == 'Counter32':
            self.oids[oid] = v2c.Counter32(self.tryIntConvert(value[0]))

        elif type_ == 'Counter64':
            self.oids[oid] = rfc1902.Counter64(long(value[0]))

        elif type_ == 'Gauge32':
            self.oids[oid] = v2c.Gauge32(self.tryIntConvert(value[0]))

        elif type_ == 'Hex-STRING':
            value = [sanitize_dotted(x) for x in value]
            self.oids[oid] = ''.join(
                [chr(int(c, 16)) for c in ' '.join(value).split(' ')])

        elif type_ == 'INTEGER':
            self.oids[oid] = self.tryIntConvert(value[0])

        elif type_ == 'IpAddress':
            value[0] = sanitize_dotted(value[0])
            self.oids[oid] = v2c.IpAddress(value[0])

        elif type_ == 'OID':
            self.oids[oid] = v2c.ObjectIdentifier(value[0])

        elif type_ == 'STRING':
            self.oids[oid] = '\n'.join(value)

        elif type_ == 'Timeticks':
            self.oids[oid] = v2c.TimeTicks(int(value[0]))

    def tryIntConvert(self, myint):
        conv = -1
        try:
            conv = int(myint)
        except:
            m = re.match(".*\((?P<myint>\d+)\).*|(?P<myint2>\d+).*", myint)
            if m:
                myint2 = m.groupdict()["myint"] or m.groupdict()["myint2"]
                try:
                    conv = int(myint2)
                except:
                    pass
        return conv

    def start(self):
        self.snmp_agent = agent.Agent(
                    dataStore=bisectoidstore.BisectOIDStore(
                        OIDs=self.oids,
                        ),
                    )
        reactor.listenUDP(
            161, agentprotocol.AgentProtocol(
                snmpVersion='v2c',
                 agent=self.snmp_agent, # netbuffalo
 #               agent=agent.Agent(
 #                   dataStore=bisectoidstore.BisectOIDStore(
 #                       OIDs=self.oids,
 #                       ),
 #                   ),
                ),
                interface=self.ip,
            )

    # netbuffalo - update mib objects
    def updateOIDs(self, variables):
        self.snmp_agent.setOIDs(variables)

    def run(self):
        reactor.callWhenRunning(self.start)


def daemonize():
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError, e:
        print >>sys.stderr, "fork #1 failed: %d (%s)" % (e.errno, e.strerror)
        sys.exit(1)

    os.chdir("/")
    os.setsid()
    os.umask(0)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError, e:
        print >>sys.stderr, "fork #2 failed: %d (%s)" % (e.errno, e.strerror)
        sys.exit(1)

class MibOperation(tornado.web.RequestHandler):

    def post(self, oper = None):

        if "Content-Type" in self.request.headers and self.request.headers['Content-Type'] == "application/json":

            if oper and oper == "update":
                data = tornado.escape.json_decode(self.request.body)

                for ip, variables in data.items():
	            faker = ip2faker[ip]
                    update_vars = []

                    for var in variables:
                        oid = var['oid']
                        str_v = var['value']
                        type_ = var['type']

                        if type_ == 'Counter32':
                            v = v2c.Counter32(int(str_v))

                        elif type_ == 'Counter64':
                            v = rfc1902.Counter64(long(str_v))

                        elif type_ == 'Gauge32':
                            v = v2c.Gauge32(int(str_v))

                        elif type_ == 'Hex-STRING':
                            value = [str_v]
                            value = [sanitize_dotted(x) for x in value]
                            v = ''.join(
                                [chr(int(c, 16)) for c in ' '.join(value).split(' ')])
                        elif type_ == 'INTEGER':
                            v = int(str_v)

                        elif type_ == 'IpAddress':
                            str_v = sanitize_dotted(str_v)
                            v = v2c.IpAddress(str_v)
               
                        elif type_ == 'OID':
                            v = v2c.ObjectIdentifier(str_v)
               
                        elif type_ == 'STRING':
                            v = '\n'.join(str_v)
               
                        elif type_ == 'Timeticks':
                            v = v2c.TimeTicks(int(str_v))

                        update_vars.append([oid, v])

	            faker.updateOIDs(update_vars)


class WebApplication(tornado.web.Application):

    def __init__(self):
        handlers = [(r"/mib/oper/?(.*)", MibOperation)]
        settings = {}
        tornado.web.Application.__init__(self, handlers, **settings)


class WebAPI(threading.Thread):

    def __init__(self, webport):
        self.port = webport
        super(WebAPI, self).__init__()

    def run(self):
        WebApplication().listen(self.port, '0.0.0.0')
        tornado.ioloop.IOLoop.instance().start()

