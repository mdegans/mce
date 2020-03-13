#!/usr/bin/python3
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
# adapted from deepstream-test1 and deepstream-test3 by mdegans
# this example takes a remote or local uri as an argument and creates an rtsp
# server for the osd stuff rather than displaying it locally
################################################################################
import sys
import math
import socket

# noinspection PyPackageRequirements
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
# noinspection PyUnresolvedReferences,PyPackageRequirements
from gi.repository import (
    GObject,
    Gst,
    GstRtspServer,
)

from mce import is_jetson as is_aarch64
from mce.bus import on_message as bus_call
from mce.osd import on_buffer as osd_sink_pad_buffer_probe
from mce.__main__ import ensure_config

MAX_DISPLAY_LEN = 64
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH = 1280  # 1920
MUXER_OUTPUT_HEIGHT = 720  # 1080
MUXER_BATCH_TIMEOUT_USEC = 4000000
TILED_OUTPUT_WIDTH = 1280  # 1920
TILED_OUTPUT_HEIGHT = 720  # 1080
GST_CAPS_FEATURES_NVMM = "memory:NVMM"
pgie_classes_str = ["Vehicle", "TwoWheeler", "Person", "RoadSign"]


def cb_newpad(_, decoder_src_pad, data):
    print("In cb_newpad\n")
    caps = decoder_src_pad.get_current_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    print("gstname=", gstname)
    if gstname.find("video") != -1:
        # We do this by checking if the pad caps contain NVMM memory features.
        print("features=", features)
        if features.contains(GST_CAPS_FEATURES_NVMM):
            # Get the source bin ghost pad
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write(
                    "Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(
                "Error: Decodebin did not pick nvidia decoder plugin.\n")


def decodebin_child_added(_, obj, name, user_data):
    print("Decodebin child added:", name, "\n")
    if name.find("decodebin") != -1:
        obj.connect("child-added", decodebin_child_added, user_data)
    if is_aarch64() and name.find("nvv4l2decoder") != -1:
        print("Seting bufapi_version\n")
        obj.set_property("bufapi-version", True)


