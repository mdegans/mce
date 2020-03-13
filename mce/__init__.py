"""Top level module for Mechanical Compound Eye."""

# Copyright (c) 2020 Michael de Gans
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
import platform
import sys

__all__ = [
    'DEBUG',
    'DEEPSTREAM_BINDINGS_PATH',
    'DEEPSTREAM_BINDINGS_ROOT',
    'DEEPSTREAM_ROOT',
    'is_jetson',
    'pyds',
]

DEBUG = True  # turns on extra logging and debug code (including --verbose)

DEEPSTREAM_ROOT = '/opt/nvidia/deepstream/deepstream-4.0'
DEEPSTREAM_MODELS_ROOT = os.path.join(
    DEEPSTREAM_ROOT, 'samples', 'models')
DEEPSTREAM_BINDINGS_ROOT = os.path.join(
    DEEPSTREAM_ROOT, 'sources', 'python', 'bindings')
THIS_DIR = os.path.abspath(os.path.dirname(__file__))
PIE_CONF = os.path.join(THIS_DIR, 'pie.conf')
MODEL_BASENAME_TEMPLATE = "resnet10.caffemodel_b{batch_size}_{precision}.engine"


def is_jetson():
    """Return True if the platform is Tegra/Jetson, False otherwise."""
    # TODO: check x86_64 explicitly instead in case somebody tries
    #  to run this in mips or ppc or something
    # TODO: do further checking if aarch64 to determine whether in fact
    #  a tegra system, and if so, which one
    return True if platform.processor() == 'aarch64' else False


# set up deepstream bindings path
if is_jetson():
    DEEPSTREAM_BINDINGS_PATH = os.path.join(DEEPSTREAM_BINDINGS_ROOT, 'jetson')
else:
    DEEPSTREAM_BINDINGS_PATH = os.path.join(DEEPSTREAM_BINDINGS_ROOT, 'x86_64')
if DEBUG:
    print(
        f'DEBUG:__init__:DEEPSTREAM_BINDINGS_PATH={DEEPSTREAM_BINDINGS_PATH}')
sys.path.append(DEEPSTREAM_BINDINGS_PATH)

try:
    import gi
    gi.require_version('Gst', '1.0')
    gi.require_version('GLib', '2.0')
    from gi.repository import (
        GObject,
        Gst,
    )
except ImportError as err:
    raise ImportError(
        "gi / GObject / Gst python bindings missing. Try running: \n"
        "sudo apt install python3-gi gir1.2-gstreamer-1.0"
    ) from err


try:
    import pyds
except ImportError as err:
    raise ImportError(
        f'ERROR:Could not import pyds.so (Python DeepStream bindings). '
        f'Is it in {DEEPSTREAM_BINDINGS_PATH} ?'
    ) from err

# print sys paths
if DEBUG:
    for path in sys.path:
        print(f'DEBUG:__init__:sys.path:{path}')

import mce.bus
import mce.osd
import mce.jetdetect


def is_xavier() -> bool:
    return mce.jetdetect.name() == "Jetson-AGX" or mce.jetdetect.nickname() == "galen"

# if this is imported before Gst.init, we get cryptic error about
# "no long-name field"
# import mce.pipeline
