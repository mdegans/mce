"""This module provides a DeepStreamApp and related utilities and objects."""

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

import collections
import itertools
import logging
import math
import os
import shutil
import subprocess
import sys
import urllib.parse

try:
    import youtube_dl
except ImportError:
    youtube_dl = None

# noinspection PyPackageRequirements
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GLib', '2.0')
# noinspection PyUnresolvedReferences,PyPackageRequirements
from gi.repository import (
    Gst,
    GLib,
)

from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)


import mce

logger = logging.getLogger(__name__)

DEFAULT_SINK = 'nveglglessink' if 'DISPLAY' in os.environ else 'nvoverlaysink'

YOUTUBE_HOSTNAMES = ('www.youtube.com', 'youtu.be')

ElementDescription = collections.namedtuple(
    "ElementDescription", ('type', 'name', 'properties'))
ElementDescription.__doc__ = """
A NamedTuple class describing a Gst.Element and it's properties.

:arg type: the type of Gst.Element to create as str (eg. "filesrc")
:arg name: the unique name to give the element (eg. "src_0")
:arg properties: an ElementProperties (a kwarg dict) to use to assign properties
     to the Gst.Element
"""
# a pipeline/bin description
BinDescription = Sequence[ElementDescription]
# the properties within an ElementDescription
ElementProperties = Optional[Mapping[str, Any]]
# a Gst.Element or Gst.Pad
ElementOrPad = Union[Gst.Element, Gst.Pad]
# Signature of a bus callback
BusCallback = Callable[[Gst.Bus, Gst.Message, Any], bool]
# Signature of a pad probe callback
PadProbeCallback = Callable[
    [Gst.Pad, Gst.PadProbeInfo, Any],
    Gst.PadProbeReturn,
]

__all__ = [
    'BinDescription',
    'DeepStreamApp',
    'ElementDescription',
    'ElementOrPad',
    'GhostBin',
    'make_element',
    'make_elements',
    'link',
    'bin_to_pdf',
    'StateSetter',
]


class BinAddError(RuntimeError):
    """Error raised when adding a Gst.Element to a Gst.Bin"""


class ElementCreationError(RuntimeError):
    """Error raised creating a Gst.Element"""


class GetPadError(RuntimeError):
    """Error raised getting a Gst.Pad"""


class LinkError(RuntimeError):
    """Error raised linking a Gst.Pad or Gst.Element"""


class PipelineCreationError(RuntimeError):
    """Error creating a Gst.Pipeline"""


def bin_to_pdf(bin_: Gst.Bin, details: Gst.DebugGraphDetails, filename: str,
               ) -> Optional[str]:
    """
    Dump a Gst.Bin to pdf using 
    `Gst.debug_bin_to_dot_file <https://lazka.github.io/pgi-docs/Gst-1.0/functions.html#Gst.debug_bin_to_dot_file>`_
    and graphviz.
    Will launch the 'dot' subprocess in the background with Popen.
    Does not check whether the process completes, but a .dot is
    created in any case. Has the same arguments as 
    `Gst.debug_bin_to_dot_file <https://lazka.github.io/pgi-docs/Gst-1.0/functions.html#Gst.debug_bin_to_dot_file>`_

    :returns: the path to the created file (.dot or .pdf) or None if
              GST_DEBUG_DUMP_DOT_DIR not found in os.environ

    :arg bin_: the bin to make a .pdf visualization of
    :arg details: a Gst.DebugGraphDetails choice (see gstreamer docs)
    :arg filename: a base filename to use (not full path, with no extension)
         usually this is the name of the bin you can get with some_bin.name
    """
    if 'GST_DEBUG_DUMP_DOT_DIR' in os.environ:
        dot_dir = os.environ['GST_DEBUG_DUMP_DOT_DIR']
        dot_file = os.path.join(dot_dir, f'{filename}.dot')
        pdf_file = os.path.join(dot_dir, f'{filename}.pdf')
        logger.debug(f"writing {bin_.name} to {dot_file}")
        Gst.debug_bin_to_dot_file(bin_, details, filename)
        dot_exe = shutil.which('dot')
        if dot_exe:
            logger.debug(
                f"converting {os.path.basename(dot_file)} to "
                f"{os.path.basename(pdf_file)} in background")
            command = ('nohup', dot_exe, '-Tpdf', dot_file, f'-o{pdf_file}')
            logger.debug(
                f"running: {' '.join(command)}")
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=os.setpgrp,
            )
        else:
            logger.warning(
                f'graphviz does not appear to be installed, so cannot convert'
                f'{dot_file} to pdf. You can install graphviz with '
                f'"sudo apt install graphviz" on Linux for Tegra or Ubuntu.')
            return dot_file
        return pdf_file
    return None


