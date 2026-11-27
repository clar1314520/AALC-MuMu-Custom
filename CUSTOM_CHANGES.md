# 自定义分支改动记录

本文件记录本仓库相对上游的所有本地改动，便于跟随上游更新时逐条确认。
上游仓库：`https://github.com/KIYI671/AhabAssistantLimbusCompany`

## 分支约定

| 分支 / tag | 用途 |
| --- | --- |
| `upstream-V1.6.2` | 本地抓取的上游发布 tag（当前基线，未改动） |
| `vendor/snapshot` | 最初到手时的 zip 快照（内容与 V1.6.2 一致，仅换行差异），仅作存档 |
| `custom/main` | 长期维护分支，所有本地改动都在这里 |

原则：

1. 一个主题一个 commit，commit message 用 `perf:` / `fix:` / `test:` / `docs:` 前缀；
2. 新逻辑尽量放新文件（`tests/unit/...` 等），减少与上游同文件冲突的面积；
3. 不对整文件执行 `ruff format`，避免无意义的重排造成大面积冲突；
4. 不使用程序内置的「检查更新」——`updater.py` 会 `shutil.rmtree("./assets/images")`
   并覆盖程序文件，会直接抹掉本地改动。更新一律走 git。

## 改动清单

### perf(automation) `0ae466a` — 截图复用基础设施

- `module/automation/automation.py`
  - `take_screenshot(gray=True, max_age=0.0)`：`max_age>0` 且最近一帧年龄不超过该值、
    色彩模式一致时直接复用，不再触发截图。默认 `0` 保持原行为，全局调用方零影响。
  - `find_regions_by_color(..., image=None)`：允许传入调用方已取到的彩色帧。

冲突风险：中。上游对 `take_screenshot` 改动较频繁，但本次是纯增量参数 + 方法开头的
一段独立分支，冲突时保留上游主体、把复用分支重新插入即可。

### perf(retry) `8e12fca` — 可选的复用近期帧

- `tasks/base/retry.py`：`retry(reuse_frame_within=0.0)`，默认行为不变。

冲突风险：低（函数签名 + 一行调用）。

### perf(event) `6323567` — 判定页单帧双路匹配

- `tasks/event/event_handling.py`
  - 判定流程由"彩色截图 + 再截一次灰度"改为同一帧派生两份灰度图：
    一份抹掉红色徽章找「极高/高/一般」，一份保留原色找「低/极低」。
  - `decision_event_handling_ocr` 的整屏 OCR 改为先只识别 `all_sinner_bbox` 区域，
    未取到等级再回退整屏。
  - 新增 `get_sinner_bbox()`（带缓存），`black_out_red` 增加越界保护。

冲突风险：中高。这是事件判定的核心函数，上游调整判定策略时会冲突。
冲突时的判据：**同一帧必须只截一次**，且红色徽章只能在"保留原色"那份里被匹配到。

### perf(mirror) `03e8e32` — 去掉重复截图与无谓固定等待

- `tasks/mirror/select_theme_pack.py`：选包循环内不再二次截图。
- `tasks/mirror/get_floor.py`：面板展开改为有界轮询（最多 3s，含 0.4s 沉降），
  每轮只取一张彩色帧，模板匹配用灰度副本、CLEAR 统计用彩色原件。
- `tasks/mirror/mirror.py`：等待卡包页就绪由 `sleep(2)` 改为有界轮询（最多 3s）；
  主循环与事件循环的 `retry` 复用近期帧。
- `tasks/mirror/reward_card.py`：无点击的空转轮次复用循环顶部帧。

有意保留的固定等待：

- `switch_theme_pack_difficulty` 的 `sleep(2)`：徽章先变、卡包列表随后整体重载，
  只轮询徽章会在列表加载完前返回，后续会读到半加载的列表。
