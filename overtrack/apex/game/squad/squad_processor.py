import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np
from dataclasses import dataclass

from overtrack.apex import data
from overtrack.frame import Frame
from overtrack.processor import Processor
from overtrack.util import arrayops, imageops, time_processing, debugops
from overtrack.util.logging_config import config_logger
from overtrack.util.region_extraction import ExtractionRegionsCollection


@dataclass
class Squad:
    name: Optional[str]
    champion: List[float]
    squadmate_names: Tuple[Optional[str], Optional[str]]
    squadmate_champions: Tuple[List[float], List[float]]

    @property
    def champion_name(self) -> str:
        return list(data.champions.keys())[arrayops.argmax(self.champion)]

    @property
    def squadmate_champions_names(self) -> Tuple[str, str]:
        # noinspection PyTypeChecker
        return tuple(list(data.champions.keys())[arrayops.argmax(arr)] for arr in self.squadmate_champions)

    def __str__(self) -> str:
        return f'Squad(' \
               f'champion={self.champion_name}({np.argmax(self.champion):1.4f}), ' \
               f'squadmate_champions=' \
               f'{self.squadmate_champions_names[0]}({np.max(self.squadmate_champions[0])}), ' \
               f'{self.squadmate_champions_names[1]}({np.max(self.squadmate_champions[1])}))'

    __repr__ = __str__

def _draw_squad(debug_image: Optional[np.ndarray], squad: Squad) -> None:
    if debug_image is None:
        return
    for x, y, s in [
        (330, 790, f'{squad.squadmate_champions_names[0]} ({np.max(squad.squadmate_champions[0]):1.4f}) - {squad.squadmate_names[0]}'),
        (330, 860, f'{squad.squadmate_champions_names[1]} ({np.max(squad.squadmate_champions[1]):1.4f}) - {squad.squadmate_names[1]}'),
        (440, 970, f'{squad.champion_name}: ({np.max(squad.champion):1.4f}) - {squad.name}')
    ]:
        cv2.putText(
            debug_image,
            s,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 0, 255),
            2
        )


def _load_template(name: str, large: bool = False) -> Tuple[np.ndarray, np.ndarray]:
    if large:
        image = imageops.imread(os.path.join(os.path.dirname(__file__), 'data', 'champions', 'large', f'{name}.png'), -1)
    else:
        image = imageops.imread(os.path.join(os.path.dirname(__file__), 'data', 'champions', f'{name}.png'), -1)
    # image = cv2.resize(
    #     image,
    #     (0, 0),
    #     cv2.INTER_NEAREST,
    #     fx=0.55,
    #     fy=0.55
    # )
    image = image[5:-5, 5:-5]
    return image[:, :, :3], cv2.cvtColor(image[:, :, 3], cv2.COLOR_GRAY2BGR)


class SquadProcessor(Processor):
    REGIONS = ExtractionRegionsCollection(os.path.join(os.path.dirname(__file__), '..', 'data', 'regions', '16_9.zip'))
    CHAMPIONS = [
        (c, (_load_template(c, large=False), _load_template(c, large=True))) for c in data.champions.keys()
    ]
    SPEAKER_LARGE = imageops.imread(os.path.join(os.path.dirname(__file__), 'data', 'speaker_lg.png'), 0)
    SPEAKER_SMALL = imageops.imread(os.path.join(os.path.dirname(__file__), 'data', 'speaker_sm.png'), 0)

    @time_processing
    def process(self, frame: Frame):
        y = frame.image_yuv[:, :, 0]
        squadmate_names = self.REGIONS['squadmate_names'].extract(y)

        # noinspection PyTypeChecker
        frame.squad = Squad(
            name=self._ocr_playername(self.REGIONS['player_name'].extract_one(y), large=True),
            champion=self._get_template_matches(self.REGIONS['champion'].extract_one(frame.image), large=True),

            squadmate_names=(
                self._ocr_playername(squadmate_names[0], large=False),
                self._ocr_playername(squadmate_names[1], large=False)
            ),
            squadmate_champions=tuple(
                self._get_template_matches(im)
                for im
                in self.REGIONS['squadmate_champions'].extract(frame.image)
            )
        )
        frame.squad_match = round(float(np.max(frame.squad.champion)), 5)
        if frame.squad_match > 0.9:
            self.REGIONS.draw(frame.debug_image)

        _draw_squad(frame.debug_image, frame.squad)
        return np.max(frame.squad.champion) > 0.99

    def _get_template_matches(self, im: np.ndarray, large: bool = False) -> List[float]:
        matches: List[float] = []
        for name, templates in self.CHAMPIONS:
            (template, mask) = templates[large]
            match = imageops.matchTemplate(
                im,
                template,
                cv2.TM_CCORR_NORMED,
                mask=mask
            )
            matches.append(round(float(np.max(match)), 5))
        return matches

    def _ocr_playername(self, image: np.ndarray, large: bool) -> Optional[str]:
        _, thresh = cv2.threshold(image, 0, 255, cv2.THRESH_OTSU)
        # cv2.imshow('image', image)
        # cv2.imshow('thresh', thresh)
        # cv2.imwrite(os.path.join(os.path.dirname(__file__), 'data', 'champions', 'speaker_sm.png'), thresh)

        template = [self.SPEAKER_SMALL, self.SPEAKER_LARGE][large]
        mnv, mxv, mnl, mxl = cv2.minMaxLoc(cv2.matchTemplate(
            thresh,
            template,
            cv2.TM_CCORR_NORMED
        ))
        # print(mxv, mxl)
        if mxv > 0.85:
            image = image[:, :mxl[0]]
            thresh = thresh[:, :mxl[0]]

        image = 255 - cv2.bitwise_and(image, cv2.dilate(thresh, None))

        # cv2.imshow('image_crop', image)
        # debugops.test_tesser_engines(image)
        # cv2.waitKey(0)

        s = imageops.tesser_ocr(
            image,
            engine=imageops.tesseract_lstm
        )
        c = np.mean(imageops.tesseract_lstm.AllWordConfidences())
        if c < 20:
            return None
        else:
            return s


def main() -> None:
    import glob
    config_logger('map_processor', logging.INFO, write_to_file=False)

    pipeline = SquadProcessor()
    ps = ["C:/Users/simon/mpv-screenshots/mpv-shot0176.png"]
    ps += glob.glob('M:/Videos/apex/*.png')
    for p in ps:
        frame = Frame.create(
            cv2.resize(cv2.imread(p), (1920, 1080)),
            0,
            True
        )
        pipeline.process(frame)
        print(frame)
        cv2.imshow('debug', frame.debug_image)
        cv2.waitKey(0)


if __name__ == '__main__':
    main()
