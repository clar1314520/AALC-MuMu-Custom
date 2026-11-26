import re
import time
from time import sleep

import numpy as np

from module.automation import auto
from module.config import cfg
from module.logger import log

# 楼层进度条横带 ROI（1440 高度基准，内部按实际截图高度自动缩放）
FLOOR_BAND_ROI = (760, 495, 1860, 590)

# 1440p ，设置的clear图片，处理后连在一起的红色区域至少包含 300 个像素，认为匹配成功
FLOOR_CLEAR_MIN_AREA = 300

# 点击设置按钮后等待楼层面板展开的上限（秒）
FLOOR_PANEL_WAIT_TIMEOUT = 3.0

# 点击设置按钮后的沉降时间：面板淡入可能让 CLEAR 徽章颜色偏暗，过早统计会少数
FLOOR_PANEL_SETTLE = 0.4

# 楼层文字所在的区域（1440 高度基准）
#   map        : 地图页左上角 "Exploring Floor 3"
#   theme_pack : 选卡包页顶部 "SELECT FLOOR 1 THEME PACK"
FLOOR_OCR_ROI = {
    "map": (32, 128, 576, 416),
    "theme_pack": (896, 160, 1664, 480),
}

# OCR 失败时才回退的"点齿轮看 CLEAR 数量"方案
FLOOR_SETTING_ASSETS = {
    "map": "mirror/road_in_mir/setting_assets.png",
    "theme_pack": "mirror/theme_pack/theme_pack_setting_assets.png",
}
FLOOR_OCR_FALLBACK_TO_PANEL = True

# 取图时允许复用的最大帧年龄：调用方通常刚截过图，避免多等一个截图间隔
FLOOR_OCR_MAX_AGE = 0.3

# 页面淡入时标题可能还没渲染出来，失败后重试一次（重试取新帧）
FLOOR_OCR_RETRY = 2

# 失败截图最多保留几份，避免每层都写一个文件
FLOOR_OCR_DUMP_LIMIT = 3
_floor_ocr_dump_count = 0

# 容错匹配：OCR 会把 O 认成 0（"FL0OR"）、吃掉空格（"SELECTFLOOR1THEMEPACK"），
# 所以先去空白再匹配，且楼层号只认 1~2 位数字。
_FLOOR_PATTERN = re.compile(r"FL[0O]?[0O]R[D0]?\D{0,4}(\d{1,2})")


def parse_floor_text(texts) -> int:
    """从 OCR 文本里解析楼层号；识别不到返回 0。"""
    for text in texts or []:
        compact = "".join(str(text).split()).upper()
        if match := _FLOOR_PATTERN.search(compact):
            floor = int(match.group(1))
            if 1 <= floor <= 20:
                return floor
    return 0


def _scale_roi(roi):
    """1440 基准坐标 -> 当前截图坐标。"""
    scale = cfg.set_win_size / 1440
    return tuple(int(value * scale) for value in roi)


def clear_badge_mask(roi_rgb):
    """输入：RGB 图像区域，形状为（高，宽，3）。
    输出：同样宽高的 uint8 二维掩码，符合红色条件的像素为 255（白），其余为 0（黑）。
    """
    r = roi_rgb[:, :, 0].astype(np.int16)
    g = roi_rgb[:, :, 1].astype(np.int16)
    b = roi_rgb[:, :, 2].astype(np.int16)

    # 排除黄色，排除不够亮的红色
    red_dom_min, red_r_min = 60, 190
    m = ((r - np.maximum(g, b)) >= red_dom_min) & (r >= red_r_min)

    return m.astype(np.uint8) * 255


def _dump_failed_ocr(screen, roi):
    """OCR 没读出楼层时留一份截图，方便事后补模板/调 ROI。"""
    global _floor_ocr_dump_count
    if _floor_ocr_dump_count >= FLOOR_OCR_DUMP_LIMIT or auto.screenshot is None:
        return
    try:
        path = f"logs/floor_ocr_fail_{screen}_{int(time.time())}.png"
        auto.screenshot.crop(roi).save(path)
        _floor_ocr_dump_count += 1
        log.debug(f"楼层 OCR 失败截图已保存: {path}")
    except Exception as error:  # noqa: BLE001 - 诊断用，失败不影响主流程
        log.debug(f"保存楼层 OCR 失败截图出错: {error}")


