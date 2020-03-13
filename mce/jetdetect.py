# Copyright 2020 Michael de Gans

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# TODO(mdegans): make this a separate proper python module with a setup.py etc.

import os
import re

__all__ = [
    'name',
    # 'model',
    'compatible_models',
    'dts_filename',
    'soc',
    'nickname',
]


def cat(filename) -> str:
    with open(filename) as f:
        return f.read().rstrip('\x00')


def name():
    return cat('/proc/device-tree/model')


# not useful because it doesn't exist on every device:
# def model():
#     return cat('/proc/device-tree/nvidia,proc-boardid')


def compatible_models():
    raw = cat('/proc/device-tree/compatible')
    return re.split(r'nvidia|\x00|,|\+', raw)[2:4]


def dts_filename(short=False):
    if short:
        return os.path.basename(dts_filename())
    return os.path.abspath(cat('/proc/device-tree/nvidia,dtsfilename'))


def soc(short=False):
    if short:
        return re.search(r'(?<=platform/)(.*)(?=kernel-dts)', dts_filename())[0].split('/')[0]
    raw = cat('/proc/device-tree/compatible')
    return re.split(r'nvidia|\x00|,|\+', raw)[9]


def nickname():
    return re.search(r'(?<=platform/)(.*)(?=kernel-dts)', dts_filename())[0].split('/')[1]


def quick_test():
    print(f'name={name()}')
    # print(f'model={model()}')
    print(f'compatible_models={compatible_models()}')
    print(f'dts_filename={dts_filename()}')
    print(f'dts_filename_short={dts_filename(short=True)}')
    print(f'soc={soc()}')
    print(f'short_soc={soc(short=True)}')
    print(f'nickname={nickname()}')


if __name__ == "__main__":
    quick_test()