def create_source_bin(index, uri):
    print("Creating source bin")

    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name = "source-bin-%02d" % index
    print(bin_name)
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    uri_decode_bin = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri", uri)
    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target(
        "src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin


def main(args):
    # Check input arguments
    if len(args) < 2:
        sys.stderr.write("usage: %s <uri1> [uri2] ... [uriN]\n" % args[0])
        sys.exit(1)

    # Calculate the number of sources
    number_sources = len(args) - 1

    # Standard GStreamer initialization
    GObject.threads_init()
    Gst.init(None)

    # # Create gstreamer elements # #

    # Create Pipeline (Bin) element that will form container for other elements
    print("Creating Pipeline")
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write("Unable to create Pipeline")
    print("Creating streamux")

    # Create nvstreammux instance to form batches from one or more sources.
    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    if not streammux:
        sys.stderr.write(" Unable to create NvStreamMux")

    pipeline.add(streammux)
    for i in range(number_sources):
        print("Creating source_bin ", i)
        uri_name = args[i + 1]
        source_bin = create_source_bin(i, uri_name)
        if not source_bin:
            sys.stderr.write("Unable to create source bin")
        pipeline.add(source_bin)
        padname = "sink_%u" % i
        sinkpad = streammux.get_request_pad(padname)
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin")
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin")
        srcpad.link(sinkpad)
    print("Creating Pgie \n ")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    if not pgie:
        sys.stderr.write(" Unable to create pgie")
    print("Creating tiler")
    tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
    if not tiler:
        sys.stderr.write("Unable to create tiler")
    print("Creating nvvidconv")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
    if not nvvidconv:
        sys.stderr.write("Unable to create nvvidconv")
    print("Creating nvosd")

    # Create OSD to draw on the converted RGBA buffer
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    if not nvosd:
        sys.stderr.write(" Unable to create nvosd")
    nvvidconv_postosd = Gst.ElementFactory.make(
        "nvvideoconvert", "convertor_postosd")
    if not nvvidconv_postosd:
        sys.stderr.write(" Unable to create nvvidconv_postosd")

    # Create a caps filter
    caps = Gst.ElementFactory.make("capsfilter", "filter")
    caps.set_property("caps", Gst.Caps.from_string(
        f"video/x-raw({GST_CAPS_FEATURES_NVMM}), format=I420"))

    # Make the h264 encoder
    encoder = Gst.ElementFactory.make("nvv4l2h264enc", "h264-encoder")
    if not encoder:
        sys.stderr.write(" Unable to create encoder")
    encoder.set_property('bitrate', 4000000)
    if is_aarch64():
        encoder.set_property('preset-level', 1)
        encoder.set_property('insert-sps-pps', 1)
        encoder.set_property('bufapi-version', 1)

    # Make the payload-encode video into RTP packets
    rtppay = Gst.ElementFactory.make("rtph264pay", "rtppay-h264")
    if not rtppay:
        sys.stderr.write(" Unable to create rtppay")

    # Make the UDP sink
    updsink_port_num = 5400
    sink = Gst.ElementFactory.make("udpsink", "udpsink")
    if not sink:
        sys.stderr.write(" Unable to create udpsink")

    sink.set_property('host', '224.224.255.255')
    sink.set_property('port', updsink_port_num)
    sink.set_property('async', False)
    sink.set_property('sync', True)

    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', number_sources)
    streammux.set_property('live-source', True)

    pgie.set_property('config-file-path', ensure_config())
    pgie_batch_size = pgie.get_property("batch-size")
    if pgie_batch_size != number_sources:
        print("WARNING: Overriding infer-config batch-size", pgie_batch_size,
              " with number of sources ", number_sources)
        pgie.set_property("batch-size", number_sources)
    tiler_rows = int(math.sqrt(number_sources))
    tiler_columns = int(math.ceil((1.0 * number_sources) / tiler_rows))
    tiler.set_property("rows", tiler_rows)
    tiler.set_property("columns", tiler_columns)
    tiler.set_property("width", TILED_OUTPUT_WIDTH)
    tiler.set_property("height", TILED_OUTPUT_HEIGHT)

    print("Adding elements to Pipeline")
    pipeline.add(pgie)
    pipeline.add(tiler)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(nvvidconv_postosd)
    pipeline.add(caps)
    pipeline.add(encoder)
    pipeline.add(rtppay)
    pipeline.add(sink)

    print("Linking elements in the Pipeline")
    streammux.link(pgie)
    pgie.link(tiler)
    tiler.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(nvvidconv_postosd)
    nvvidconv_postosd.link(caps)
    caps.link(encoder)
    encoder.link(rtppay)
    rtppay.link(sink)

    # create an event loop and feed gstreamer bus mesages to it
    loop = GObject.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    encoder_name = "H264"
    rtsp_port_num = 8554

    server = GstRtspServer.RTSPServer.new()
    server.props.service = "%d" % rtsp_port_num
    server.attach(None)

    factory = GstRtspServer.RTSPMediaFactory.new()
    factory.set_launch(
        "( udpsrc name=pay0 port=%d buffer-size=524288 caps=\"application/x-rtp"
        ", media=video, clock-rate=90000, encoding-name=(string)%s, "
        "payload=96 \" )" % (
            updsink_port_num,
            encoder_name))
    factory.set_shared(True)
    server.get_mount_points().add_factory("/ds-test", factory)

    print(f"\n\n*** DeepStream: Launched RTSP Streaming at "
          f"rtsp://{socket.gethostname()}:{rtsp_port_num}/ds-test ***\n\n")

    osdsinkpad = nvosd.get_static_pad("sink")
    if not osdsinkpad:
        sys.stderr.write(" Unable to get sink pad of nvosd")

    osdsinkpad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # List the sources
    print("Now playing...")
    for i, source in enumerate(args):
        if i != 0:
            print(i, ": ", source)

    print("Starting pipeline")
    # start play back and listed to events
    pipeline.set_state(Gst.State.PLAYING)
    import mce.pipeline
    mce.pipeline.bin_to_pdf(pipeline, Gst.DebugGraphDetails.ALL, 'dstest1')
    try:
        loop.run()
    except KeyboardInterrupt:
        print("Got SIGINT")
    finally:
        print("Cleaning up")
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(10)


if __name__ == '__main__':
    import os
    import mce.__main__
    import logging
    logging.basicConfig(level=logging.DEBUG)
    os.environ['GST_DEBUG_DUMP_DOT_DIR'] = mce.__main__.ensure_config_path()
    sys.exit(main(sys.argv))
