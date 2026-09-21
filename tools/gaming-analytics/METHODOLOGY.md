# Player Scale: 数据来源与估算逻辑 / Sources and estimate logic

> 回应 Kat 的 comment 1：「Player Scale 的数据来源和 estimate 逻辑是什么？」
>
> **一句话答案**：原表里的 `~250–350M (estimated)` 没有可追溯的来源，所以这里把它拆成了
> 「口径定义 + 5 条取数路径 + 一组公开的假设参数 + 误差区间 + 置信度」。程序里每一个数字都能
> 回答三个问题：它来自哪个 API/公告、用了哪几个假设、如果假设错了会错多少。
>
> **TL;DR (EN)**: the old cell was an unsourced point estimate. This document defines the metric,
> lists the five derivation paths in priority order, publishes every constant in
> `config/model.json`, and requires every output to be a range with a named method and a source URL.

---

## 1. 口径 / What "Player Scale" means here

**Player Scale = 月活跃玩家 (MAU)，全平台去重后的近似值。**

明确 *不是* 以下任何一个，因为这三个数字经常被混用，量级差 3–20 倍：

| 口径 | 含义 | 为什么不能当 Player Scale |
|---|---|---|
| Registered accounts 注册账号 | 历史累计注册 | 只增不减，含小号/机器人。Fortnite 的 6 亿+是这个口径 |
| Lifetime units sold 累计销量 | 卖出的份数 | 2013 年买 GTA V 的人不等于这个月在玩 |
| Peak CCU 同时在线峰值 | 瞬时并发 | 和 MAU 差一到两个数量级 |

分类层面的 Player Scale = 该品类下各 IP 的 MAU 之和 × (1 − 重叠折扣)。重叠折扣在
`config/catalog.json` 里按品类设置（FPS 25%、二次元 30% 等），因为一个人同时玩 CS 和 Apex
会被重复计算。

---

## 2. 取数优先级 / Source hierarchy

程序按下表顺序取数，取到第一条可用的作为主口径，其余作为交叉验证（`method_priority` in
`config/model.json`）：

| 优先级 | 方法 | 数据来源 | 是否自动抓取 | 置信度 |
|---|---|---|---|---|
| 1 | `official_mau` | 厂商财报 / 官方公告（Microsoft、Riot、Take-Two…） | 否，人工录入 `config/manual_figures.json` | A |
| 2 | `steam_ccu` | Valve `ISteamUserStats/GetNumberOfCurrentPlayers` | 是，免 key | B |
| 3 | `steam_owners` | SteamSpy owners 区间 | 是，免 key | C |
| 4 | `units_sold` | 厂商公告 / Wikipedia 销量表（带原始引用链接） | 是（Wikipedia）+ 人工 | C |
| 5 | `registered_users` | 官方注册账号公告 | 否，人工录入 | C |

没有任何一条可用时，程序输出 `no signal` 并把这个 IP 列进报告第 4 节的「数据缺口」，
**不会**用别的 IP 外推补一个数——这正是原表最需要修掉的问题。

---

## 3. 五条换算公式 / The five formulas

所有系数都在 `config/model.json`，改完重新跑 `python3 run.py report` 即可看到影响，无需重新抓数。

### 3.1 `official_mau`（最可信）
```
MAU = 公告值
区间 = 值 ÷ 1.15 ~ 值 × 1.15，再按数据新鲜度放大
```
只有「时间衰减」一个不确定性：2021 年的 MAU 用在 2026 年的表里，区间会被自动放大
（`freshness`：超过 180 天后，每满一年把区间半宽放大 35%，上限 +120%）。

### 3.2 `steam_ccu`（主力方法）
```
DAU        = CCU × ccu_to_dau        (默认 9，区间 6–13)
MAU_steam  = DAU × dau_to_mau        (默认 3.2，区间 2.2–4.5)
MAU_pc     = MAU_steam ÷ steam_share_of_pc   (默认 0.75，仅当该作在 Steam 之外的 PC 平台也发行)
MAU        = MAU_pc × platform_multiplier    (PC 1.0 + 主机 1.6 + 手机 3.0，封顶 6.0)
```
举例：某作 CCU = 1,000,000 → DAU ≈ 9.0M → Steam MAU ≈ 28.8M；若为 PC 独占则 Player Scale ≈ 28.8M，
若同时有主机和手机版则 ×5.6 ≈ 161M。

