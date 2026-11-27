# AALC-Custom

> **本项目基于 [KIYI671/AhabAssistantLimbusCompany](https://github.com/KIYI671/AhabAssistantLimbusCompany) 修改，遵循 [AGPL-3.0](./LICENSE) 协议开源。**
>
> 这是一个**个人向的性能魔改分支**，不是上游官方版本。上游的完整说明文档已保留在
> [README.upstream.md](./README.upstream.md)，功能原理、安装步骤、常见问题请优先看上游文档。

---

## ⚠️ 环境限制与注意事项（务必先读）

> **本项目是高度定制版，只在下面这一套环境下实测通过：**
>
> | 项目 | 实测环境 |
> |---|---|
> | 分辨率 | **1600 × 900**（窗口分辨率必须按游戏实际高度设置） |
> | 模拟器 | **MuMu 模拟器 12**（`simulator_type: 0`） |
> | 游戏语言 | **英文界面** |
> | 主题 | 默认主题（非暗色） |
>
> **换环境会出问题，这不是"可能"，是必然需要重新标定：**
>
> - **其他分辨率（如 1920×1080、1280×720）**：代码里所有坐标都走
>   `scale = 窗口高度 / 1440` 的比例换算，理论上能等比缩放；但**盲点寻路的落点、
>   地图拖拽验收窗口、技能栏上下两排的行高**都是我在 1600×900 上逐帧实测标出来的，
>   换高度后会出现几十像素的偏差，表现为"寻路点歪一格""技能划一半漏掉"。
>   需要按 README 里的「重新标定」步骤用探针重跑一次。
> - **中文界面**：大部分模板有 `default/zh_cn` 版本（64 个），主流程可用；
>   但**楼层的 OCR 正则只认英文**（`FLOOR`/`SELECTFLOORxTHEMEPACK`），
>   中文界面下会退回到较慢的"点开设置面板数 CLEAR 红点"方案。
> - **暗色主题**：上游只提供了 36 张 `dark/share` 模板，覆盖极不完整，基本不可用。
> - **其他模拟器 / 真机**：输入通道走 MuMu 的原生注入，换模拟器需要改
>   `module/automation/input_handlers/simulator/`，并且 `background_click` 相关行为要重测。
>
> **本项目仅供学习交流使用，遵循 AGPL-3.0，禁止用于商业用途。**
> 使用本软件可能导致的游戏账号封禁等一切后果由使用者自行承担，作者不负责。

---

## 这个分支改了什么

一句话：**在上游基础上把"每一秒都在等"的地方砍掉，并补齐战斗里的手操细节**。
完整逐条记录见 [CHANGELOG.md](./CHANGELOG.md)，这里只列最有感的几项。

### 提速（单次镜牢约省下 2~4 分钟）

| 优化 | 效果 |
|---|---|
| 截图复用 + 可调截图节流 | 同屏重复识别不再重新截图，单次识别省 1 个节流周期 |
| 镜牢主循环去掉重复截图与固定 `sleep` | 主循环每轮少 0.3~1.5s |
| 楼层直接 OCR 标题，不再点开面板数红点 | 每层省 3~6s，且不再误判楼层 |
| 选卡包 / 饰品页 OCR 只裁目标区域 | OCR 耗时从 5s 级降到 1s 级 |
| 商店按实测耗时重排（买→确认→离开全改成"等按钮出现"） | 一次商店 52s → 20s 级 |
| 寻路：盲点下一节点 + 更快等"进入"按钮 | 单步 0.60s → 0.39s |

### 战斗

- **纯 P 模式**：勾选后只按 `P + Enter`，不划技能连线、不用 EGO、不防御。
- **盲点寻路**：路线在进层时就规划好，之后每步直接用上一帧 Bus 坐标推算落点，
  不必每步重新截图找 Bus；带小幅随机抖动，避免像素级重复点击。
- **技能栏划线**：按住左侧齿轮等技能栏展开后再划（`技能栏按住时长` 可调），
  上下两排按实测行高落点，3 技能格按"吸附最近格子"定位。
- **小指良单通连续防御**：守备成功直接回车开打，不再被后续的 `P` 覆盖；
  守备回合严格优先于 3 技能。
- **饰品升两级即退**、**寻路确认即点**等细节见 CHANGELOG。

### 界面 / 配置

- 高级设置新增 **`技能栏按住时长`**（调小更快，太小会划不到）。
- 高级设置新增 **`游戏语言`**（自动识别 / 中文 / 英文）：指定后不再靠截图猜语言。
- 兑换开关拆分：**禁止狂气换体** / **禁止体力换饼** 两个独立开关。

### 工具

- `dist_tool/`：独立的**模板替换小工具**，方便换分辨率后批量替换截图模板。

---

## 快速开始

1. 下载 Release 里的压缩包，解压到**非中文路径**（例如 `D:\AALC`）。
2. 启动 MuMu 模拟器，把游戏分辨率设为 **1600×900**，语言设为**英文**。
3. 运行 `AALC.exe`，在「窗口设置」里把**窗口分辨率**选成 `1600*900`。
4. 队伍设置里按需勾选：`纯P模式`、`小指良单通·连续防御`、`优先/避免3技能`。
5. 点 `Link Start!`。

> 首次运行会检查更新并展示公告（纯离线逻辑，不收集任何数据）。

### 换了分辨率怎么重新标定

勾上探针后跑一场战斗，会自动把"当帧 + 计算出的点击点"存到 `logs/battle_probe/`：

```bash
# 在 AALC 目录下建一个空文件即可开启（删掉就是关闭）
touch logs/battle_probe.on
```

然后对照 `*_expanded.png`（按住齿轮展开后的落点）看标记是否压在技能卡上，
差多少就改 `tasks/battle/battle.py` 里 `_calculate_skills_position` 的 `y_offset`
和 `_chain_battle` 里的格距常量（160 / 145 这两个数都在 1440 基准上）。

---

## 更新会比较慢

这是个人娱乐向的魔改分支，**不承诺更新节奏**：

- 上游功能更新时我可能很久才合并一次；
- 游戏界面一改版，模板和坐标就得重标，我可能没空第一时间跟；
- 提 Issue 我会看，但不保证修。

想要最稳的版本，请用 [上游仓库](https://github.com/KIYI671/AhabAssistantLimbusCompany)。

---

## 协议与致谢

### 协议

- 本项目基于 [KIYI671/AhabAssistantLimbusCompany](https://github.com/KIYI671/AhabAssistantLimbusCompany)
  修改，原项目及本项目均遵循 **[GNU AGPL-3.0](./LICENSE)**。
- `LICENSE` 文件为上游原样保留（未做任何修改）。
- 本分支相对于上游的**全部改动**记录在 [CUSTOM_CHANGES.md](./CUSTOM_CHANGES.md)（开发者视角，
  含文件级细节）与 [CHANGELOG.md](./CHANGELOG.md)（使用者视角）。
- 若你分发本项目的二进制版本，按 AGPL-3.0 要求需同时提供对应源码。
- 软件图标素材来源网图，不属于 AGPL v3 协议开源的内容，如有侵权请联系原作者删除。
- 部分图像与音频素材来自 [边狱巴士中文WIKI](https://limbuscompany.huijiwiki.com/wiki/) 与
  [月海伦娜](https://yuehailunna.lofter.com/)，应要求进行声明。

### 致谢（继承自上游，完整列表见 [README.upstream.md](./README.upstream.md)）

AALC 的存在离不开这些开源项目：

| 项目 | 链接 | 说明 |
|---|---|---|
| LALC | [LixAssistantLimbusCompany](https://github.com/HSLix/LixAssistantLimbusCompany) | 上游作者的起点项目 |
| OCR 识别 | [PaddleOCR-json](https://github.com/hiroi-sora/PaddleOCR-json) | 队伍/卡包识别的基础 |
| 图形界面 | [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) | GUI 组件库 |
| 三月七小助手 | [March7thAssistant](https://github.com/moesnow/March7thAssistant) | 模拟器相关思路 |
| BAAS | [blue_archive_auto_script](https://github.com/pur1fying/blue_archive_auto_script) | 模拟器相关代码 |

以及上游 [贡献者列表](https://github.com/KIYI671/AhabAssistantLimbusCompany/graphs/contributors)。

---

## 免责声明

本项目为自动化脚本，仅用于学习与研究。使用本软件可能违反游戏用户协议，
由此产生的账号封禁、数据异常等一切后果由使用者自行承担。请勿用于商业用途或代练收费。
