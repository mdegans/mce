# logic and some code mostly copied from:
# https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/blob/master/apps/deepstream-test1/deepstream_test_1.py
# so credit where credit is due:
################################################################################
# Copyright (c) 2019, NVIDIA CORPORATION. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
################################################################################
import enum
import logging

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gst

logger = logging.getLogger(__name__)

from mce import pyds

from typing import (
    Dict,
    Iterator,  # like Generator, but only yields (no send/ return)
)

__all__ = [
    'frame_meta_iterator',
    'obj_meta_iterator',
    'on_buffer'
]

VEHICLE = 0
BICYCLE = 1
PERSON = 2
ROADSIGN = 3


# this iterator and the one below are identical, other than the type hints
# they iterate through a GLib.List, yielding it's elements
def frame_meta_iterator(frame_meta_list: GLib.List
                        ) -> Iterator[pyds.NvDsFrameMeta]:
    # generators catch StopIteration to stop iteration,
    while frame_meta_list is not None:
        yield pyds.glist_get_nvds_frame_meta(frame_meta_list.data)
        # a Glib.List is a doubly linked list where .data is the content
        # and 'next' and 'previous' contain to the next and previous elements
        frame_meta_list = frame_meta_list.next


def obj_meta_iterator(obj_meta_list: GLib.List
                      ) -> Iterator[pyds.NvDsObjectMeta]:
    while obj_meta_list is not None:
        yield pyds.glist_get_nvds_object_meta(obj_meta_list.data)
        obj_meta_list = obj_meta_list.next


def on_buffer(pad: Gst.Pad, info: Gst.PadProbeInfo, _: None,
              ) -> Gst.PadProbeReturn:

    gst_buffer = info.get_buffer()
    if not gst_buffer:
        raise BufferError("Could not get Gst.Buffer")

    obj_counter = {
        VEHICLE: 0,
        PERSON: 0,
        BICYCLE: 0,
        ROADSIGN: 0,
    }  # type: Dict[int, int]

    # hash returns a pointer, apparently
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))

    # (mdegans) condensed this a bit from the original to be more pythonic
    for frame_meta in frame_meta_iterator(batch_meta.frame_meta_list):
        for obj_meta in obj_meta_iterator(frame_meta.obj_meta_list):
            obj_counter[obj_meta.class_id] += 1

        # Acquiring a display meta object. The memory ownership remains in
        # the C code so downstream plugins can still access it. Otherwise
        # the garbage collector will claim it when this probe function exits.
        display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
        display_meta.num_labels = 1
        py_nvosd_text_params = display_meta.text_params[0]

        # Setting display text to be shown on screen
        # Note that the pyds module allocates a buffer for the string, and the
        # memory will not be claimed by the garbage collector.
        # Reading the display_text field here will return the C address of the
        # allocated string. Use pyds.get_string() to get the string content.
        # (this is a setter, and reading from it will only return a pointer)
        py_nvosd_text_params.display_text = \
            f"Frame={frame_meta.frame_num} " \
            f"Objects={frame_meta.num_obj_meta} " \
            f"Vehicles={obj_counter[VEHICLE]} " \
            f"People={obj_counter[PERSON]}"

        # Now set the offsets where the string should appear
        py_nvosd_text_params.x_offset = 10
        py_nvosd_text_params.y_offset = 12

        # Font , font-color and font-size
        py_nvosd_text_params.font_params.font_name = "Serif"
        py_nvosd_text_params.font_params.font_size = 10
        # set(red, green, blue, alpha); set to White
        py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

        # Text background color
        py_nvosd_text_params.set_bg_clr = 1
        # set(red, green, blue, alpha); set to Black
        py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
        # Using pyds.get_string() to get display_text as string
        pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)

    return Gst.PadProbeReturn.OK