def make_element(type_name: str, name: str) -> Gst.Element:
    """
    Run Gst.ElementFactory.make(type_name, name) and log to DEBUG level.

    :arg type_name: the element type to create as str (eg. "fakesink")
    :arg name: the unique name to give the element. It doesn't actually have
         to be unique, but it should (at least per Gst.Bin)

    :raises: ElementCreationError if element creation fails
    """
    logger.debug(f"creating element: {type_name} with name: {name}")
    element = Gst.ElementFactory.make(type_name, name)
    if not element:
        err = f"failed to create {type_name} with name: {name}"
        logger.error(err)
        raise ElementCreationError(err)
    return element


def make_elements(bin_description: BinDescription
                  ) -> List[Gst.Element]:
    """
    :returns: a Gst.Element for each element described in in bin_description.

    note: If an element evaluates to false (eg, None), it's addition will be
          silently skipped. See make_inference_description for why, and example
          usage of this feature.

    :arg bin_description: a BinDescription (Sequence of ElementDescription)
    """
    elements = []
    for ed in bin_description:
        if not ed:
            continue
        element = make_element(ed.type, ed.name)
        if ed.properties:
            for k, v in ed.properties.items():
                element.set_property(k, v)
        if ed.name in (e.name for e in elements):
            logger.warning(
                f"DUPLICATE ELEMENT NAME: {ed.name} "
                f"this may lead to unexpected behavior.")
        elements.append(element)
    return elements


def caps_start_with(pad: Gst.Pad, caps_str: str) -> bool:
    caps = pad.query_caps()  # type: Gst.Caps
    string = caps.to_string()  # type: str
    if string.startswith(caps_str):
        return True
    return False


def is_video_pad(pad: Gst.Pad) -> bool:
    return caps_start_with(pad, "video/x-raw")


def _link_pads(a: Gst.Pad, b: Gst.Pad):
    """
    link two Gst.Pad by doing a.link(b) but with extra logging.

    :arg a: src pad to link from
    :arg b: sink pad to link to

    :raises: LinkError if link fails
    """
    # check pads are not none
    if a is None or b is None:
        raise LinkError(f'cannot link {a} to {b} because one is None (null)')
    # try to link pads
    ret = a.link(b)
    if ret == Gst.PadLinkReturn.OK:
        logger.debug(
            f'pad link between {a.parent.name}:{a.name} and '
            f'{b.parent.name}{b.name} OK')
        return
    elif ret == Gst.PadLinkReturn.WRONG_HIERARCHY:
        # todo: handle this automatically (really, gstreamer itself should)
        #  but at least this saves some googling
        raise LinkError(
            f"could not link {a.name} to {b.name} because you need to create"
            f"ghost pads from the elements inside the bin to the bin itself."
            f"You may need to request a pad if it's not a static pad.")
    elif ret == Gst.PadLinkReturn.WAS_LINKED:
        for pad in (a, b):  # type: Gst.Pad
            if pad.is_linked():
                peer = pad.get_peer()  # type: Gst.Pad
                raise LinkError(
                    f"{pad.name} of {pad.get_parent_element().name} is already "
                    f"linked to {peer.name} of {peer.get_parent_element().name}")
    elif ret == Gst.PadLinkReturn.NOFORMAT:
        a_caps = a.get_current_caps()
        b_caps = b.get_current_caps()
        raise LinkError(
            f"could not link pads {a.name} and {b.name} because caps are "
            f"incompatible:\n"
            f"{a.name}: {a_caps.to_string() if a_caps is not None else a_caps}\n"
            f"{b.name}: {b_caps.to_string() if b_caps is not None else b_caps}"
        )
    else:
        raise LinkError(
            f"could not link {a.name} on {a.get_parent_element().name} "
            f"to {b.name} on {b.get_parent_element().name} because "
            f"pad return: {ret.value_name}")