- `select_theme_pack` 选包成功后的 `sleep(3)` 与刷新后的 `sleep(1)`：紧随其后的
  点击/OCR 依赖动画播完，且找不到比固定等待更可靠的"已播完"判据。

冲突风险：高（`mirror.py`、`select_theme_pack.py` 是上游迭代最频繁的两个文件）。

### fix(mirror) `70373d6` — 新版界面的镜牢入口识别 + 空转兜底退出

现象：程序在「Drive 界面」和「Window（角色）界面」之间每 5 秒来回点，永远进不了镜牢。

根因（与提速无关，是游戏版本更新）：Drive 界面里的镜牢入口从「一行大字
`Mirror Dungeons`」改成「两行小字 `Mirror` / `Dungeons`」，旧模板
`home/mirror_dungeons_assets.png` 在 1600x900 下只有 **0.51** 相似度，永远低于 0.8，
于是 `road_to_mir` 走到「看不到镜牢入口 → 点 Window 图标」的兜底分支，而 Window 界面上
Drive 图标仍然可见，又点回 Drive，形成死循环。两个分支都是 `continue`，会跳过循环末尾的
`loop_count` 判定，所以连兜底退出都触发不了。

- 新增 `assets/images/default/en/home/mirror_dungeons_v2_assets.png`（两条文字样式的入口按钮）。
  同一画面实测：Drive 界面 **0.99**，Window 界面 **0.48**，区分度足够。
- `MIRROR_ENTRY_ASSETS` + `mirror_entry_visible()`：新旧两份模板都试，旧版界面不受影响。
- 两个来回点的分支也计入 `loop_count`，并把兜底退出判定搬到循环开头
  （原来在末尾，被 `continue` 跳过，等于没有）。

维护提示：**游戏再改 UI 时，这张模板会第一个失效**。症状就是日志里反复出现
`home/window_assets.png ... 相似度：0.98` 与 `home/drive_assets.png ... 相似度：0.98` 交替。
补模板的方法：截一张 1600x900 的 Drive 界面，按 `assets/images` 的惯例（2560x1440 黑底画布、
内容留在原位）扣出入场按钮，存成 `default/en/home/mirror_dungeons_v2_assets.png` 即可。

冲突风险：低（只改了 `road_to_mir` 内 3 处判断，模板是新增文件）。

### perf(ocr/mirror) — 楼层 OCR 直读 + 选卡包/选饰品局部化

**楼层识别不再点齿轮**（`tasks/mirror/get_floor.py`）：

| | 旧方案 | 新方案 |
|---|---|---|
| 做法 | 点齿轮 → 等面板 → 数 CLEAR 徽章 | 直接 OCR 界面文字 |
| 地图页 | 同左 | 读左上角 `Exploring Floor N` |
| 卡包页 | 同左 | 读顶部 `SELECT FLOOR N THEME PACK` |
| 耗时 | 3~4s | ~0.7s（两次尝试都失败才算失败） |

- 解析做了容错：OCR 常把 `FLOOR` 认成 `FL0OR`、把空格吃掉
  （`SELECTFLOOR1THEMEPACK`），所以先去掉空白再匹配 `FL[0O]?[0O]R\D{0,4}(\d{1,2})`。
- 失败会重试一次（页面淡入），仍失败才回退到原来的齿轮方案，并把失败截图存到
  `logs/floor_ocr_fail_*.png`（每局最多 3 张），方便下次调 ROI。

**OCR 本身的两处浪费**：

1. `Det.limit_side_len: 736` + `limit_type: min` 意味着**任何裁剪图都会被放大到短边
   736**。一条 390x50 的楼层文字条会被放大到 1600x216，像素量反超整屏，
   实测 3.8s > 整屏 3.3s。新增 `ocr.run_small()` 把检测短边临时压到 320，
   同一区域 0.43s，识别结果不变。
