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

### test `8ce623b` — 回归测试（新增文件，无冲突）

- `tests/unit/module/automation/test_screenshot_reuse.py`
- `tests/unit/tasks/event/test_decision_frame.py`（1600x900 合成画面）
- `tests/unit/tasks/mirror/test_get_floor.py`
- `tests/unit/tasks/base/test_enkephalin_exchange.py`（两个兑换开关与迁移）

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