def link(a: ElementOrPad, b: ElementOrPad):
    """
    links two Gst.Element or Gst.Pad with a.link(b) but with extra logging

    :arg a: source Gst.Element or Gst.Pad
    :arg b: sink/target Gst.Element or Gst.Pad

    :raises: LinkError if link fails
    """
    # todo: support elements with request pads
    try:
        logger.debug(
            f"linking {'pad ' if isinstance(a, Gst.Pad) else ''}{a.name} "
            f"to {'pad ' if isinstance(b, Gst.Pad) else ''}{b.name}")
    except AttributeError:
        raise LinkError(f"{a} or {b} does not seem to be an Element or Pad")
    if isinstance(a, Gst.Element) and isinstance(b, Gst.Element):
        if not a.link(b):
            raise LinkError(f"could not link {a.name} to {b.name}")
    if isinstance(a, Gst.Pad) and isinstance(b, Gst.Pad):
        _link_pads(a, b)


def auto_link(elements: Iterable[Gst.Element]):
    """
    Automatically link a *linear* Iterable of elements together (no tees or
    other branching).

    note: Won't link sometimes/request pads (for now), but link() could be
          patched to so. If you want to submit a PR, this would be a welcome
          addition. Warning: it's not an easy task, with a lot of edge cases.

    :arg elements: an Iterable of Gst.Element to link together

    :raises: LinkError if a link fails
    """
    prev = None
    for element in elements:  # type: Gst.Element
        if prev is not None:
            link(prev, element)
        prev = element


def calc_rows_and_columns(num_sources: int) -> int:
    """
    calculates rows and columns values from a number of sources
    :returns:  int(math.ceil(math.sqrt(num_sources)))
    """
    if not num_sources:
        return 1
    return int(math.ceil(math.sqrt(num_sources)))


def calc_in_scale(out_scale: Tuple[int, int], rows_and_columns: int
                  ) -> Tuple[int, int]:
    return out_scale[0] // rows_and_columns, out_scale[1] // rows_and_columns


def make_inference_description(pie_config: str,
                               sink: str = DEFAULT_SINK,
                               num_sources: int = 1,
                               out_scale: Tuple[int, int] = (1920, 1080),
                               ) -> BinDescription:
    """
    :returns: a BinDescription (Sequence of ElementDescription) describing a
    Gst.Bin to perform primary inferences. More or less equal to:

    "nvstreammux ! nvinfer ! nvvideoconvert ! nvosd ! nvegltransform (if Jetson)
    ! |sink|"

    :arg pie_config: path to a config file for the primary inference engine
         (pie). Samples are provided by Nvidia with DeepStream and in the mce
         Python library path (see pie.conf). Usually this is ~./mce/pie.conf
    :param num_sources: the number or sources in the pipeline. Will be used for
           the "batch-size" parameter of various elements.
    :param out_scale: a Tuple[width, height] for the width and height on the
           nvmultistreamtiler element. Input scaling is automatically set
           based on this and the number of sources.
    :param sink: sink element to use (eg. nveglglessink). Must support NVMM.
           (otherwise performance will suffer, so don't use some standard
           gstreamer element). If it doesn't start with "nv" it won't perform
           well, if it works at all. 'qos' and 'sync' will be set to false on
           this element automatically.
    """
    rows_and_columns = calc_rows_and_columns(num_sources)
    in_scale = calc_in_scale(out_scale, rows_and_columns)
    return (
        ElementDescription(
            'nvstreammux', 'stream-muxer', {
                'width': in_scale[0],
                'height': in_scale[1],
                'enable-padding': 1,  # maintain aspect raidou
                'batch-size': num_sources,
                # https://en.wikipedia.org/wiki/Millisecond#Examples
                # a single frame of 29.97 fps seems reasonable
                'batched-push-timeout': 33367,
                'live-source': True,
            },
        ),
        ElementDescription(
            'nvinfer', 'pie', {
                'config-file-path': pie_config,
                'model-engine-file': mce.MODEL_BASENAME_TEMPLATE.format(
                    batch_size=num_sources,
                    precision='int8' if mce.is_xavier() else 'fp16',
                ),
                'batch-size': num_sources,
            },
        ),
        ElementDescription(
            'nvvideoconvert', 'converter', None,
        ),
        ElementDescription(
            'nvmultistreamtiler', 'tiler', {
                'rows': rows_and_columns,
                'columns': rows_and_columns,
                'width': out_scale[0],
                'height': out_scale[1],
            },
        ),
        ElementDescription(
            'nvdsosd', 'osd', None,
        ),
        ElementDescription(
            'nvegltransform', 'transform', None,
        ) if mce.is_jetson() and sink == 'nveglglessink' else None,
        ElementDescription(
            sink, 'sink', {
                'sync': False,
                'qos': False,
            },
        ),
    )