def _floor_by_ocr(screen: str) -> int:
    """直接识别界面上的楼层文字，不再点齿轮。"""
    if screen not in FLOOR_OCR_ROI:
        return 0
    roi = _scale_roi(FLOOR_OCR_ROI[screen])

    # 页面淡入时标题可能还没出来，给一次重试；重试取新帧，
    # 比直接退回"点齿轮数徽章"（3~4 秒）便宜得多。
    for attempt in range(FLOOR_OCR_RETRY):
        max_age = FLOOR_OCR_MAX_AGE if attempt == 0 else 0.0
        if auto.take_screenshot(max_age=max_age) is None:
            return 0
        groups = auto.ocr_text_groups([roi])
        texts = groups[0] if groups else []
        floor = parse_floor_text(texts)
        if floor:
            log.debug(f"楼层 OCR({screen}): {texts} -> 第{floor}层")
            return floor
        log.debug(f"楼层 OCR({screen}) 第{attempt + 1}次未读出楼层: {texts}")

    _dump_failed_ocr(screen, roi)
    return 0


def _floor_by_setting(setting_assets: str) -> int:
    """兜底方案：点齿轮打开楼层进度条，数 CLEAR 徽章（较慢，仅在 OCR 失败时使用）。"""
    current_floor = 0
    setting_button = auto.find_element(setting_assets, take_screenshot=True)
    if setting_button:
        auto.mouse_action_with_pos(setting_button)
        # 面板有淡入动画，过早截图会把 CLEAR 徽章数错，先留一小段沉降再轮询。
        # 轮询每轮只取一张彩色图：模板匹配用它的灰度副本、CLEAR 统计用它的彩色原件，
        # 两者来自同一帧，既省掉一次被节流的截图，也不会把两帧状态错配。
        sleep(FLOOR_PANEL_SETTLE)
        color_frame = None
        deadline = time.monotonic() + FLOOR_PANEL_WAIT_TIMEOUT
        while True:
            if auto.take_screenshot(gray=False) is None:
                break
            frame = np.array(auto.screenshot)
            auto.screenshot = auto.screenshot.convert("L")
            if auto.find_element("mirror/road_in_mir/to_window_assets.png", threshold=0.75):
                color_frame = frame
                break
            if time.monotonic() >= deadline:
                log.debug(f"等待楼层设置面板超时({FLOOR_PANEL_WAIT_TIMEOUT}s)")
                break
        if color_frame is not None:
            clear_regions = auto.find_regions_by_color(
                FLOOR_BAND_ROI,
                min_area=FLOOR_CLEAR_MIN_AREA,
                min_dist=80,
                mask_fn=clear_badge_mask,
                image=color_frame,
            )
            if clear_regions is not None:
                current_floor = len(clear_regions) + 1
        auto.mouse_click_blank()
        sleep(1)  # 等待设置窗口关闭
    return current_floor


def get_floor(previous_floor=0, screen="map") -> int:
    """识别当前楼层；失败时记录错误并返回 0，表示楼层未知。

    Args:
        previous_floor: 上一层楼层号，仅用于异常提示
        screen: "map"（地图页）或 "theme_pack"（选卡包页），决定 OCR 区域
    """
    current_floor = _floor_by_ocr(screen)
    if current_floor == 0 and FLOOR_OCR_FALLBACK_TO_PANEL:
        log.info("楼层 OCR 未读出楼层，回退到设置面板方式（较慢）")
        current_floor = _floor_by_setting(
            FLOOR_SETTING_ASSETS.get(screen, FLOOR_SETTING_ASSETS["map"])
        )

    if current_floor == 0:
        log.error("楼层识别异常：未能确认当前楼层，标记为 0（未知）")
        return 0

    log.info(f"楼层识别结果：当前为第{current_floor}层")
    if current_floor != previous_floor + 1:
        log.info(
            f"楼层识别异常：上一层为 {previous_floor}，预计当前为 {previous_floor + 1}，"
            f"实际识别为 {current_floor}，使用识别结果继续"
        )
    return current_floor
