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

from kombu import Connection
from oslo_config import cfg

from st2actions.container.base import RunnerContainer
from st2common import log as logging
from st2common.constants import action as action_constants
from st2common.exceptions.actionrunner import ActionRunnerException
from st2common.exceptions.db import StackStormDBObjectNotFoundError
from st2common.models.db.liveaction import LiveActionDB
from st2common.services import executions
from st2common.transport import consumers, liveaction
from st2common.util import action_db as action_utils
from st2common.util import system_info


LOG = logging.getLogger(__name__)

ACTIONRUNNER_WORK_Q = liveaction.get_status_management_queue(
    'st2.actionrunner.work', routing_key=action_constants.LIVEACTION_STATUS_SCHEDULED)


class ActionExecutionDispatcher(consumers.MessageHandler):
    message_type = LiveActionDB

    def __init__(self, connection, queues):
        super(ActionExecutionDispatcher, self).__init__(connection, queues)
        self.container = RunnerContainer()

    def process(self, liveaction):
        """Dispatches the LiveAction to appropriate action runner.

        LiveAction in statuses other than "scheduled" are ignored. If
        LiveAction is already canceled and result is empty, the LiveAction
        is updated with a generic exception message.

        :param liveaction: Scheduled action execution request.
        :type liveaction: ``st2common.models.db.liveaction.LiveActionDB``

        :rtype: ``dict``
        """

        if liveaction.status == action_constants.LIVEACTION_STATUS_CANCELED:
            LOG.info('%s is not executing %s (id=%s) with "%s" status.',
                     self.__class__.__name__, type(liveaction), liveaction.id, liveaction.status)
            if not liveaction.result:
                action_utils.update_liveaction_status(
                    status=liveaction.status,
                    result={'message': 'Action execution canceled by user.'},
                    liveaction_id=liveaction.id)
            return

        if liveaction.status != action_constants.LIVEACTION_STATUS_SCHEDULED:
            LOG.info('%s is not executing %s (id=%s) with "%s" status.',
                     self.__class__.__name__, type(liveaction), liveaction.id, liveaction.status)
            return

        try:
            liveaction_db = action_utils.get_liveaction_by_id(liveaction.id)
        except StackStormDBObjectNotFoundError:
            LOG.exception('Failed to find liveaction %s in the database.', liveaction.id)
            raise

        # stamp liveaction with process_info
        runner_info = system_info.get_process_info()

        # Update liveaction status to "running"
        liveaction_db = action_utils.update_liveaction_status(
            status=action_constants.LIVEACTION_STATUS_RUNNING,
            runner_info=runner_info,
            liveaction_id=liveaction_db.id)

        action_execution_db = executions.update_execution(liveaction_db)

        # Launch action
        extra = {'action_execution_db': action_execution_db, 'liveaction_db': liveaction_db}
        LOG.audit('Launching action execution.', extra=extra)

        # the extra field will not be shown in non-audit logs so temporarily log at info.
        LOG.info('Dispatched {~}action_execution: %s / {~}live_action: %s with "%s" status.',
                 action_execution_db.id, liveaction_db.id, liveaction.status)

        try:
            result = self.container.dispatch(liveaction_db)
            LOG.debug('Runner dispatch produced result: %s', result)
            if not result:
                raise ActionRunnerException('Failed to execute action.')
        except Exception as e:
            extra['error'] = str(e)
            LOG.info('Action "%s" failed: %s' % (liveaction_db.action, str(e)), extra=extra)

            liveaction_db = action_utils.update_liveaction_status(
                status=action_constants.LIVEACTION_STATUS_FAILED,
                liveaction_id=liveaction_db.id)

            raise

        return result


def get_worker():
    with Connection(cfg.CONF.messaging.url) as conn:
        return ActionExecutionDispatcher(conn, [ACTIONRUNNER_WORK_Q])
