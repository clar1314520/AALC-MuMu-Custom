import logging
import threading
from contextlib import contextmanager

import cv2
import numpy as np
from cv2 import createCLAHE
from PIL import Image
from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
from rapidocr.utils.output import RapidOCROutput

from utils.singletonmeta import SingletonMeta

# 小区域识别用的检测短边。默认配置是 736（limit_type: min），意味着任何裁剪图都会被
# 放大到短边 736：一条 390x50 的文字条会被放大成 3 倍像素量，反而比整屏还慢。
# 只识别界面上的大号文字（楼层、卡包名）时，320 足够，实测快 3~8 倍。
SMALL_REGION_DET_LIMIT = 320


class OCR(metaclass=SingletonMeta):
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._lock = threading.RLock()
        self.engine = RapidOCR(
            params={
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.CH,
                "Det.model_type": ModelType.MOBILE,
                "Det.ocr_version": OCRVersion.PPOCRV4,
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.CH,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.ocr_version": OCRVersion.PPOCRV4,
            },
            config_path=r"assets\config\default_rapidocr.yaml",
        )

    def run(self, image: Image.Image | np.ndarray | str) -> RapidOCROutput:
        """执行OCR识别，支持Image对象、文件路径和np.ndarray对象"""
        with self._lock:
            return self._run(image)

    def run_small(self, image: Image.Image | np.ndarray | str, det_limit: int = SMALL_REGION_DET_LIMIT):
        """小区域识别：临时把检测短边调小，避免窄条/小图被放大到无谓的像素量。

        只适合识别界面上的大号文字（楼层、卡包名等）；正文级别的密集小字仍用 run()。
        """
        with self._lock, self._det_limit(det_limit):
            return self._run(image)

    @contextmanager
    def _det_limit(self, det_limit: int):
        """临时改写检测引擎的最短边，退出时还原。"""
        det = getattr(self.engine, "text_det", None)
        if det is None or not hasattr(det, "limit_side_len"):
            yield
            return
        original = det.limit_side_len
        det.limit_side_len = det_limit
        try:
            yield
        finally:
            det.limit_side_len = original

    def _run(self, image: Image.Image | np.ndarray | str) -> RapidOCROutput:
        try:
            if isinstance(image, str):
                with Image.open(image) as image_file:
                    image_array = np.array(image_file)
            elif isinstance(image, Image.Image):
                image_array = np.array(image)
            elif isinstance(image, np.ndarray):
                image_array = image
            else:
                image_array = np.array(image)

            if image_array.ndim == 2:
                img_cv_gray = image_array
            elif image_array.ndim == 3:
                channel_count = image_array.shape[2]
                if channel_count == 1:
                    img_cv_gray = image_array[:, :, 0]
                elif channel_count == 3:
                    img_cv = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)
                    img_cv_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                elif channel_count == 4:
                    img_cv = cv2.cvtColor(image_array, cv2.COLOR_RGBA2BGR)
                    img_cv_gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                else:
                    raise ValueError(f"不支持的图像通道数: {channel_count}")
            else:
                raise ValueError(f"不支持的图像维度: {image_array.ndim}")

            # 自适应均衡化(均值化后更亮)
            clahe = createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            processed_image = clahe.apply(img_cv_gray)
            results = self.engine(processed_image)
            self.log_results(results)
            return results
        except Exception as e:
            self.logger.error(e)
            return RapidOCROutput()

    def log_results(self, ocr_results: RapidOCROutput) -> None:
        """记录OCR识别记录"""
        self.logger.debug(f"OCR识别结果：{ocr_results.txts}")