def add_iterable(bin_: Gst.Bin, elements: Iterable[Gst.Element], link_=True):
    """
    Adds each Gst.Element in a supplied Iterable to a Gst.Bin and
    links them together *linearly* in supplied order, using `auto_link`_

    :arg bin_: the Gst.Bin to add the elements to
    :arg elements: an Iterable (list, tuple, generator) of Gst.Element
    :param ``link_``: whether to auto-link the elements in supplied order
           (default True)

    todo: add |ghost| parameter to run .make_ghost() if the supplied Bin is a
     GhostBin and |ghost|=True
    """
    for element in elements:
        if not bin_.add(element):
            raise BinAddError(
                f"could not add {element.name} to {bin_.name}")
    if link_:
        auto_link(elements)


class StateSetter(Gst.Pipeline):
    """a Gst.Pipeline with easier state setting"""

    def set_state(self, state: Gst.State, async_=False, timeout=10, pdf=True
                  ) -> Gst.StateChangeReturn:
        """
        .. _set_state:
        Sets the element to a given state, like it's parent method, however also
        handles some logging and does a .get_state() check if ``async_``=False

        :param state: a Gst.State to change to
        :param ``async_``: if True, and the Gst.StateChangeReturn is ASYNC, wait...
        :param timeout: seconds if ``async_`` is True and StateChangeReturn == async
        :param pdf: if True, dumps a pdf before and after state change
        :returns:
        """
        if pdf:
            bin_to_pdf(
                self, Gst.DebugGraphDetails.ALL,
                f"{self.name}.{state.value_name}.start")
        ret = super().set_state(state)
        if not ret == Gst.StateChangeReturn.ASYNC:
            if not async_:
                logger.debug(
                    f"waiting {timeout} seconds for {state.value_name}")
                self.get_state(timeout)
        elif ret == Gst.StateChangeReturn.FAILURE:
            logger.error(
                f"failed to set {self.name} state to {state.value_name}")
        if pdf:
            bin_to_pdf(
                self, Gst.DebugGraphDetails.ALL,
                f"{self.name}.{state.value_name}.end")
        return ret

    def ready(self, **kwargs) -> Gst.StateChangeReturn:
        """
        Set the pipeline to READY state.

        :param kwargs: are passed to :meth:`~set_state`
        """
        return self.set_state(Gst.State.READY, **kwargs)

    def play(self, loop_also=True, **kwargs) -> Gst.StateChangeReturn:
        """
        Set the pipeline to PLAYING state

        :param loop_also: also .run() any Glib.MainLoop at .``_loop`` if one is
               found and not .is_running()
        :param kwargs: are passed to :meth:`~set_state`
        """
        ret = self.set_state(Gst.State.PLAYING, **kwargs)
        if loop_also and hasattr(self, '_loop') and not self._loop.is_running():
            self._loop.run()
        return ret

    def pause(self, **kwargs) -> Gst.StateChangeReturn:
        """
        Set the pipeline to PAUSED state

        :param kwargs: are passed to :meth:`~set_state`
        """
        return self.set_state(Gst.State.PAUSED, **kwargs)

    def null(self, **kwargs) -> Gst.StateChangeReturn:
        """
        set the pipeline to NULL state

        :param kwargs: are passed to :meth:`~set_state`
        """
        return self.set_state(Gst.State.NULL, **kwargs)

    def quit(self, loop_also=True, **kwargs) -> Gst.StateChangeReturn:
        """
        Set the DeepStreamApp to NULL and (optionally) quits the MainLoop.

        :param loop_also: also .quit() any GLib.MainLoop  at .``_loop`` if one is
               found and .is_running().
        :param kwargs: are passed to :meth:`~set_state`
        """
        ret = self.null(**kwargs)
        if loop_also and hasattr(self, 'loop') and self._loop.is_running():
            self._loop.quit()
        return ret