2. `mirror.py` 里"拒绝饰品"的 `find_language_text` 没有裁剪区域，等于**每轮主循环
   整屏 OCR**（3.3s）——这是"选饰品时卡一下"的主因。限制到按钮区域后 0.4s。

**选卡包批量识别**（`select_theme_pack.py`）：原先每张卡各自 OCR 一次（0.8~1s/张），
改成整排一次 OCR 再按 x 坐标归属到各卡，3 张卡从 ~2.7s 降到 1.07s；某张卡完全没
分到文本时才单卡补识别。

**耗时日志**（`utils/perf.py`）：截图 / 匹配 / OCR 分阶段累计，页面处理完输出一行：

```
选卡包页 耗时分布: 截图 1.70s/2次 · OCR 0.70s/1次 · 匹配 0.42s/13次 · 合计 2.82s
```

想看得更细就把日志级别调到 DEBUG。

冲突风险：中。`automation.py` 的 `find_image_element` / `find_language_text` 是上游
高频改动点，新增参数都放在参数表末尾，合并时注意保留。

### perf(mirror) `77df7d1` — 饰品选择合并 OCR + 奖励卡空转跳过匹配

**饰品选择（acquire_ego_gift）**：原先每张卡各 OCR 两次（白棉花 + 已持有），
3 张卡就是 6 次整卡 OCR，每次 1.5~3s，日志实测这一页光识别就 14s。改成：
一次 OCR 覆盖三张卡并集 → 按横坐标归属到各卡 → 两项检查复用同一份结果；
"Select 0/1" 原先用两组关键词各识别一遍，改为识别一次。

**奖励卡（get_reward_card）**：领取后要等游戏自己的过场（实测约 2.6s，期间
`acquire_ego_gift_card` 稳定 0.56 分，然后一帧黑屏到 0.98，说明是动画而不是识别失败）。
这段等待无法消除，但空转轮次原先每轮要做 13 次模板匹配（0.34s），现在用缩略图
指纹判断"画面没变"就直接跳过整轮匹配（保存 5s 重试计时仍然生效）。

### perf(mirror) `e6bc437` — 单饰品直给页跳过饰品识别

打关后有时只送一个饰品：屏幕上一张卡 + 下方一个确认按钮，没得挑。

- `acquire_ego_gift`：只有 1 个卡框且界面**没有**"拒绝"入口 → 直接点卡 + Select，
  整页 OCR 全部跳过；**有**拒绝入口时保留白棉花判断（否则会收下本该拒绝的白棉花）
- `get_reward_card`：单饰品页（确认按钮 + 只有 1 个卡框）最优先判定，命中即确认返回，
  不再进三选一的 5 次模板匹配；只在选择态检查，后续轮次再省一次匹配
- 三选一的 5 个奖励卡模板本就是 `clam` 模式（只搜模板原位 ±30px），天然是局部匹配，
  代码里补了注释说明，避免以后误以为在全屏扫描又叠一层 ROI

注：单饰品页实际是走 `acquire_ego_gift`（主循环由饰品卡框标记触发），
`get_reward_card` 里的这段是"带 ✓ 确认按钮"的变体兜底。

### feat(tools) `3ddcf6b` — 独立模板替换小工具

`tools/template_tool.py`：列出模板与内容尺寸、从模拟器抓帧、框选替换、
自动按 2560x1440 黑底规范生成、替换前备份。零合并冲突。

### build(tools) — 模板替换工具打包成独立 exe

`tools/template_tool.py` 增加了打包后的目录定位：

- 打包后 `__file__` 在 PyInstaller 解包目录里，改用 `sys.executable`（`app_dir()`）
- 依次尝试：上次选的目录（exe 旁 `template_tool.json`）→ exe 同级 → 上一级 → 上两级 →
  cwd，以及这些目录下的常见子目录；任何一层有 `assets/images` 就采用
- 界面顶部显示当前 AALC 目录，并提供「更换 AALC 目录…」按钮（选择会被记住）
- 全都没命中时弹窗让用户选一次，不会再静默列出空列表

