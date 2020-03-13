"""
Main executable for Mechanical Compound Eye. Executed when 'mce' is run from
the command line.
"""

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
import shutil
import logging

from typing import (
    Iterable,
)

import gi
gi.require_version('Gst', '1.0')
from gi.repository import (
    GObject,
    Gst,
)

import mce

logger = logging.getLogger(__name__)

__all__ = [
    'cli_main',
    'ensure_config_path',
    'ensure_config',
    'main',
]


def ensure_config_path() -> str:
    """
    Get path to config folder at ~/.mce, creating it if necessary along with
    symlinks to necessary models in ~/.mce/models/...

    :returns: full, expanded, path of ~/.mce
    """
    home = os.path.expanduser('~')
    mce_config_dir = os.path.join(home, '.mce')
    if not os.path.exists(mce_config_dir):
        print(f'creating config dir at {mce_config_dir}')
        os.mkdir(mce_config_dir, mode=0o755)
    model_path = os.path.join(mce_config_dir, "models")
    if not os.path.exists(model_path):
        os.mkdir(model_path, 0o755)
        print(f'copying models into {model_path}')
        model_file = os.path.join(
            mce.DEEPSTREAM_MODELS_ROOT, "Primary_Detector/resnet10.caffemodel")
        proto_file = os.path.join(
            mce.DEEPSTREAM_MODELS_ROOT, "Primary_Detector/resnet10.prototxt")
        label_file_path = os.path.join(  # why not label_file?
            mce.DEEPSTREAM_MODELS_ROOT, "Primary_Detector/labels.txt")
        int8_calib_file = os.path.join(
            mce.DEEPSTREAM_MODELS_ROOT, "Primary_Detector/cal_trt.bin")
        for f in (model_file, proto_file, label_file_path, int8_calib_file):
            target = os.path.join(model_path, os.path.basename(f))
            # if it's not fixed by deepstream 5.0...
            # if os.access(f, os.W_OK):
            #     sys.stderr.write(
            #         f"WARNING: {f} is writable. This is a security risk.")
            if not os.path.exists(target):
                print(f'cpoying {f} to {target}')
                shutil.copy(f, target)
                os.chmod(target, 0o644)
    return mce_config_dir


def ensure_config() -> str:
    """
    Get path to config file at ~/.mce/pie.conf, creating it and containing
    path if necessary.

    :returns: full, expanded, path of ~/.mce/pie.conf
    """
    mce_config_dir = ensure_config_path()
    filename = os.path.join(mce_config_dir, 'pie.conf')
    if not os.path.exists(filename):
        print(f'copying pie config to {filename}')
        shutil.copy(mce.PIE_CONF, filename)
    return filename


def main(sources: Iterable[str], pie_config: str):
    """
    Main function for mce. Does not parse the command line.

    :arg sources: video streams/files to analyse
    :arg pie_config: primary inference engine config file for nvinfer element
    """
    logger.debug(f'main({sources}, {pie_config})')
    GObject.threads_init()
    logger.debug('main:GObject.threads_init() complete')
    # todo: figure out good way to mix argparse arguments in with Gst.init
    Gst.init()
    # this has to be here, because the act itself of subclassing Gst.Pipeline
    # causes a core dump if Gst.init() is not called first
    # f**king bug took me ages to find.
    import mce.pipeline

    # do the gstreamer dance, elegantly.
    with mce.pipeline.DeepStreamApp(pie_config, sources=sources) as pipeline:
        pipeline.ready()
        pipeline.play()


def cli_main(args: Iterable[str] = None):
    """
    Parse command line arguments and run main()

    :arg args: an iterable of string to pass to ap.parse_args() for testing
    """
    import argparse
    ap = argparse.ArgumentParser(
        description="Mechanical Compound Eye",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    ap.add_argument('sources', help="urls or file sources", nargs='+')
    # todo: move ensure_config since it requires an import of mce and on the
    #  the Nano this is kind of heavy and leads to a pause before arg parsing
    ap.add_argument('--config', help='primary inference config',
                    default=ensure_config())
    ap.add_argument('-v', '--verbose', help='print DEBUG log level',
                    action='store_true', default=mce.DEBUG)

    os.environ['GST_DEBUG_DUMP_DOT_DIR'] = ensure_config_path()

    args = ap.parse_args(args=args)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO)

    main(args.sources, args.config)


if __name__ == '__main__':
    cli_main()