**这三个系数就是「estimate 逻辑」的全部**，它们的依据：
- `ccu_to_dau` 9×：竞技类在线时长长、翻台率低（取 6×），休闲/手游化的高（取 13×）。
- `dau_to_mau` 3.2×：等价于 31% 的 DAU/MAU 粘性；FPS/MOBA 粘性高（2.2×），抽卡/单机低（4.5×）。
- `platform_multiplier`：主机盘子约等于 PC 的 1.6 倍、手机约 3 倍，用于从「只能测到的 PC」外推到全平台。

> ⚠️ 主机和手机的数字是**外推**，不是实测。要实测只能买 Circana（北美主机）、Sensor Tower /
> AppMagic（手机）或 Newzoo 的面板数据。报告里这类单元格的置信度永远不会高于 B。

### 3.3 `steam_owners`
```
MAU = SteamSpy owners 中位 × lifetime_to_mau[game_type] × platform_multiplier
```
`lifetime_to_mau`（月活占累计拥有者的比例）是整个模型里最大的杠杆，按品类分档：
沙盒长线 30%、live-service 14%、抽卡 18%、带在线模式的买断 10%、纯单机 3.5%。
SteamSpy owners 本身就是估算且区间很宽（如 "100M .. 200M"），所以这条路径固定为 C 级。

### 3.4 `units_sold`
```
MAU = 累计销量 × lifetime_to_mau[game_type] ÷ 新鲜度惩罚
```
适合《塞尔达》《The Last of Us》这类没有在线口径的单机作。3.5% 的活跃率意味着
3200 万销量 ≈ 112 万 MAU——看起来低，但这正是单机 IP 与 live-service 的真实差别。

### 3.5 `registered_users`
```
MAU = 注册账号 × registered_to_mau (默认 8%，区间 4–15%)
```
最弱的一条，只在没有别的口径时使用，报告里会标注「account-derived」。

---

## 4. 交叉验证与置信度 / Cross-checks and confidence

程序会把所有可用方法都算一遍：

- 主口径 = 优先级最高的那条；
- 其余方法作为 cross-check 写进 `out/analysis.json`；
- 若任意两条相差 ≥ **2.5 倍**，置信度降为 C，区间扩展为所有方法的并集，并在报告里写明
  「methods disagree N×」。**不做平均**——平均会把「我们不知道」伪装成「我们知道」。

置信度分级：**A** 厂商一手披露；**B** 一手 API 推导（Steam CCU）；**C** 三方估算 / 累计值 / 过期数据。

---

## 5. 这套逻辑答不了的问题 / Known limits

1. **中国大陆数据**：原神/鸣潮/明日方舟的国服、以及微信小游戏生态，公开 API 完全测不到。
   需要伽马数据、QuestMobile 或厂商披露。
2. **主机端**：PSN/Xbox 不开放玩家量接口，本模型用 PC 外推。
3. **手游**：Sensor Tower / AppMagic 是付费的，程序预留了录入位（`manual_figures.json`），
   但不会假装能免费拿到。
4. **Steam CCU 是瞬时值**：单次采样会受时区影响，正式出数前请用 `run.py collect` 定时跑
   （如每天 UTC 20:00 + 04:00 两次）取均值，或改用 SteamDB 的日峰值。
5. **官方 MAU 往往过期**：Minecraft 的 1.7 亿 MAU 是 2021 年的口径，程序会因此自动放宽区间——
   这是提醒，不是修复；正确做法是去找最新披露。

---

## 6. 如果要推翻原表的 `~250–350M` / How to falsify the old numbers

跑一次 `python3 run.py all`，对照报告第 1 节：

- 如果程序给出的品类区间**包含** 250–350M，说明原估计和公开数据不矛盾（但仍需注明口径）；
- 如果**不包含**，报告会直接给出是哪几个 IP、哪条公式、哪个系数导致的差异，可以逐项讨论；
- 如果品类覆盖率（coverage 列）低于 60%，那么任何总量都是**下限**，原表的区间既不能被证实也不能被证伪，
  这种情况下应该改写成「已覆盖 X 个 IP，合计 ≥ N」而不是给一个范围。