打包命令（单文件，带图标，无控制台）：

```bash
uv run --no-sync pyinstaller tools/template_tool.py --onefile --noconfirm --windowed \
  --name "模板替换工具" --icon "<绝对路径>/assets/logo/my_icon_256X256.ico" \
  --distpath dist_tool --workpath build_tool --specpath build_tool
```

注意：`--icon` 必须给绝对路径，相对路径会按 `--specpath` 解析导致找不到文件。

### fix(enkephalin) — 兑换开关拆分 + 修复空跑换饼

- `module/config/config_typing.py` / `assets/config/config.example.yaml`
  - `skip_enkephalin` 拆为 `skip_lunacy_exchange`（禁止狂气换体）与
    `skip_stamina_exchange`（禁止体力换饼），两者互不影响。
  - `config_version` 提升到 `1795737600`。
- `module/config/config.py`：`_old_version_cfg_upgrade` 增加迁移，旧 `skip_enkephalin`
  的值按「体力换饼」语义迁移到 `skip_stamina_exchange`，并把旧键移除。
- `tasks/base/make_enkephalin_module.py`
  - `make_enkephalin_module` 新增 `convert` 参数：`False` 时只负责打开脑啡肽面板，
    不点「全部换入」。供「禁止体力换饼但允许狂气换体」的场景使用。
  - `lunacy_to_enkephalin` 入口新增两个 guard：`times <= 0` 直接返回（修复选「不换」
    仍会开面板白跑一次换饼的 bug）、`skip_lunacy_exchange` 为真直接返回。
  - 结尾的 `make_enkephalin_module(skip=False)` 改为 `make_enkephalin_module()`，
    改为遵循设置。
- `tasks/base/script_task_scheme.py`：启动提示改为分别报告两个开关。
- `app/page_card.py` / `i18n/myapp_en.ts`：原来的「不自动兑换脑啡肽 (?)」换成两个
  独立勾选框「禁止狂气换体」「禁止体力换饼」，文案与提示都写明互不影响。

有意保留的 `skip=False`：`tasks/tools/production_module.py` 的两处调用属于工具页
「自动生产」，由用户手动触发且目的就是换饼，不受自动兑换开关约束。

冲突风险：中。`module/config/config_typing.py` 与 `config.example.yaml` 必须成对修改，
否则 `tests/test_config_schema.py` 会直接失败（这也是护栏）。合并上游时若上游加了新的
配置项或新的迁移块，注意 `_old_version_cfg_upgrade` 尾部与 `config_version` 数值。

### perf(mirror/battle) — 饰品升两级即退 / 寻路确认即点 / 盲点下一节点 / 纯P开关

- `tasks/mirror/in_shop.py`
  - `ego_gift_to_power_up(max_upgrades=2)` 重写：一件饰品最多升两级，升满立刻退出
    （原来升满后还会继续点第三次）；每级固定 `sleep(3)` 换成"确认框出现即点、确认框
    消失就点下一级"的有界轮询；每级最多点两次「升级」，避免升级动画没放完时第一次
    点击被游戏忽略。
  - 新增模块级 `_wait_click()` / `_wait_gone()`（出现即点 / 消失即返回），
    点击间隔显式压到 0.15s：全局 `mouse_action_interval` 默认 0.5s，会把
    "看到按钮立刻点"多拖半秒。
- `tasks/mirror/search_road.py`
  - 新增 `_click_enter_immediately()`：点完节点后盯「进入」按钮，出现即点，
    替换原来固定的 `sleep(1.25)` / `sleep(0.75)`（用户感知就是"点确定时犹豫一下"）。
  - `MirrorMap` 记住上一次识别到的 Bus 坐标（`_bus_position`），`enter_next_node`
    直接按规划好的方向 + 缓存坐标算出下一节点位置（盲点），省掉每步重新截图找 Bus；
    盲点未命中时立刻回退到实时定位 Bus，并把 `legend_assets` 消失视为"其实已进入"。
  - `refresh_floor` 换层时清空 Bus 坐标，防止用旧坐标盲点到错行节点。
