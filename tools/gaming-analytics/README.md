# gaming-analytics — 游戏 IP × YouTube 数据抓取与排序

一个零依赖（只用 python3 标准库）的数据管线，用来替掉那张手工维护的品类表里两处说不清的地方：

| Kat 的 comment | 这里怎么解决 |
|---|---|
| 1. Player Scale 的数据来源和 estimate 逻辑是什么？ | 每个数字都带 **来源 URL + 方法名 + 假设系数 + 区间 + 置信度**，逻辑全部写在 [METHODOLOGY.md](METHODOLOGY.md)，系数在 `config/model.json` 里可改可复算 |
| 2. Key IPs 按销量和 YouTube 观看量排序（能爬就爬） | `run.py all` 自动抓 Steam 在线人数 / SteamSpy / Wikipedia 销量 / YouTube Data API，算出综合分并输出排好序的 Key IPs 列、逐 IP 明细表和 CSV |

> 抓取全部走**官方 API**（Valve 公开接口、YouTube Data API v3、Wikipedia API、SteamSpy 公开 API），
> 不解析 YouTube 网页、不绕验证码——那样做既违反 ToS 又几天就会失效。

---

## 快速开始

```bash
cd tools/gaming-analytics

# 0) 不需要 key、不需要网络：用内置假数据跑通全流程，看看产出长什么样
python3 run.py selftest && cat out/selftest/report.md

# 1) 申请一个 YouTube Data API key（Google Cloud Console → 启用 "YouTube Data API v3" → 凭据）
export YOUTUBE_API_KEY=xxxxxxxx

# 2) 补齐 Steam appid 和 YouTube channel id（写入 config/catalog.resolved.json，需人工过目）
python3 run.py resolve

# 3) 抓数 + 出报告
python3 run.py all

# 产出
#   out/report.md      Markdown 报告（品类总表 / Key IP 排序 / 达人频道 / 数据缺口 / 审计链路）
#   out/ips.csv        逐 IP 明细，可直接贴回原表
#   out/categories.csv 品类汇总
#   out/channels.csv   达人频道
#   out/raw.json       原始 API 返回，出数有疑问时回查
#   out/analysis.json  完整推导过程，含未被采用的交叉验证方法
```

只想重算模型、不想再消耗配额：改完 `config/model.json` 后跑 `python3 run.py report`，它只读 `out/raw.json`。

---

## Windows 从零开始（非技术向）

**只需要做一次的准备**

1. 装 Python：打开 <https://www.python.org/downloads/> → 点黄色大按钮 `Download Python 3.x` → 运行下载的安装包
   → ⚠️ **务必勾选最下面的 `Add python.exe to PATH`** → 点 `Install Now` → 等它跑完点 Close
2. 把 `gaming-analytics.zip` 解压出来（右键 → 全部解压），记住解压后的文件夹位置，比如
   `C:\Users\你的用户名\Downloads\gaming-analytics`
3. 进到那个文件夹里（里面能看到 `run.py`），**按住 Shift 键 + 在空白处点右键** →
   选 `在此处打开 PowerShell 窗口`（有的系统显示"在终端中打开"）
4. 在弹出的黑窗口里输入下面这行，确认 Python 装好了：

   ```powershell
   python --version
   ```

   显示 `Python 3.x.x` 就对了。如果提示"不是内部或外部命令"，说明第 1 步的 PATH 没勾，重装一遍。

**每次要出数据时**

在同一个黑窗口里，依次粘贴这两行（第一行把 `你的密钥` 换成实际的 key）：

```powershell
$env:YOUTUBE_API_KEY="你的密钥"
python run.py all
```

跑完会显示产出文件的位置。结果在 `out` 文件夹里：

- `report.md` —— 完整报告，用记事本就能打开（想看排版效果可以拖进浏览器或用 VS Code）
- `ips.csv` / `categories.csv` —— **双击用 Excel 打开**，可以直接贴回原表

**常见状况**

| 现象 | 原因 / 处理 |
|---|---|
| `python` 不是内部或外部命令 | 安装时没勾 `Add python.exe to PATH`，重装 |
| 满屏 `407 Proxy Authentication Required` | 你的网络要经过需要账号密码的代理。先跑 `python run.py doctor` 看用的是哪个代理，再按它给的三种解法选一种 |
| 公司代理要账号密码 | `python run.py all --proxy-user 你的公司账号` —— 会提示输密码，输入时不显示，也不会留在命令历史里。若仍报 407，多半是 NTLM/Kerberos 域认证，Python 的基础认证搞不定，需要找 IT 开白名单 |
| 想先确认环境有没有问题 | `python run.py doctor` —— 一条命令看 Python、代理、五个数据源分别通不通 |
| 卡在 Wikipedia 或 Steam 很久 | 网络连不上这两个站，改用 `python run.py all --no-wikipedia --no-steam` |
| 提示 quota / 配额用尽 | 当天 10,000 点用完了，太平洋时间午夜自动重置；或加 `--no-search` 只花 24 点 |
| 想省额度先试试水 | `python run.py all --no-search`（跳过最贵的搜索，只拿频道数据） |