class GhostBin(Gst.Bin):
    # i found "link_maybe_ghosting" in the docs after creating this so I may
    # remove this. Less code is better.
    """
    This is a Gst.Bin, but for convenience, a :meth:`~make_ghost` method is added
    to easily add ghost pads for inner unlinked pads so that the Bin itself
    may be linked like any other element.

    note: There is a *minor* performance penalty to ghosting a Pad.

    :arg name: the (hopefully unique) name to give the GhostBin
    :param bd: a BinDescription describing the GhostBin. Without this an
        empty GhostBin will be created.
    :param ``link_``: if true, auto-link the GhostBin's children in the order
        supplied in the BinDescription Iterable.
    """
    def __init__(self, name: str,
                 bd: BinDescription = None,
                 link_: bool = True):
        logger.debug(
            f"Creating {self.__class__.__name__} {name} "
            f"with {len(bd) if bd is not None else 'no'} elements"
            f"{' and linking them.' if link_ else '.'}")
        Gst.Bin.__init__(self)
        self._outer_pad_count = {
            Gst.PadDirection.SRC: 0,
            Gst.PadDirection.SINK: 0,
        }
        self.set_name(name)
        if bd:
            elements = make_elements(bd)
            if elements:
                self.add_iterable(elements, link_=link_)
        bin_to_pdf(
            self, Gst.DebugGraphDetails.ALL, f"{self.name}.__init__.complete")

    def __getitem__(self, item) -> Gst.Element:  # noqa: D105
        return self.get_by_name(item)

    def add_iterable(self, elements: Iterable[Gst.Element], link_=True):
        """
        adds an iterable of elements to self and links them if ``link_`` is truthy
        """
        # noinspection PyTypeChecker
        add_iterable(self, elements, link_=link_)

    def make_ghost(self, direction: Gst.PadDirection = None,
                   inner_pad: Optional[Gst.Pad] = None,
                   ) -> Gst.GhostPad:
        """
        Attempts to add a ghost pad (proxy) to the GhostBin from an unlinked
        pad inside the GhostBin. Either direction *or* inner_pad should be
        supplied. If both are supplied, direction will be ignored.

        :param direction: a Gst.PadDireection to to look for using
               self.find_unlinked_pad.  If inner_pad is also supplied, this is
               ignored in lieu of inner_pad.direction.
        :param inner_pad: an inner pad to ghost to the outside

        :returns: a Gst.GhostPad, already added to the GhostBin, ready to link
                  to another Gst.Element (or subclass). This may not be needed
                  if your pads are compatible and link() should just work on
                  the bin itself. eg: ghost_bin.link(some_other_element_or_bin)
        """
        if inner_pad is None and direction is None:
            raise BinAddError(
                f'need inner pad or direction to add ghost pad to '
                f'{self.__class__.__name__}')
        logger.debug(
            f"creating ghost pad for {self.__class__.__name__}: {self.name}")
        if inner_pad:
            direction = inner_pad.direction
            if inner_pad.is_linked():
                raise LinkError(
                    f"pad {inner_pad.name} is already linked")
        else:
            logger.debug(
                f"Finding unlinked {direction.value_name} pad within {self.name}.")
            # get the real pad for an unlinked element of a given direction
            inner_pad = self.find_unlinked_pad(direction)  # type: Gst.Pad
            if inner_pad is None:
                raise GetPadError(f"Unlinked pad not found. Perhaps request one?")
            else:
                logger.debug(f"Unlinked pad {inner_pad.name} found in bin {self.name}")
        if direction == Gst.PadDirection.SRC:
            outer_name = f'src_{self._outer_pad_count[direction]}'
        elif direction == Gst.PadDirection.SINK:
            outer_name = f'sink_{self._outer_pad_count[direction]}'
        else:
            raise GetPadError(
                f"invalid pad direction: {direction.value_name} requested for {self.name}")
        logger.debug(f"adding ghost pad '{outer_name}' to {self.name}")
        # create a ghost pad that can be accessed from the outside
        outer_pad = Gst.GhostPad.new(outer_name, inner_pad)
        if outer_pad is not None:
            self._outer_pad_count[direction] += 1
        else:
            raise GetPadError(
                f"could not create outer ghost pad {outer_name} "
                f"for inner pad {inner_pad.name}")
        outer_pad.set_active(True)
        if not self.add_pad(outer_pad):
            raise BinAddError(
                f"could not add pad {outer_name} to bin {self.name}")
        return outer_pad


