#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Unix SMB/CIFS implementation.
# Copyright (C) Anatoliy Atanasov <anatoliy.atanasov@postpath.com> 2010
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
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
#
# Usage:
#  export DC1=dc1_dns_name
#  export DC2=dc2_dns_name
#  export SUBUNITRUN=$samba4srcdir/scripting/bin/subunitrun
#  PYTHONPATH="$PYTHONPATH:$samba4srcdir/torture/drs/python" $SUBUNITRUN fsmo -U"$DOMAIN/$DC_USERNAME"%"$DC_PASSWORD"
#

import sys
import time
import os

sys.path.append("bin/python")

from samba.auth import system_session
from ldb import SCOPE_BASE
from samba.samdb import SamDB

import samba.tests

class DrsFsmoTestCase(samba.tests.TestCase):

    # RootDSE msg for DC1
    info_dc1 = None
    ldb_dc1 = None
    # RootDSE msg for DC1
    info_dc2 = None
    ldb_dc2 = None

    def setUp(self):
        super(DrsFsmoTestCase, self).setUp()

        # connect to DCs singleton
        if self.ldb_dc1 is None:
            DrsFsmoTestCase.dc1 = get_env_var("DC1")
            DrsFsmoTestCase.ldb_dc1 = connect_samdb(self.dc1)
        if self.ldb_dc2 is None:
            DrsFsmoTestCase.dc2 = get_env_var("DC2")
            DrsFsmoTestCase.ldb_dc2 = connect_samdb(self.dc2)

        # fetch rootDSEs
        if self.info_dc1 is None:
            ldb = self.ldb_dc1
            res = ldb.search(base="", expression="", scope=SCOPE_BASE, attrs=["*"])
            self.assertEquals(len(res), 1)
            DrsFsmoTestCase.info_dc1 = res[0]
        if self.info_dc2 is None:
            ldb = self.ldb_dc2
            res = ldb.search(base="", expression="", scope=SCOPE_BASE, attrs=["*"])
            self.assertEquals(len(res), 1)
            DrsFsmoTestCase.info_dc2 = res[0]

        # cache some of RootDSE props
        self.schema_dn = self.info_dc1["schemaNamingContext"][0]
        self.dsServiceName_dc1 = self.info_dc1["dsServiceName"][0]
        self.dsServiceName_dc2 = self.info_dc2["dsServiceName"][0]

        # we will need DCs DNS names for 'net fsmo' command
        self.dnsname_dc1 = self.info_dc1["dnsHostName"][0]
        self.dnsname_dc2 = self.info_dc2["dnsHostName"][0]
        pass

    def tearDown(self):
        super(DrsFsmoTestCase, self).tearDown()

    def _net_fsmo_schema_transfer(self, DC):
        # find out where is net command
        net_cmd = os.path.abspath("./bin/net")
        # make command line credentials string
        creds = samba.tests.cmdline_credentials
        cmd_line_auth = "-U%s/%s%%%s" % (creds.get_domain(),
                                         creds.get_username(), creds.get_password())
        # bin/net fsmo transfer --role=schema --host=ldap://<Dest_DC_NAME>:389
        cmd_line = "%s fsmo transfer --role=schema --host=ldap://%s:389 %s" % (net_cmd, DC,
                                                                               cmd_line_auth)
        ret = os.system(cmd_line)
        self.assertEquals(ret, 0, "Transfering schema to %s has failed!" % (DC))
        pass


    def test_SchemaMasterTransfer(self):
        """Triggers schema master transfer role from DC1 to DC2
           and vice versa so the role goes back to the original dc"""
        # dc2 gets the schema master role from dc1
        print "Testing for role transfer from %s to %s" % (self.dnsname_dc1, self.dnsname_dc2)

        self._net_fsmo_schema_transfer(DC=self.dnsname_dc2)
        # check if the role is transfered, but wait a little first so the getncchanges can pass
        time.sleep(20)
        res = self.ldb_dc2.search(self.schema_dn,
                                  scope=SCOPE_BASE, attrs=["fSMORoleOwner"])
        assert len(res) == 1
        self.schemaMaster = res[0]["fSMORoleOwner"][0]
        self.assertEquals(self.schemaMaster, self.dsServiceName_dc2,
                          "Transfering schema to %s has failed, schema master is: %s!"%(self.dsServiceName_dc2,self.schemaMaster))

        # dc1 gets back the schema master role from dc2
        print "Testing for role transfer from %s to %s" % (self.dnsname_dc2, self.dnsname_dc1)
        self._net_fsmo_schema_transfer(DC=self.dnsname_dc1)
        # check if the role is transfered
        time.sleep(20)
        res = self.ldb_dc1.search(self.schema_dn,
                                  scope=SCOPE_BASE, attrs=["fSMORoleOwner"])
        assert len(res) == 1
        self.schemaMaster = res[0]["fSMORoleOwner"][0]
        self.assertEquals(self.schemaMaster, self.dsServiceName_dc1,
                          "Transfering schema to %s has failed, schema master is %s"%(self.dsServiceName_dc1, self.schemaMaster))
        pass

########################################################################################
def get_env_var(var_name):
    if not var_name in os.environ.keys():
        raise AssertionError("Please supply %s in environment" % var_name)
    return os.environ[var_name]

def connect_samdb(samdb_url):
    ldb_options = []
    if not "://" in samdb_url:
        if os.path.isfile(samdb_url):
            samdb_url = "tdb://%s" % samdb_url
        else:
            samdb_url = "ldap://%s:389" % samdb_url
            # user 'paged_search' module when connecting remotely
            ldb_options = ["modules:paged_searches"]

    return SamDB(url=samdb_url,
                 lp=samba.tests.env_loadparm(),
                 session_info=system_session(),
                 credentials=samba.tests.cmdline_credentials,
                 options=ldb_options)