> 完整跑一次 `all` 约消耗 5,500 点配额，一天的额度够跑 1 次多一点。改模型系数重新出报告
> （`python run.py report`）不花任何配额。

---

## 命令

| 命令 | 作用 | 网络 | YouTube 配额 |
|---|---|---|---|
| `selftest` | 用 `tests/fixtures/raw_sample.json` 跑通分析+渲染 | 不需要 | 0 |
| `resolve` | 按名字查 Steam appid、按 handle 查 channel id | 需要 | ~20 单位 |
| `collect` | 抓取全部原始数据 → `out/raw.json` | 需要 | 见下 |
| `doctor` | 体检：Python 版本、代理设置、五个数据源连通性 | 需要 | 0 |
| `report` | 只读 `raw.json` 出报告和 CSV | 不需要 | 0 |
| `all` | `collect` + `report` | 需要 | 见下 |
| `verify` | 列出所有人工录入的数字及其过期天数 | 不需要 | 0 |

常用开关：`--proxy http://127.0.0.1:7890`（走本地代理软件）、`--no-search`（跳过最贵的 search.list）、`--offline`（全部走缓存）、
`--verified-only`（忽略 `verified=false` 的人工数字）、`--cache-ttl`（默认 86400 秒）。

### 配额预算 / Quota budget

YouTube Data API 默认每天 10,000 单位：`channels.list` = 1，`videos.list` = 1，**`search.list` = 100**。

| 跑法 | 请求构成（当前 catalog：18 个 IP、3 个查询词） | 约计消耗 |
|---|---|---|
| `all` 完整 | 18×(1 频道 + 3×(100 搜索 + 1 视频)) + 6 达人频道 | **≈ 5,500 单位** |
| `all --no-search` | 18 频道 + 6 达人频道 | **≈ 24 单位** |
| `resolve` | 每个未解析 handle 1 单位（回退到搜索时 100） | ≈ 20 单位 |

也就是说完整跑一次每天能跑约 1.8 次。加查询词或加 IP 前先按 100/次 算一下。
配额打满时程序会给出明确提示，而不是静默返回空数据。

---

## 目录结构

```
config/catalog.json        品类 / Key IP / 频道 / 搜索词（手工维护的唯一真源）
config/model.json          全部估算系数：CCU→DAU、DAU→MAU、平台倍数、活跃率、排序权重
config/manual_figures.json 没有 API 的数字（厂商公告 MAU / 销量 / 注册数），逐条带来源和日期
gaming_analytics/
  httpclient.py   带磁盘缓存、指数退避重试、配额计数的 GET 客户端（key 不进缓存键）
  youtube.py      YouTube Data API v3：频道、handle 解析、按播放量取 top 视频
  steam.py        Valve 在线人数 / 商店搜索 / appdetails；SteamSpy owners
  wikipedia.py    销量表解析（保留维基条目里的原始引用链接）
  playerscale.py  ★ 估算器：五条路径、区间、新鲜度惩罚、交叉验证
  rank.py         ★ 综合排序：log10 归一 + 缺维重归一化
  report.py       Markdown / CSV 渲染
  pipeline.py     resolve / collect / analyse 编排
  cli.py          命令行
tests/            21 个离线单测 + 假数据生成器
```

测试：`python3 -m unittest discover -s tests -v`

---

## 出数时必须遵守的三条

1. **Player Scale 一律写区间，不写单值**，并带上方法名（`steam_ccu` / `official_mau` …）。
   原表那种 `~250–350M (estimated)` 如果不写清口径和来源，等于没写。
2. **"YouTube 总播放量" 这个指标 API 给不了。** Data API 只能给：某个频道的历史总播放量、
   某条视频的播放量。报告里的 *Creator sample views* 是「该 IP 搜索词下最高播放的一批视频之和」，
   是**跨 IP 可比的热度指数**，不是该 IP 在 YouTube 的全量播放。像 Minecraft 的 1.5T 这种全量数字
   只存在于 letsplayindex 这类三方聚合站，引用时必须标明是三方口径。
3. **人工录入的数字先 `run.py verify` 过一遍。** `config/manual_figures.json` 里的初始值都是
   `verified=false` 的种子值，只是为了让管线跑起来，**发布前必须逐条打开 source_url 核对并改成
   `verified=true`**；`report --verified-only` 会直接拒绝使用未核对的数字。

---

## 想加一个 IP / 换一个品类

改 `config/catalog.json`：加一条 `ips` 记录（`name` / `game_type` / `platforms` / `on_steam` /
`youtube.search_queries` 是必填项），跑 `run.py resolve` 补 id，再跑 `run.py all`。
`game_type` 决定用哪档活跃率，填错会系统性地高估或低估，取值见 `config/model.json` 的 `lifetime_to_mau`。
