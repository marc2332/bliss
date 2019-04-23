# -*- coding: utf-8 -*-
#
# This file is part of the bliss project
#
# Copyright (c) 2015-2019 Beamline Control Unit, ESRF
# Distributed under the GNU LGPLv3. See LICENSE for more info.

"""SpecReply module
This module defines the SpecReply class
"""

REPLY_ID_LIMIT = 2 ** 30
current_id = 0


def getNextReplyId():
    global current_id
    current_id = (current_id + 1) % REPLY_ID_LIMIT
    return current_id


class SpecReply:
    """SpecReply class
    Represent a reply received from a remote Spec server
    Signals:
    replyFromSpec(self) - - emitted on update
    """

    def __init__(self):
        """Constructor."""
        self.data = None
        self.error = False
        self.error_code = 0  # no error
        self.id = getNextReplyId()

        self.callback = None

    def update(self, data, error, error_code):
        """Emit the 'replyFromSpec' signal."""
        self.data = data
        self.error = error
        self.error_code = error_code

        if callable(self.callback):
            self.callback(self)

    def getValue(self):
        """Return the value of the reply object(data field)."""
        return self.data
