from time import monotonic

from module.automation import auto
from module.decorator.decorator import begin_and_finish_time_log
from module.logger import log
from tasks.base.retry import retry
from utils.perf import perf

reward_card_model = {
    0: [
        "gain_starlight",
        "gain_ego",
        "gain_cost",
        "gain_cost_and_ego",
        "gain_ego_resource",
    ],
    1: [
        "gain_starlight",
        "gain_cost",
        "gain_ego",
        "gain_cost_and_ego",
        "gain_ego_resource",
    ],
    2: [
        "gain_cost",
        "gain_ego",
        "gain_cost_and_ego",
        "gain_ego_resource",
        "gain_starlight",
    ],
    3: [
        "gain_ego",
        "gain_cost",
        "gain_cost_and_ego",
        "gain_ego_resource",
        "gain_starlight",
    ],
}

_CLAIM_RETRY_DELAY = 5.0

# 饰品已获得页的确认按钮（屏幕正下方一个 ✓）
EGO_GIFT_CONFIRM = "mirror/road_in_mir/ego_gift_get_confirm_assets.png"
# 饰品卡框标记：三选一时每张卡各一个，单饰品页只有一个
EGO_GIFT_CARD_MARKER = "mirror/road_in_mir/acquire_ego_gift_card.png"


def _frame_signature(image) -> int:
    """极便宜的画面指纹：缩略图灰度总和。

    比模板匹配快两个数量级，用来判断"这一轮画面和上一轮是否完全一样"。
    画面没变时匹配结果必然相同，可以直接跳过整轮模板匹配。
    """
    thumb = image.resize((32, 18)).convert("L")
    return sum(thumb.getdata())


def _try_finish_single_gift() -> bool:
    """单饰品直给页：屏幕上孤零零一张饰品卡 + 一个确认按钮。

    这种页面没有可挑的东西，饰品名（含"已持有"）认不认识都不影响结果，
    所以只做两次便宜的模板匹配就确认走人，不进后面的饰品识别流程。

    判据：先看确认按钮（59x44，位置固定，匹配最便宜），
    再数饰品卡框标记——只有一个才算单饰品直给。
    """
    position = auto.find_element(EGO_GIFT_CONFIRM, model="clam")
    if not position:
        return False
    cards = auto.find_element(EGO_GIFT_CARD_MARKER, find_type="image_with_multiple_targets")
    if len(cards or []) != 1:
        return False
    auto.mouse_click(position[0], position[1])
    log.debug("单饰品直给页：直接确认，跳过饰品识别与三选一匹配")
    return True


def _select_reward_card(reward_card: list[str]) -> bool:
    """按优先度点一张奖励卡。

    只做模板匹配（图标模板，clam 模式只搜原位 ±30px），不认任何文字：
    奖励卡上唯一的区别就是那个图标，罗马数字/描述文字都不影响选哪张。
    """
    for card in reward_card:
        if position := auto.find_element(f"mirror/get_reward_card/{card}.png"):
            auto.mouse_click(position[0], position[1])
            log.debug(f"奖励卡：选择 {card}")
            return True
    return False


def _confirm_reward_card(timeout: float = 1.5) -> bool:
    """选完卡后盯 Confirm，出现即点（不再固定等一轮循环）。"""
    deadline = monotonic() + timeout
    while True:
        if auto.click_element(
            "mirror/get_reward_card/get_reward_card_confirm_assets.png",
            threshold=0.75,
            model="clam",
            take_screenshot=True,
            interval=0.2,
        ):
            return True
        if monotonic() >= deadline:
            return False