- `tasks/battle/battle.py`：抽出 `_press_p_enter()`，新增纯P短路分支：
  `battle_pure_p` 为真时只按 P + Enter，不划技能连线、不使用 EGO/防御。
- `module/config/config_typing.py` / `assets/config/config.example.yaml`
  / `app/page_card.py` / `i18n/myapp_en.ts`：新增全局开关 `battle_pure_p`
  （镜牢页高级配置：「战斗仅按P（不划技能、不用EGO/防御）」）。

冲突风险：中。`search_road.py` 的 `enter_next_node` / `_get_next_position` 与上游
寻路策略耦合最紧，冲突时保留上游主体，再把"盲点优先 + 进入按钮轮询"两段补回；
`in_shop.py` 的 `ego_gift_to_power_up` 是独立函数，冲突时整段替换即可。
`battle_pure_p` 与 `config.example.yaml` 必须成对增删，否则 `test_config_schema.py` 失败。

### perf(mirror/shop) — 按实测耗时分布砍掉大段 OCR 与固定等待 + 全链路打点

实测（`logs/debugLog.log`，1600×900）：饰品选择页 5.5s（其中 OCR 5.0s/2 次）、
楼层奖励卡页 1.5~3s（几乎全是轮询空转）、一次商店 52s（含两件饰品的固定 sleep、
金钱 OCR 1.7s/次、刷新确认误判重试、离开商店多等 2.5s）。

- `utils/perf.py`：新增 `STAGE_WAIT`（截图节流 + 点击间隔 + 固定 sleep）与
  `STAGE_ACTION`（实际点击耗时），配合原有 截图/匹配/OCR 五项；新增 `tracked_sleep()`。
- `module/automation/automation.py`：截图节流等待、点击间隔等待、输入调用分别记账。
- `tasks/mirror/reward_card.py`：新增快路径——进页面直接「找图标选卡 → 盯 Confirm 出现即点」，
  成功时不再回主循环（原来一页要空转 6~8 轮，每轮一次 retry + 十几次匹配）；
  单饰品直给页只在"确认完卡之后"检查，不再每轮跑一次全屏多目标匹配。
- `tasks/mirror/mirror.py`：饰品选择页的 OCR 裁剪从"整张卡（含 10 行效果描述）"
  改成"卡片顶部名称带（饰品名 + Owned 徽章）"，`白棉花`/`已持有` 判断依据不变；
  各分支输出 `饰品选择页` 耗时分布；`acquire_ego_gift` 增加 60 次循环上限
  （原先异常会被 except 吞掉后无限空转）。
- `tasks/mirror/in_shop.py`
  - 金钱 OCR 改 `ocr_text_groups(..., fast_ocr=True)`（检测短边 320，原来默认 736 会把
    一小块区域放大到 1.7 秒）；
  - 买饰品：`点货架 → 等购买按钮出现（≤1.5s）→ 点购买 → 等获得确认（≤1.5s）`，
    去掉两处固定 `sleep(1)`；
  - 关键词刷新：点确认后先等确认框收起再判断是否生效（原来点完 80ms 就回看，必然误判重试）；
  - 离开商店：确认框等待里加"已回到路线图"判据，省掉超时的 2.5 秒；
  - 输出 `商店-购买` 耗时分布。
- `tasks/mirror/search_road.py`：盲点命中率按次打印（`盲点命中/未命中 … 命中率 x/y`），
  换层时汇总上一张图的命中率。

冲突风险：中。`in_shop.py` 的购买/刷新流程与上游耦合，冲突时按"等按钮出现而不是固定 sleep"
的原则重写即可；`reward_card.py` 快路径是新增函数，保留上游主体再补两段调用即可。

