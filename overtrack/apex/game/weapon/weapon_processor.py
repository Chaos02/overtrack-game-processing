import logging
import os
import string

import cv2

from overtrack.apex import ocr
from overtrack.frame import Frame
from overtrack.processor import Processor
from overtrack.util import imageops, time_processing
from overtrack.util.logging_config import config_logger
from overtrack.util.region_extraction import ExtractionRegionsCollection
from .models import *


def _draw_weapons(debug_image: Optional[np.ndarray], weapons: Weapons) -> None:
    if debug_image is None:
        return
    cv2.putText(
        debug_image,
        f'{weapons}',
        (850, 1070),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 0, 255),
        2
    )


class WeaponProcessor(Processor):
    REGIONS = ExtractionRegionsCollection(os.path.join(os.path.dirname(__file__), '..', 'data', 'regions', '16_9.zip'))

    def eager_load(self):
        self.REGIONS.eager_load()

    @time_processing
    def process(self, frame: Frame):
        y = cv2.cvtColor(frame.image, cv2.COLOR_BGR2YUV)[:, :, 0]

        weapon_images = self.REGIONS['weapon_names'].extract(y)
        weapon_images = [255 - imageops.normalise(i) for i in weapon_images]

        # cv2.imshow(f'weapons', np.vstack(weapon_images))

        weapon_names = imageops.tesser_ocr_all(
            weapon_images,
            whitelist=string.ascii_uppercase,
            engine=imageops.tesseract_lstm,
            scale=2
        )

        clip_im = self.REGIONS['clip'].extract_one(y)
        clip_im = 255 - imageops.normalise(clip_im)
        clip = imageops.tesser_ocr(
            clip_im,
            expected_type=int,
            scale=2,
            engine=ocr.tesseract_arame,
            warn_on_fail=False
        )

        ammo_im = self.REGIONS['ammo'].extract_one(y)
        ammo_im = 255 - imageops.otsu_thresh_lb_fraction(ammo_im, 0.9)
        ammo_im = cv2.resize(
            ammo_im,
            (0, 0),
            fx=3,
            fy=3,
            interpolation=cv2.INTER_NEAREST
        )
        ammo_im = cv2.GaussianBlur(ammo_im, (0, 0), 3)
        ammo_im = cv2.erode(ammo_im, None)
        # cv2.imshow('ammo', cv2.resize(
        #     ammo_im,
        #     (0, 0),
        #     fx=3,
        #     fy=3,
        #     interpolation=cv2.INTER_NEAREST
        # ))
        ammo = imageops.tesser_ocr(
            ammo_im,
            expected_type=int,
            scale=3,
            engine=ocr.tesseract_arame,
            warn_on_fail=False
        )

        selected_weapons = [int(np.median(im)) for im in self.REGIONS['selected_weapon_tell'].extract(y)]

        frame.weapons = Weapons(
            weapon_names,
            selected_weapons=(selected_weapons[0], selected_weapons[1]),
            clip=clip,
            ammo=ammo
        )

        self.REGIONS.draw(frame.debug_image)
        _draw_weapons(
            frame.debug_image,
            frame.weapons
        )

        return frame.weapons.selected_weapons is not None


def main() -> None:
    config_logger('map_processor', logging.INFO, write_to_file=False)

    frame: Optional[Frame] = Frame.create(
        cv2.imread(
            "C:/Users/simon/workspace/overtrack_2/dev/apex_images/mpv-shot0171.png"
        ),
        0,
        True
    )
    assert frame
    WeaponProcessor().process(
        frame
    )
    print(frame)
    cv2.imshow('debug', frame.debug_image)
    cv2.waitKey(0)

    pipeline = WeaponProcessor()
    path: List[Tuple[int, int]] = []

    import glob
    for p in glob.glob('../../../../dev/apex_images/*.png') + glob.glob('../../../../dev/apex_images/**/*.png'):
        frame = Frame.create(
            cv2.resize(cv2.imread(p), (1920, 1080)),
            0,
            True
        )
        pipeline.process(frame)
        cv2.imshow('debug', frame.debug_image)
        cv2.waitKey(0)

    # source = Twitch(
    #     'https://www.twitch.tv/videos/387748639',
    #     2,
    #     keyframes_only=False,
    #     seek=ts2s('5:54:30'),
    #     debug_frames=True
    # )
    # del frame
    # while True:
    #     frame = source.get()
    #     if frame is None:
    #         break
    #
    #     if pipeline.process(frame):
    #         location = frame.location
    #         path.append(location)
    #
    #     cv2.imshow('debug', frame.debug_image)
    #
    #     print(frame.weapons)
    #
    #     # if f:
    #     #     cv2.waitKey(0)
    #     #     f = False
    #
    #     cv2.waitKey(0)


if __name__ == '__main__':
    main()
