import logging
import os
import re
import zipfile
from typing import List, Optional, Tuple
from urllib.parse import unquote

import numpy as np

logger = logging.getLogger('MapLocations')

class MapLocations:

    def __init__(self, name: str):
        self.name = name
        self.layers: Optional[List[Tuple[str, np.ndarray]]] = None

    def _ensure_loaded(self) -> None:
        import cv2

        if self.layers is not None:
            return
        self.layers = []

        # TODO: workaround for https://github.com/Miserlou/Zappa/issues/1754
        source = os.path.join(os.path.dirname(__file__), self.name + '.zip')
        altsource = os.path.join(os.path.dirname(__file__), self.name + '._zip')
        if not os.path.exists(source) and os.path.exists(altsource):
            source = altsource

        with zipfile.ZipFile(source) as z:
            for f in z.namelist():
                if not f.startswith('L') or not f.endswith('.png'):
                    # not a layer
                    continue
                layer_props = f.rsplit('.', 1)[0].split(',')
                layer_name = unquote(re.sub(r'%00(\d\d)', r'%\1', layer_props[3]))
                if layer_name.lower() != 'background' and not layer_name.startswith('.'):
                    with z.open(f, 'r') as fobj:
                        logger.debug(f'Loading location {layer_name}')
                        layer = cv2.imdecode(np.frombuffer(fobj.read(), dtype=np.uint8), -1)
                        mask = layer[:, :, 3] > 0
                        self.layers.append((layer_name, mask))

    def get_location_name(self, location: Tuple[int, int]) -> str:
        self._ensure_loaded()
        assert self.layers is not None
        for name, mask in self.layers:
            if mask[location[1], location[0]]:
                # logger.info(f'Resolving {location} -> {name}')
                return name
        # logger.warning(f'Unable to resolve {location}')
        return 'Unknown'

    def __getitem__(self, location: Tuple[int, int]) -> str:
        return self.get_location_name(location)


KINGS_CANYON_LOCATIONS = MapLocations('kings_canyon_locations')
WORLDS_EDGE_LOCATIONS = MapLocations('worlds_edge_locations')