@begin_and_finish_time_log(task_name="镜牢获取奖励卡", calculate_time=False)
# 获取奖励卡
def get_reward_card(model=0):
    loop_count = 30
    claim_retry_at = 0.0
    state = "select_reward"
    auto.model = "clam"
    reward_card = reward_card_model[model]
    last_signature = 0
    perf.reset()  # 只统计本页面，避免带上上一页的耗时

    def _finish(result: bool = True) -> bool:
        log.info(perf.report_and_reset("楼层奖励卡(轮询)"))
        return result

    # 快路径：这一页要做的只有"选一张卡 + 点 Confirm"，两步都不需要识别任何文字。
    # 原来每次都要回主循环（截图节流 + retry + 十几次匹配）再判断一次，一页下来要好几秒。
    if auto.take_screenshot() is not None:
        # 单饰品直给页（打完特殊关卡）：没有可挑的东西，点确认走人，连奖励卡模板都不匹配
        if _try_finish_single_gift():
            log.info(perf.report_and_reset("楼层奖励卡(单饰品)"))
            return True
        if _select_reward_card(reward_card):
            if _confirm_reward_card():
                log.info(perf.report_and_reset("楼层奖励卡"))
                return True
            log.debug("奖励卡确认按钮未出现，回退到轮询流程")
            state = "select_reward"

    while True:
        # 自动截图
        if auto.take_screenshot() is None:
            continue
        # 画面与上一轮完全一致时，匹配结果必然一致：跳过整轮模板匹配。
        # 但领取按钮的"重试计时"是时间驱动的，到点那一轮必须照常检查。
        signature = _frame_signature(auto.screenshot)
        if (
            signature == last_signature
            and state == "wait_result"
            and monotonic() < claim_retry_at
        ):
            log.debug("画面未变化，跳过本轮模板匹配")
            continue
        last_signature = signature
        auto.mouse_to_blank()
        # 单饰品直给页只在"确认完奖励卡之后"才出现；选择阶段就查等于每轮多跑一次
        # 全屏多目标匹配（约 0.1~0.3 秒），是这一页最没必要的开销。
        if state != "select_reward" and _try_finish_single_gift():
            return _finish()
        if auto.find_element("mirror/road_in_mir/legend_assets.png"):
            return _finish()
        if auto.click_element(EGO_GIFT_CONFIRM, model="clam"):
            log.debug("奖励卡领取后识别到EGO确认，领取流程结束")
            return _finish()
        if auto.find_element(EGO_GIFT_CARD_MARKER):
            log.debug("奖励卡领取后进入饰品选择，交回镜牢主循环处理")
            return _finish()
        if auto.click_element("mirror/get_reward_card/continue_choosing_assets.png", model="clam"):
            state = "select_reward"
            continue

        if state == "claim_reward":
            if confirm_position := auto.find_element(
                "mirror/get_reward_card/get_reward_card_confirm_assets.png",
                threshold=0.75,
                model="clam",
            ):
                auto.mouse_click(confirm_position[0], confirm_position[1])
                claim_retry_at = monotonic() + _CLAIM_RETRY_DELAY
                state = "wait_result"
                log.debug("已点击奖励卡领取按钮，等待页面切换")
                continue

        elif state == "wait_result":
            if confirm_position := auto.find_element(
                "mirror/get_reward_card/get_reward_card_confirm_assets.png",
                threshold=0.75,
                model="clam",
            ):
                if monotonic() >= claim_retry_at:
                    auto.mouse_click(confirm_position[0], confirm_position[1])
                    claim_retry_at = monotonic() + _CLAIM_RETRY_DELAY
                    log.debug("奖励卡领取按钮仍在原位置，重新点击")
                    continue

        if state == "select_reward":
            # 三选一：5 个模板都按 clam 模式匹配（只搜模板原位 ±30px），
            # 天然就是"只看中间那三张卡的位置"，不做全屏扫描，无需再套 ROI。
            select_reward = False
            for card in reward_card:
                if auto.click_element(f"mirror/get_reward_card/{card}.png"):
                    select_reward = True
                    break
            if select_reward:
                state = "claim_reward"
                continue
        # 走到这里说明本轮没有任何点击，可以复用循环顶部那一帧
        log.debug(perf.format("获取奖励卡页-本轮空转"))
        if retry(reuse_frame_within=0.2) is False:
            return _finish(False)
        loop_count -= 1
        if loop_count < 20:
            auto.model = "normal"
        if loop_count < 10:
            auto.model = "aggressive"
        if loop_count < 0:
            log.error("无法获取奖励卡")
            return _finish(False)
