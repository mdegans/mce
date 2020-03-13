"""Module for bus callbacks and other bus related functionality."""
import logging

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gst

import mce

logger = logging.getLogger(__name__)

__all__ = [
    'on_message',
]


def on_message(bus: Gst.Bus,
               message: Gst.Message,
               app,
               ) -> bool:
    """Callback for handling bus messages"""
    # TAG and DURATION_CHANGED seem to be the most common
    if message.type == Gst.MessageType.TAG:
        pass
    elif message.type == Gst.MessageType.DURATION_CHANGED:
        pass
    elif message.type == Gst.MessageType.STREAM_STATUS:
        status, owner = message.parse_stream_status()  # type: Gst.StreamStatusType, Gst.Element
        logger.debug(f"{owner.name}:status:{status.value_name}")
    elif message.type == Gst.MessageType.STATE_CHANGED:
        old, new, pending = message.parse_state_changed()  # type: Gst.State, Gst.State, Gst.State
        logger.debug(
            f"{message.src.name}:state-change:"
            f"{old.value_name}->{new.value_name}")
    elif message.type == Gst.MessageType.EOS:
        logger.debug(f"Got EOS")
        app.quit()
    elif message.type == Gst.MessageType.ERROR:
        err, errmsg = message.parse_error()  # type: GLib.Error, str
        logger.error(f'{err}: {errmsg}')
        app.quit()
    elif message.type == Gst.MessageType.WARNING:
        err, errmsg = message.parse_warning()  # type: GLib.Error, str
        logger.warning(f'{err}: {errmsg}')
    else:
        if mce.DEBUG:
            logger.debug(
                f"{message.src.name}:{Gst.MessageType.get_name(message.type)}")
    return True