### perf(mirror/road) — 楼层扫描去掉 3 次重复截图与"点 Bus 白等"

v9 实跑复测（10:19–10:25）：盲点 7 次全部命中、未命中 0（抖动后坐标 894–902 / 357–363），
单步 0.60 → 0.39s。但楼层扫描 4.57 → 5.38~6.00s：拖拽少走几十像素会判定不达标、
再拖一次（+1.2s）。

- `tasks/mirror/search_road.py`
  - 扫图前改为"先进按钮是否已亮 → 直接点"，去掉"点一下 Bus 再等 0.35s"的探针
    （55 次扫描里它一次都没命中，纯白等 0.5s）。
  - 找 Bus 复用同一帧（不再为同一屏多截一次，-0.33s）；拖拽结束后沿用循环末尾
    的坐标（-0.23s）。
  - 拖拽验收窗口 y∈(675,700)→(640,725)、x<150→x<230：少走几十像素不再触发第二次拖拽。
  - `bus` 为 None 时明确告警返回，不再 `bus[0]` 抛 TypeError。
- 截图实测（用户 5 张 1600×900 原图）：Bus 模板命中位置全部精确为 **(586,330)**、
  相似度 0.98，与 `_natural_bus` 假设完全一致；M 行节点实测偏移 (+320,+18)、
  列间距 639/2≈319.5，与代码里的 (+312,+31)/312.5 相差 ~10px（节点半宽 78px，安全）。

### perf(mirror/road) — 盲点抖动 + 消除"拖拽坐标"失效导致的未命中 + 更快等进入按钮

实测（v8 实跑 22 次镜牢，`AALC_v8/logs/debugLog.log*`，1600×900）：寻路共 324 步、
418s，其中 **55 次楼层扫描占 255s（61%）**；单步 0.60s（键盘与盲点一致），
盲点未命中 9 次、每次约 2.0s。9 次未命中的点击坐标全部来自"扫图拖拽后的 Bus 位置"
（约 (70,425)），而游戏在进入节点后会把镜头拉回 Bus 的自然位置 (586,330)。

- `module/automation/automation.py`：`take_screenshot()` 补上 `min_interval` 实际生效
  （参数上一轮已加但未落到节流里）。
- `tasks/mirror/search_road.py`
  - `_jitter_position()`：盲点/回退点击坐标加 ±8（1440 基准）随机抖动，点击前再插
    0~50ms 随机静默；避免几千次重复点同一像素。
  - `_click_enter_immediately()`：改为 `take_screenshot(min_interval=0.08)` +
    `find_element(model="normal")` + `mouse_action_with_pos(interval=0.12)`；
    进"进入"按钮的轮询从被全局 0.25s 节流压着，变成 0.08s 一次。
  - 新增 `_natural_bus` / `_bus_is_natural` / `_after_enter()`：扫图时地图被拖到角落，
    拖拽后的 Bus 坐标只在"进图第一步"有效；进入节点后用规划时记下的自然位置
    `(586,330)` 继续盲点，未命中则本层放弃自然位置改回实时定位（防连撞）。
  - `search_road_from_road_map()`：记录 Bus 自然位置；"点 Bus 直接进入"探针的等待
    0.8s → 0.35s（实测 55 次扫描中从未命中）。
- 冲突风险：低。`search_road.py` 的两处改动都是新增函数/常量。

### test — 寻路相关用例更新

- `tests/unit/tasks/test_flow_speedups.py`：寻路用例改为 mock `_click_enter_immediately`，
  新增抖动范围、进入后切回自然位置、未命中后放弃自然位置、进入按钮轮询间隔四例。

### test `8ce623b` — 回归测试（新增文件，无冲突）