class InferenceBin(GhostBin):
    """
    A subclass of GhostBin with the inference part of a pipeline ready to link
    like any other Element supporting NVMM on it's source and sink pads.
    """

    # class variables are only shared across classes if they are mutable
    # integers are immutable in python so they can't be used for this
    _count = itertools.count(0)

    def __init__(self, pie_config: str,
                 on_buffer: Callable = mce.osd.on_buffer,
                 **kwargs):
        """
        Create a new InferenceBin, ready to link to other Gst.Element

        :arg pie_config: primary inference config
        :param kwargs: keyword arguments passed to make_inference_description
               (see it's documentation for full available parameters)
        """
        bd = make_inference_description(pie_config=pie_config, **kwargs)
        super().__init__(f'inference_{next(self._count)}', bd=bd)

        self.stream_muxer = self['stream-muxer']
        # this is a counter for the pad number to request
        # could possibly need a lock around use in get_sink_pad
        self._pad_counter = 0
        # a counter for the number of sources added
        self._source_counter = 0

        # add on_buffer callback to osd sink pad
        osd = self.get_by_name('osd')  # tyoe: Gst.Element
        osd_sink_pad = osd.get_static_pad('sink')  # type: Gst.Pad
        if not osd_sink_pad:
            raise GetPadError("could not get nvosd sink pad")
        osd_sink_pad.add_probe(
            Gst.PadProbeType.BUFFER, on_buffer, None)

    @property
    def source_counter(self) -> int:
        return self._source_counter

    @source_counter.setter
    def source_counter(self, count: int):
        # setting these at runtime seems to only work half the time
        # rows_and_columns = calc_rows_and_columns(count)
        # out_scale = (
        #     self['tiler'].get_property('width'),
        #     self['tiler'].get_property('height'),)
        # in_scale = calc_in_scale(out_scale, rows_and_columns)
        # self['stream-muxer'].set_property('batch-size', count)
        # self['stream-muxer'].set_property('width', in_scale[0])
        # self['stream-muxer'].set_property('height', in_scale[1])
        # self['pie'].set_property('batch-size', count)
        # self['tiler'].set_property('rows', rows_and_columns)
        # self['tiler'].set_property('columns', rows_and_columns)
        self._source_counter = count

    def get_sink_pad(self) -> Gst.GhostPad:
        """
        First, try to find an unlinked sink pad, and return that if possible.
        If not, request a new sink pad from the stream-muxer, ghost it to the
        outside of the InferenceBin, and return it.

        :returns: a Gst.GhostPin, ready to be linked
        """
        logger.debug(f'finding unlinked pad on {self.name}')
        inner_pad = self.find_unlinked_pad(Gst.PadDirection.SINK)  # type:Gst.Pad
        if not inner_pad or inner_pad.parent is not self.stream_muxer:
            logger.debug(
                f'unlinked pad not found on {self.name}. '
                f'requesting new sink pad from {self.stream_muxer.name}')
            inner_pad = self.stream_muxer.get_request_pad(
                f"sink_{self._pad_counter}")
        if inner_pad:
            self._pad_counter += 1
        else:
            raise GetPadError(
                f'Could not find or request sink pad from {self.name}.muxer')
        return self.make_ghost(inner_pad=inner_pad)

    def link_source(self, source: Gst.Element, src_pad: Gst.Pad, *_):
        # TODO: test and see if pausing the pipeline is necessary
        #  (i think it is)
        logger.debug(f'linking {source.name} to {self.name} by {src_pad.name}')
        if not is_video_pad(src_pad):
            logger.debug(
                f"ignoring non-video pad from {source.name} "
                f"(CAPS: {src_pad.query_caps().to_string()})")
            return
        self.source_counter += 1
        try:
            sink_pad = self.get_sink_pad()
            link(src_pad, sink_pad)
        except Exception as _:
            self.source_counter -= 1
            logger.error(
                f"failed to link {source.name} to stream muxer:",
                exc_info=sys.exc_info(),)
            raise


