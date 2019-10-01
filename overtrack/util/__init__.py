import datetime
import dataclasses
import logging
import time
from functools import wraps
import numpy as np
from typing import Callable, Tuple, TypeVar, TYPE_CHECKING

import typing

if TYPE_CHECKING:
    from overtrack.frame import Frame

logger = logging.getLogger(__name__)

BIG_NOODLE_DIGITSUBS = 'O0', 'D0', 'I1', 'L1', 'B8', 'A8', 'S5'


def round_floats(_cls=None, *, precision: int = 2):
    def wrap(cls):
        orig__post_init__ = getattr(cls, '__post_init__', None)

        def __post_init__(self, *initvars):
            if orig__post_init__:
                orig__post_init__(self, *initvars)
            for field in dataclasses.fields(cls):
                if field.type is float:
                    object.__setattr__(self, field.name, round(float(getattr(self, field.name)), precision))
                elif getattr(field.type, '__origin__', None) is typing.Tuple:
                    object.__setattr__(
                        self,
                        field.name,
                        tuple(
                            round(float(e), precision) if isinstance(e, (float, np.float, np.float16, np.float32, np.float64)) else e
                            for e in getattr(self, field.name)
                        )
                    )
                elif getattr(field.type, '__origin__', None) is typing.List:
                    object.__setattr__(
                        self,
                        field.name,
                        [
                            round(float(e), precision) if isinstance(e, (float, np.float, np.float16, np.float32, np.float64)) else e
                            for e in getattr(self, field.name)
                        ]
                    )

        setattr(cls, '__post_init__', __post_init__)
        return cls

    if _cls is None:
        return wrap
    return wrap(_cls)


def big_noodle_digitsub(s: str) -> str:
    for c1, c2 in BIG_NOODLE_DIGITSUBS:
        s = s.replace(c1, c2)
    return s


def humansize(nbytes: float, suffixes: Tuple[str, ...]=('B', 'KB', 'MB', 'GB', 'TB', 'PB')) -> str:
    # http://stackoverflow.com/a/14996816
    if nbytes == 0:
        return '0 B'
    i = 0
    while nbytes >= 1024 and i < len(suffixes) - 1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s %s' % (f, suffixes[i])


def s2ts(s: float, ms: bool=False, zpad: bool=True, sign=False) -> str:
    prepend = ''
    if s < 0:
        prepend = '-'
        s = -s
    elif sign:
        prepend = '+'

    m = s / 60
    h = m / 60
    if zpad or int(h):
        ts = '%s%02d:%02d:%02d' % (prepend, h, m % 60, s % 60)
    else:
        ts = '%s%02d:%02d' % (prepend, m % 60, s % 60)

    if ms:
        return ts + f'{s % 1 :1.3f}'[1:]
    else:
        return ts


def ms2ts(ms: float) -> str:
    return s2ts(ms / 1000)


def ts2s(ts: str) -> int:
    hs, ms, ss = ts.split(':')
    h, m, s = int(hs), int(ms), int(ss)
    m = m + 60 * h
    s = m * 60 + s
    return s


def ts2ms(ts: str) -> int:
    return ts2s(ts) * 1000


def dhms2timedelta(s: str) -> datetime.timedelta:
    td = datetime.timedelta()
    current = ''
    for c in s:
        if c.isdigit():
            current += c
        else:
            if c == 'd':
                td += datetime.timedelta(days=int(current))
            elif c == 'h':
                td += datetime.timedelta(hours=int(current))
            elif c == 'm':
                td += datetime.timedelta(minutes=int(current))
            elif c == 's':
                td += datetime.timedelta(seconds=int(current))
            else:
                raise ValueError('Unknown timedelta specifier "%s"', c)
            current = ''
    return td


T = TypeVar('T')


def time_processing(process: Callable[[T, 'Frame'], bool]) -> Callable[[T, 'Frame'], bool]:
    @wraps(process)
    def timed_process(self: T, frame: 'Frame') -> bool:
        t0 = time.time()
        result = process(self, frame)
        t1 = time.time()
        name = self.__class__.__name__
        if name in frame.timings:
            name = name + '.2'
        frame.timings[name] = (t1 - t0) * 1000
        return result
    return timed_process


def bgr2html(color: Tuple[int, int, int]) -> str:
    return '#' + ''.join(f'{c:02x}' for c in color[::-1])


def html2bgr(hex_str: str) -> Tuple[int, int, int]:
    if hex_str[0] == '#':
        hex_str = hex_str[1:]
    return int(hex_str[4:6], 16), int(hex_str[2:4], 16), int(hex_str[0:2], 16)


def test_processor(directory: str, proc, *fields: str, game='overwatch', show=True) -> None:
    import glob
    import cv2
    import os
    from pprint import pprint
    from overtrack.frame import Frame

    from overtrack.util.logging_config import config_logger

    config_logger(directory, logging.DEBUG, False)

    proc.eager_load()

    for p in glob.glob(f"C:/Users/simon/overtrack_2/{game}_images/{directory}/*.png") + \
             glob.glob(f"C:/Users/simon/overtrack_2/{game}_images/*/*.png", recursive=True):

        time.sleep(0.01)
        print('\n\n' + '-' * 32 )
        print(os.path.abspath(p))

        im = cv2.imread(p)
        im = cv2.resize(im, (1920, 1080))
        f = Frame.create(im, 0, debug=True)
        if 'game_time=' in p:
            f.game_time = float(os.path.basename(p).split('=', 1)[1].rsplit('.', 1)[0])

        proc.process(f)
        for n in fields:
            print(f.get(n))
        pprint(f.timings)
        if show:
            cv2.imshow('debug', f.debug_image)
            cv2.waitKey(0)

        print('-' * 32)
