"""Lucifer, the bringer of light -- to your porch!"""

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

# this is mostly unfinished code related to turning the porch light on. It
# should be ready and hooked into the pipeline shortly. Why Lucifer? Why,
# he's the angel of light, of course. Google it.

import abc
import ctypes
import logging
import multiprocessing
import requests
import time

from typing import (
    Iterator,
    Mapping,
    Tuple,
)


DISCOVERY_URL = 'https://discovery.meethue.com/'

logger = logging.getLogger(__name__)


class ResponseError(requests.exceptions.BaseHTTPError):
    """raised on invalid status code for a response"""


class SetupError(requests.exceptions.BaseHTTPError):
    """raised on Hue setup failure"""


# so, I could use python async, but that require and even loop that probably
# won't play well with GLib's MainLoop (and I would have to use async
# everywhere) and the threading module still has the GIL problem, so, we'll use
# an actual separate process instead to avoid blocking GLib's MainLoop with
# network code.
class Morningstar(abc.ABC, multiprocessing.Process):
    """a process to control lighting"""

    def __init__(self, *args,
                 sleep=1/30,
                 log_level=logging.INFO,
                 on_quit_light_state=False,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = multiprocessing.log_to_stderr(log_level)
        self.logger.debug(f'{self.__class__.__name__}.__init__')
        self.on_quit_light_state = on_quit_light_state
        # Lock must be false to avoid blocking. RawValue would also work.
        self._on = multiprocessing.Value(ctypes.c_bool, lock=False)
        self._quit_requested = multiprocessing.Value(ctypes.c_bool, lock=False)
        self._sleep = sleep

    @property
    def on(self) -> bool:
        return self._on.value

    @on.setter
    def on(self, state: bool):
        self._on.value = state

    def quit(self):
        self.logger.debug(f'quit()')
        # make sure the light is off before stopping the main loop
        self.on = self.on_quit_light_state
        self._quit_requested.value = True

    def run(self) -> None:
        # the main loop of the process
        while not self._quit_requested.value:
            self.update()
            time.sleep(self._sleep)
        self.logger.debug('quit requested. updating one last time...')
        self.update()

    @abc.abstractmethod
    def update(self):
        """put your lighting logic here, your function should set your lights
        (or whatever) to the state of self.on"""


def check_response(response: requests.Response, expected=200,
                   ) -> requests.Response:
    if response.status_code != expected:
        raise ResponseError(
            f'got code {response.status_code} from {response.url} '
            f'(expected: {expected})')
    return response


def find_hub_ips(session=None):
    if not session:
        session = requests
    response = check_response(session.get(DISCOVERY_URL))
    data = response.json()
    for hub in data:
        if 'internalipaddress' in hub:
            yield hub['internalipaddress']
        else:
            raise ResponseError(
                f"Hue ip address not found in response from {DISCOVERY_URL}")


def register_one(ip, session=None) -> Tuple[str, str]:
    if not session:
        session = requests
    url = f'https://{ip}/api'
    payload = {
        'devicetype': 'mce_lucifer'
    }
    response = check_response(session.post(url, json=payload))
    status = response.json()[0]
    if 'error' in status:
        error = status['error']
        if error['type'] == 101:  # link button not pressed
            input(f'Press the blinking button on Hue hub at {ip} and press '
                  f'enter when done.')
            register_one(ip, session=session)
        else:
            try:
                logger.error(f"{error['type']}:{error['description']}")
            except KeyError as err:
                raise SetupError(
                    f'Got malformed error "{error}" from "{url}" with payload: '
                    f'"{payload}"'
                ) from err
    elif 'success' in status:
        try:
            username = status['success']['username']
        except KeyError as err:
            raise SetupError(
                'got success status but no username found') from err
        return ip, username


def register_all(session=None) -> Iterator[Tuple[str, str]]:
    """
    for each hub found, registers a username and yields a Tuple[ip,username]
    """
    if not session:
        session = requests
    for ip in find_hub_ips():
        yield register_one(ip, session=session)


def get_all_lights() -> Iterator[Tuple[str, str]]:
    pass


class HueHue(Morningstar):
    """a process to control lighting and hue hue hue"""

    # This is a way to discover local Hue hubs:
    # These are so as not to make a silly number of requests to the poor
    # Hue hub. If they don't change from one tick to the next, do nothing.
    _cached_on = None
    _cached_hue = None
    _cached_sat = None
    _cached_val = None
    # these are so the light is reset periodically anyway in case somebody
    # changes the light value with another app
    _update_count = 0
    _update_anyway_after = 300  # iterations of self.update()
    # a requests session to do Hue Hue stuff
    _session = None  # type: requests.Session

    def __init__(self, *args, hub=None, username=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hub = hub  # ip of the hub
        self.username = username  # wow, such authentication, much Hue Hue
        self._hue = multiprocessing.Value(ctypes.c_ushort, lock=False)
        self._sat = multiprocessing.Value(ctypes.c_ubyte, lock=False)
        self._val = multiprocessing.Value(ctypes.c_ubyte, lock=False)

    # todo: color properties, and on the superclass, since setting by rgb values
    #  is less of a headache than calculating the bong unit: 'hue'

    @property
    def hue(self):
        return self._hue.value

    @hue.setter
    def hue(self, hue: int):
        self._hue.value = hue

    @property
    def sat(self):
        return self._sat.value

    @sat.setter
    def sat(self, sat: int):
        self._sat.value = sat

    @property
    def val(self):
        return self._val.value

    @val.setter
    def val(self, val: int):
        self._val = val

    bri = val

    def _network_update(self) -> bool:
        """actually make a request to the light, wait for a response, and return
        True if successful (False on failure)"""
        self.logger.debug(f"turning light {'on' if self.on else 'off'}")
        payload = {
            'on': self.on,
            'hue': self.hue,
            'sat': self.sat,
            'bri': self.bri,
        }
        response = self._session.post(
            url=f'http://{self.hub}', json=payload)  # type: requests.Response
        if response.status_code == 200:
            update_status = response.json()[0]  # type: Mapping[str, str]
            if 'success' in update_status:
                return True
            return False
        else:
            self.logger.error(
                f'got response status code: {response.status_code}')
            return False

    def update(self):
        # TODO: consider moving this to the parent class
        self._update_count += 1
        # if the requested light state isn't the cached state or it's been
        # self._update_after_any iterations, try to change the light state
        if (self.on != self._cached_on
                or self.hue != self._cached_hue
                or self._update_count % self._update_anyway_after == 0):
            if not self._network_update():
                self.logger.error(
                    f'failed to update {self.name} light')
                return
            # if successful, store the changed state anyway
            self._cached_on = self.on
            self._cached_hue = self.hue

    def run(self) -> None:
        self.logger.debug('.run() -- starting session')
        with requests.Session() as self._session:
            self._find_hub()
            super().run()


if __name__ == '__main__':
    for hub_ip in find_hub_ips():
        print(hub_ip)