def youtube_in_uris(uris: Iterable[str]) -> bool:
    """
    :returns: true if a youtube uri is in |uris|
    """
    return any(
        urllib.parse.urlparse(uri).hostname in YOUTUBE_HOSTNAMES
        for uri in uris)


def convert_uris(uris: Iterable[str], ydl: youtube_dl.YoutubeDL = None) -> Iterator[str]:
    """
    :yields: file uris for uris that are files and actual video links for
    youtube uris.

    :param uris:
    :param ydl:
    """
    # convert uris to a list, just in case it's an iterator
    _uris = list(uris)
    # if we already don't already have a YoutubeDL instance, and there is at
    # least one youtube uri, create an instance and run this iterator again with
    # it as the ydl parameter. doing it like this because creating a YouTubeDL
    # instance is costly, even on a fast system.
    if youtube_dl and not ydl and youtube_in_uris(_uris):
        with youtube_dl.YoutubeDL({'format': 'best'}) as ydl:
            for uri in convert_uris(_uris, ydl=ydl):
                yield uri
        raise StopIteration()
    for uri in uris:
        # if the uri is a filename, convert it to a file uri and yield it
        if os.path.isfile(uri):
            yield f"file://{os.path.abspath(uri)}"
            continue
        # otherwise, parse the uri and check if it's a youtube uri
        pr = urllib.parse.urlparse(uri)  # type: urllib.parse.ParseResult
        if pr.hostname in YOUTUBE_HOSTNAMES:
            if not ydl:
                # if no ydl instance, warn that youtube uris can't be parsed
                logger.warning(
                    f"{uri} looks like a youtube uri but no youtube-dl found. "
                    f"Try 'pip3 install youtube-dl'")
                continue
# https://stackoverflow.com/questions/18054500/how-to-use-youtube-dl-from-a-python-program
            # get one or more video uris using the YoutubeDL instance
            result = ydl.extract_info(uri, download=False)
            if 'entries' in result:
                # if a playlist, yield every video
                # TODO: test this, as the stackoverflow article is outdated
                for video in result['entries']:
                    if 'url' in video:
                        yield video['url']
            else:
                # not a playlist, just yield the result
                if 'title' in result:
                    logger.debug(f"Adding youtube video: {result['title']}")
                if 'url' in result:
                    logger.debug(f"youtube video uri: {result['url']}")
                    yield result['url']
            continue
        yield uri


