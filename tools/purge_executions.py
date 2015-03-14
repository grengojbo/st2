#!/usr/bin/env python
# Licensed to the StackStorm, Inc ('StackStorm') under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
A utility script that purges st2 executions older than certain
timestamp.

*** RISK RISK RISK. You will lose data. Run at your own risk. ***
"""

from datetime import datetime, timedelta
import sys

import eventlet
from oslo.config import cfg

from st2common import config
from st2common.models.db import db_setup
from st2common.models.db import db_teardown
from st2common.persistence.action import LiveAction
from st2common.persistence.execution import ActionExecution

DEFAULT_TIMEDELTA_DAYS = 2  # in days


def _monkey_patch():
    eventlet.monkey_patch(
        os=True,
        select=True,
        socket=True,
        thread=False if '--use-debugger' in sys.argv else True,
        time=True)


def do_register_cli_opts(opts, ignore_errors=False):
    for opt in opts:
        try:
            cfg.CONF.register_cli_opt(opt)
        except:
            if not ignore_errors:
                raise


def _purge_action_models(execution_db):
    liveaction_id = execution_db.liveaction['id']
    if not liveaction_id:
        print('Invalid LiveAction id. Skipping delete: %s', execution_db)
    liveaction_db = None
    try:
        liveaction_db = LiveAction.get_by_id(liveaction_id)
    except:
        print('LiveAction with id: %s not found. Skipping delete.', liveaction_id)
    try:
        ActionExecution.delete(execution_db)
    except Exception as e:
        print('Exception deleting Execution model: %s, exception: %s',
              execution_db, str(e))
    else:
        try:
            LiveAction.delete(liveaction_db)
        except Exception as e:
            print('Zombie LiveAction left in db: %s. Exception: %s',
                  liveaction_db, str(e))


def _purge_executions(timestamp=None, action_ref=None):
    if not timestamp:
        print('Specify a timestamp to purge.')
        return

    if not action_ref:
        action_ref = ''

    print('Purging executions older than timestamp: %s',
          timestamp.strftime('%Y-%m-%d %H:%M:%S.%f'))
    # XXX: Replace with fancy pantsy query based on timestamp.
    # XXX: Think about paginating this call.
    executions = ActionExecution.get_all()
    for execution_db in executions:
        if execution_db.start_timestamp < timestamp:
            if action_ref != '':
                if execution_db.liveaction['action'] == action_ref:
                    print('Deleting execution: %s ' % execution_db)
                    _purge_action_models(execution_db)
            else:
                print('Deleting execution: %s' % execution_db)
                _purge_action_models(execution_db)


def main():
    _monkey_patch()

    cli_opts = [
        cfg.StrOpt('timestamp', default=None,
                   help='Will delete data older than ' +
                   'this timestamp. (default 48 hours). ' +
                   'Example value: 2015-03-13 19:01:27.255542'),
        cfg.StrOpt('action-ref', default='',
                   help='action-ref to delete executions for.')
    ]
    do_register_cli_opts(cli_opts)
    config.parse_args()

    # Get config values
    timestamp = cfg.CONF.timestamp
    action_ref = cfg.CONF.action_ref
    username = cfg.CONF.database.username if hasattr(cfg.CONF.database, 'username') else None
    password = cfg.CONF.database.password if hasattr(cfg.CONF.database, 'password') else None

    # Connect to db.
    db_setup(cfg.CONF.database.db_name, cfg.CONF.database.host, cfg.CONF.database.port,
             username=username, password=password)

    if not timestamp:
        now = datetime.now()
        timestamp = now - timedelta(days=DEFAULT_TIMEDELTA_DAYS)
    else:
        timestamp = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S.%f')

    # Purge models.
    _purge_executions(timestamp=timestamp, action_ref=action_ref)

    # Disconnect from db.
    db_teardown()

if __name__ == '__main__':
    main()
