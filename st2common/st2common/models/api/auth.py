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

from oslo_config import cfg
from st2common.util import isotime
from st2common.models.api.base import BaseAPI
from st2common.models.db.auth import UserDB, TokenDB
from st2common import log as logging


LOG = logging.getLogger(__name__)


def get_system_username():
    return cfg.CONF.system_user.user


class UserAPI(BaseAPI):
    model = UserDB
    schema = {
        "title": "User",
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "required": True
            }
        },
        "additionalProperties": False
    }

    @classmethod
    def to_model(cls, user):
        name = user.name
        model = cls.model(name=name)
        return model


class TokenAPI(BaseAPI):
    model = TokenDB
    schema = {
        "title": "Token",
        "type": "object",
        "properties": {
            "id": {
                "type": "string"
            },
            "user": {
                "type": ["string", "null"]
            },
            "token": {
                "type": ["string", "null"]
            },
            "ttl": {
                "type": "integer",
                "minimum": 1
            },
            "expiry": {
                "type": ["string", "null"],
                "pattern": isotime.ISO8601_UTC_REGEX
            },
            "metadata": {
                "type": ["object", "null"]
            }
        },
        "additionalProperties": False
    }

    @classmethod
    def from_model(cls, model, mask_secrets=False):
        doc = super(cls, cls)._from_model(model, mask_secrets=mask_secrets)
        doc['expiry'] = isotime.format(model.expiry, offset=False) if model.expiry else None
        return cls(**doc)

    @classmethod
    def to_model(cls, instance):
        user = str(instance.user) if instance.user else None
        token = str(instance.token) if instance.token else None
        expiry = isotime.parse(instance.expiry) if instance.expiry else None

        model = cls.model(user=user, token=token, expiry=expiry)
        return model