class DeepStreamApp(StateSetter):
    """
    A Gst.Pipeline subclass with extra functionality specific to DeepStream.

    :arg pie_config: path to the primary inference config file
    :param sources: urls or filenames to add and link on __enter__
    :param loop: a GLib.MainLoop (or one will be created)
    :param bus_cb: a bus callback, (default mce.bus.on_message)
    :param on_buffer: a per-buffer callback to attach to osd element (default: mce.osd.on_buffer)
    """

    _muxer = None  # type: Gst.Element
    _inference_bin = None  # type: InferenceBin
    _source_counter = 0

    def __init__(self, pie_config,
                 sources: Iterable[str] = None,
                 loop: Optional[GLib.MainLoop] = None,
                 bus_cb: BusCallback = mce.bus.on_message,
                 on_buffer: PadProbeCallback = mce.osd.on_buffer,
                 ):
        logger.debug(f"{self.__class__.__name__}.__init__")
        Gst.Pipeline.__init__(self)
        self._pie_config = pie_config
        self._uris = list(sources) if sources else []  # type: List[str]
        self._loop = loop if loop else GLib.MainLoop()
        self._bus_cb = bus_cb
        self._on_buffer = on_buffer

    def __enter__(self):  # noqa: D105
        logger.debug(f"{self.name}.__enter__")

        # add the bus callback
        bus = self.get_bus()
        if not bus:
            logger.error("could not get bus")
        bus.add_watch(
            GLib.PRIORITY_DEFAULT,
            self._bus_cb,
            self)

        # create the inference bin, and add it to self
        self._inference_bin = InferenceBin(
            self._pie_config,
            on_buffer=self._on_buffer,
            num_sources=len(self._uris),
        )
        self.add(self._inference_bin)

        # add and link all sources
        if self._uris:
            for uri in convert_uris(self._uris):
                # noinspection PyTypeChecker
                self._add_source(uri)

        bin_to_pdf(
            self, Gst.DebugGraphDetails.ALL, f"{self.name}.__enter__.complete")
        return self

    def _on_decode_bin_child_added(self, bin_: Gst.Bin,
                                   element: Gst.Element):
        # logic borrowed from :
# https://github.com/NVIDIA-AI-IOT/deepstream_reference_apps/blob/master/runtime_source_add_delete/deepstream_test_rt_src_add_del.c
        # sets properties on the nvv4l2decoder elements so that the pipeline
        # but setting these doesn't seem to do anything
        logger.debug(f"{bin_.name} child added: {element.name}")
        if element.name.startswith('decodebin'):
            # add this callback to the sub-bin
            logger.debug(f'adding element-added callback to {element.name}')
            element.connect('element-added', self._on_decode_bin_child_added)
        elif element.name.startswith('nvv4l2decoder'):
            logger.debug(f'setting properties on decoder: {element.name}')
            element.set_property('enable-max-performance', True)
            element.set_property('bufapi-version', True)
            element.set_property('drop-frame-interval', 0)
            element.set_property('num-extra-surfaces', 0)

    def _add_source(self, uri: str):
        """
        Adds a source uridecodebin to the app and sets up a callback to link it
        to the inference bin.

        :arg uri: a uri for uridecodebin
        """
        uridecodebin = Gst.ElementFactory.make(
            'uridecodebin', f'source_{self._source_counter}')  # type: Gst.Element
        uridecodebin.set_property('uri', uri)
        uridecodebin.set_property('caps', Gst.Caps.from_string("video/x-raw(ANY)"))
        uridecodebin.set_property('expose-all-streams', False)
        uridecodebin.set_property('async-handling', True)
        uridecodebin.connect('pad-added', self._inference_bin.link_source)
        uridecodebin.connect('element-added', self._on_decode_bin_child_added)
        self.add(uridecodebin)
        self._source_counter += 1

    def __exit__(self, exc_type, exc_value, traceback):  # noqa: D105
        exc_info = None
        if exc_type is not None and exc_type is not KeyboardInterrupt:
            exc_info = sys.exc_info()
        logger.debug(f"{self.name}.__exit__", exc_info=exc_info)
        bin_to_pdf(
            self, Gst.DebugGraphDetails.ALL, f"{self.name}.__exit__.begin")
        self.quit()
        # todo: this gets called twice on an EOS exit, while not a big problem,
        #  it could be in the future if quit() becomes more complex.
        if exc_type is KeyboardInterrupt:
            logger.debug('successfully handled SIGINT')
            return True

    def __getitem__(self, item) -> Gst.Element:  # noqa: D105
        return self.get_by_name(item)

    def __iter__(self) -> Iterator[Gst.Element]:  # noqa: D105
        return self.children


if __name__ == '__main__':
    pass