- `tests/unit/module/automation/test_screenshot_reuse.py`
- `tests/unit/tasks/event/test_decision_frame.py`（1600x900 合成画面）
- `tests/unit/tasks/mirror/test_get_floor.py`
- `tests/unit/tasks/base/test_enkephalin_exchange.py`（两个兑换开关与迁移）
- `tests/unit/tasks/test_flow_speedups.py`（饰品升两级即退、寻路确认即点、
  盲点下一节点与回退、纯P战斗）
- `tests/unit/tasks/test_page_speedups.py`（奖励卡快路径、饰品页只 OCR 名称带）

### 本地环境备注

- `uv sync --frozen` 在 Windows 上可能因 uv 缓存损坏报 `WinError 183`，
  改用 `uv sync --frozen --no-cache` 或 `uv pip install --no-cache` 即可。
- 仅跑测试的最小依赖：`pytest pydantic ruamel.yaml colorlog concurrent-log-handler PySide6`。
- `tests` 不依赖游戏窗口；`QT_QPA_PLATFORM=offscreen` 可避免弹窗。

### build `scripts/build_custom.py`（新增文件，无冲突）

本地定制版打包脚本，替代官方 `scripts/build.py`：

- 不压缩 7z，直接产出可运行的 `dist/AALC/` 目录；
- **不构建 `AALC Updater.exe`**：没有它，误点「检查更新」不会把定制版覆盖掉；
- 只从源码目录向产物目录单向复制，绝不回写/删除源码目录的 `config.yaml` 与 `assets`；
- `config.yaml` / `theme_pack_list.yaml` 只在产物里不存在时才复制，重复打包不会覆盖
  你在产物目录里改过的配置（需要强制同步加 `--sync-config`）。

```bash
uv run --no-sync python scripts/build_custom.py               # 完整构建（约 2~3 分钟）
uv run --no-sync python scripts/build_custom.py --post-only   # 只重做后处理
```

产物是 **onedir**（`main.spec` 里 `EXE(exclude_binaries=True)` + `COLLECT`），
`AALC.exe` 必须和 `_internal/` 放在同一目录，不能单独拷走。

## 跟随上游更新

```bash
git fetch upstream --tags
git merge upstream/main          # 或指定发布 tag，例如 git merge V1.7.0

# 合并后用自动检查兜底
python -m compileall -q module tasks utils tests
QT_QPA_PLATFORM=offscreen uv run --no-sync pytest -ra
uv run --no-sync ruff check tasks/mirror tasks/event module/automation
```

冲突热点（按概率从高到低）：

1. `tasks/mirror/mirror.py`
2. `tasks/mirror/select_theme_pack.py`
3. `tasks/event/event_handling.py`
4. `module/automation/automation.py`
5. `tasks/mirror/get_floor.py`
6. `module/config/config_typing.py` + `assets/config/config.example.yaml`（必须成对改）

处理建议：上述文件冲突时优先采用上游版本，再按本文件的改动清单逐条把本地意图补回去
（每条的意图和判据都写在上面对应小节），最后用测试与一次完整镜牢跑图确认。

## 手工验收清单

自动测试覆盖不到的部分，跑一局完整镜牢时重点看：

- 卡包页：选中的卡包关键词是否仍符合权重预期，是否出现"unknown"异常增多
- 判定页：选的罪人是否符合成功率高低，是否点空/点错位置
- 闸层：日志中「楼层识别结果」是否与实际楼层一致（重点确认没有少数 CLEAR）
- 日志耗时：`结束执行 选择镜牢主题包 耗时` 应明显低于改动前
- 兑换开关：分别勾选两项各跑一次，确认
  - 勾「禁止狂气换体」→ 日志出现「设置了禁止狂气换体」，游戏内狂气数值不变
  - 勾「禁止体力换饼」→ 日志出现「设置了禁止体力换饼」，镜牢开局不再弹脑啡肽面板
  - 狂气换体下拉框选「不换」→ 日志出现「狂气换体次数为 0」，且完全不操作面板
