# Gaming IP x YouTube data pack

> ⚠️ **SYNTHETIC FIXTURE RUN.** Every number below comes from `tests/fixtures/raw_sample.json`, which contains made-up values used to test the pipeline offline. Do not quote anything here. Run `python3 run.py all` with a YouTube API key and network access for real figures.

Generated: `2026-09-21T03:26:50.583322+00:00` · requests: 0 (cache hits 0) · YouTube quota used: 0 units

Two review comments drove this table:

1. **"Player Scale 的数据来源和 estimate 逻辑是什么？"** — every Player Scale cell below now shows `mid (low–high)`, the method that produced it, and a confidence grade. The full derivation is in [METHODOLOGY.md](METHODOLOGY.md); the constants are in `config/model.json`.
2. **"Key IPs 按销量和 YouTube 观看量排序"** — the Key IPs column is ordered by a composite score (sales + YouTube views + player scale), and the per-IP table below shows the raw inputs behind that order.

Confidence grades: **A** = first-party disclosure, **B** = derived from a first-party API (Steam CCU), **C** = derived from third-party estimates or stale/lifetime figures.

## 1. Category overview

| Category | Key IPs (ranked) | Player Scale (MAU, mid & range) | Method | Conf. | Top-IP YouTube views | Official channels (sum) | Creator channels (sum) | Coverage |
|---|---|---|---|---|---|---|---|---|
| **Minecraft** | Minecraft | 170M (67.2M–430M) | official_mau | A | 5.7B | 3.2B | 9.0B | 1/1 IPs |
| **FPS** | Call of Duty > PUBG: Battlegrounds > Overwatch 2 > VALORANT > Counter-Strike 2 > Apex Legends > Fortnite | 248M (113M–3.5B) | steam_ccu | C | 602B | 582B | 23.0B | 4/7 IPs |
| **Single-player / Console** | The Legend of Zelda > Souls-like (FromSoftware) > Grand Theft Auto V (unranked, no data: The Last of Us) | 26.4M (6.5M–265M) | steam_ccu | C | 160B | 97.8B | 105B | 2/4 IPs |
| **Anime** | Wuthering Waves > Honkai: Star Rail > Genshin Impact (unranked, no data: Arknights) | no signal | - | C | 1.0T | 1.0T | 67.0B | 0/4 IPs |
| **MOBA** | Dota 2 > League of Legends | 2.0M (911K–16.1M) | steam_ccu | C | 1.1T | 601B | n/a | 1/2 IPs |

> Player Scale is **monthly active players (MAU)**, summed across the category's IPs and then cut by an overlap discount (`overlap_discount` in `config/catalog.json`) because one person plays several shooters. Categories where some IPs have no signal are a **floor, not a total** — see the coverage column and §4.

## 2. Key IP ranking

| # | IP | Category | Score | Units sold | Official channel views | Creator sample views | Most-viewed video | Player Scale (MAU) | Method | Conf. | Missing |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Wuthering Waves | Anime | 0.992 | n/a (F2P or undisclosed) | [640B](https://www.youtube.com/channel/UC_FIXTURE_wuthering_wa) | 373B | [320B](https://www.youtube.com/watch?v=vid_wuthering_waves_0) | no signal | - | - | player_scale, sales |
| 2 | Honkai: Star Rail | Anime | 0.933 | n/a (F2P or undisclosed) | [380B](https://www.youtube.com/channel/UC_FIXTURE_honkai_star_) | 298B | [190B](https://www.youtube.com/watch?v=vid_honkai_star_rail_0) | no signal | - | - | player_scale, sales |
| 3 | Call of Duty | FPS | 0.9156 | n/a (F2P or undisclosed) | [380B](https://www.youtube.com/channel/UC_FIXTURE_call_of_duty) | 222B | [190B](https://www.youtube.com/watch?v=vid_call_of_duty_0) | no signal | - | - | player_scale, sales |
| 4 | PUBG: Battlegrounds | FPS | 0.768 | n/a (F2P or undisclosed) | [76.0B](https://www.youtube.com/channel/UC_FIXTURE_pubg) | 101B | [38.0B](https://www.youtube.com/watch?v=vid_pubg_0) | 103M (47.1M–930M) | steam_ccu | C | sales |
| 5 | Dota 2 | MOBA | 0.75 | n/a (F2P or undisclosed) | [600B](https://www.youtube.com/channel/UC_FIXTURE_dota2) | 470B | [300B](https://www.youtube.com/watch?v=vid_dota2_0) | 2.5M (1.1M–20.1M) | steam_ccu | C | sales |
| 6 | The Legend of Zelda | Single-player / Console | 0.7218 | n/a (F2P or undisclosed) | [90.0B](https://www.youtube.com/channel/UC_FIXTURE_zelda) | 70.5B | [45.0B](https://www.youtube.com/watch?v=vid_zelda_0) | no signal | - | - | player_scale, sales |
| 7 | Overwatch 2 | FPS | 0.6635 | n/a (F2P or undisclosed) | [56.0B](https://www.youtube.com/channel/UC_FIXTURE_overwatch) | 61.2B | [28.0B](https://www.youtube.com/watch?v=vid_overwatch_0) | 37.1M (17.0M–599M) | steam_ccu | C | sales |
| 8 | Minecraft | Minecraft | 0.6516 | [300M](https://www.minecraft.net/en-us/article/minecraft-live-2023) | [3.2B](https://www.youtube.com/channel/UC_FIXTURE_minecraft) | 2.5B | [1.6B](https://www.youtube.com/watch?v=vid_minecraft_0) | 170M (67.2M–430M) | official_mau | A | - |
| 9 | VALORANT | FPS | 0.5994 | n/a (F2P or undisclosed) | [44.0B](https://www.youtube.com/channel/UC_FIXTURE_valorant) | 25.7B | [22.0B](https://www.youtube.com/watch?v=vid_valorant_0) | no signal | - | - | player_scale, sales |
| 10 | Counter-Strike 2 | FPS | 0.4373 | n/a (F2P or undisclosed) | [22.0B](https://www.youtube.com/channel/UC_FIXTURE_counter_stri) | 20.9B | [11.0B](https://www.youtube.com/watch?v=vid_counter_strike_0) | 5.1M (2.3M–87.5M) | steam_ccu | C | sales |
| 11 | Genshin Impact | Anime | 0.3864 | n/a (F2P or undisclosed) | [7.0B](https://www.youtube.com/channel/UC_FIXTURE_genshin_impa) | 9.3B | [3.5B](https://www.youtube.com/watch?v=vid_genshin_impact_0) | no signal | - | - | player_scale, sales |
| 12 | Apex Legends | FPS | 0.385 | n/a (F2P or undisclosed) | [1.8B](https://www.youtube.com/channel/UC_FIXTURE_apex_legends) | 2.2B | [900M](https://www.youtube.com/watch?v=vid_apex_legends_0) | 185M (84.9M–3.0B) | steam_ccu | C | sales |
| 13 | Souls-like (FromSoftware) | Single-player / Console | 0.2547 | n/a (F2P or undisclosed) | [5.0B](https://www.youtube.com/channel/UC_FIXTURE_soulsborne) | 3.9B | [2.5B](https://www.youtube.com/watch?v=vid_soulsborne_0) | 4.3M (2.0M–8.7M) | steam_ccu | B | sales |
| 14 | Fortnite | FPS | 0.2395 | n/a (F2P or undisclosed) | [2.7B](https://www.youtube.com/channel/UC_FIXTURE_fortnite) | 3.3B | [1.4B](https://www.youtube.com/watch?v=vid_fortnite_0) | no signal | - | - | player_scale, sales |
| 15 | Grand Theft Auto V | Single-player / Console | 0.1929 | [200M](https://ir.take2games.com/financial-information/quarterly-results) | [2.8B](https://www.youtube.com/channel/UC_FIXTURE_gta) | 3.4B | [1.4B](https://www.youtube.com/watch?v=vid_gta_0) | 26.8M (5.7M–303M) | steam_ccu | C | - |
| 16 | League of Legends | MOBA | 0.0 | n/a (F2P or undisclosed) | [600M](https://www.youtube.com/channel/UC_FIXTURE_league_of_le) | 570M | [300M](https://www.youtube.com/watch?v=vid_league_of_legends_0) | no signal | - | - | player_scale, sales |
| - | The Last of Us | Single-player / Console | - | n/a (F2P or undisclosed) | n/a | n/a | - | no signal | - | - | player_scale, sales, youtube_views |
| - | Arknights | Anime | - | n/a (F2P or undisclosed) | n/a | n/a | - | no signal | - | - | player_scale, sales, youtube_views |

Score = weighted mean of log10-normalised sales (40%), YouTube views (45%) and player scale (15%); when a dimension is missing the remaining weights are renormalised (the *Missing* column says which).

**"Creator sample views"** is the sum of the most-viewed videos the Data API returns for that IP's search terms, excluding the official channel. It is a *comparable heat index across IPs*, not the IP's total YouTube views — the API cannot produce an all-time total for a topic. Whole-ecosystem figures (e.g. Minecraft's 1.5T) only exist at third-party aggregators such as letsplayindex, which must be cited as such.

## 3. Creator channels

| Category | Channel | Subscribers | Lifetime views | Videos | Country |
|---|---|---|---|---|---|
| Minecraft | [MrBeastGaming (fixture)](https://www.youtube.com/channel/UC_FIXTURE_MrBeastGamin) | 37.2M | 9.0B | 1.3K | US |
| FPS | [Anomaly (fixture)](https://www.youtube.com/channel/UC_FIXTURE_Anomaly) | 100M | 23.0B | 4.6K | US |
| Single-player / Console | [TheDaniRep (fixture)](https://www.youtube.com/channel/UC_FIXTURE_TheDaniRep) | 55.2M | 25.0B | 2.5K | US |
| Single-player / Console | [Jelly (fixture)](https://www.youtube.com/channel/UC_FIXTURE_Jelly) | 87.4M | 25.0B | 1.5K | US |
| Single-player / Console | [VanossGaming (fixture)](https://www.youtube.com/channel/UC_FIXTURE_VanossGaming) | 344M | 55.0B | 1.8K | US |
| Anime | [KyoStinV (fixture)](https://www.youtube.com/channel/UC_FIXTURE_KyoStinV) | 25.0M | 15.0B | 383 | US |
| Anime | [IWinToLose (fixture)](https://www.youtube.com/channel/UC_FIXTURE_IWinToLose) | 98.5M | 52.0B | 5.7K | US |

## 4. Data gaps (nothing here is estimated — these need a human or a paid panel)

| IP | Issue | What to do |
|---|---|---|
| Counter-Strike 2 | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| VALORANT | no player-scale signal | VALORANT is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| VALORANT | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Call of Duty | no player-scale signal | Steam endpoints returned nothing - check the appid in config/catalog.json. |
| Call of Duty | no units-sold figure | Premium title with no units figure - check the publisher's IR page and add it to config/manual_figures.json, or set sales_key so the Wikipedia lookup can find it. |
| Fortnite | no player-scale signal | Fortnite is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| Fortnite | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Overwatch 2 | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Apex Legends | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| PUBG: Battlegrounds | no units-sold figure | Premium title with no units figure - check the publisher's IR page and add it to config/manual_figures.json, or set sales_key so the Wikipedia lookup can find it. |
| The Legend of Zelda | no player-scale signal | The Legend of Zelda is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| The Legend of Zelda | no units-sold figure | Seed row exists but is empty - pull the figure from https://www.nintendo.co.jp/ir/en/finance/software/index.html. |
| Souls-like (FromSoftware) | no units-sold figure | Seed row exists but is empty - pull the figure from https://www.bandainamco.co.jp/en/ir/. |
| The Last of Us | no player-scale signal | Steam endpoints returned nothing - check the appid in config/catalog.json. |
| The Last of Us | no units-sold figure | Seed row exists but is empty - pull the figure from https://www.sie.com/en/corporate/release.html. |
| The Last of Us | official YouTube channel unresolved | Set youtube.official_channel_id in config/catalog.json or rerun `resolve`. |
| Genshin Impact | no player-scale signal | Genshin Impact is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| Genshin Impact | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Wuthering Waves | no player-scale signal | Steam endpoints returned nothing - check the appid in config/catalog.json. |
| Wuthering Waves | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Arknights | no player-scale signal | Arknights is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| Arknights | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Arknights | official YouTube channel unresolved | Set youtube.official_channel_id in config/catalog.json or rerun `resolve`. |
| Honkai: Star Rail | no player-scale signal | Honkai: Star Rail is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| Honkai: Star Rail | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| League of Legends | no player-scale signal | League of Legends is not on Steam and has no seeded figure. Add a publisher disclosure to config/manual_figures.json, or buy a third-party panel (Sensor Tower / Newzoo / Circana) and cite it. |
| League of Legends | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |
| Dota 2 | no units-sold figure | Free-to-play: units do not exist. Rank this IP on revenue or MAU, and leave the sales column blank rather than implying zero. |

## 5. Audit trail

Per-IP derivations, including the cross-check methods that were *not* chosen and any disagreement between them, are in `out/analysis.json` under `ip_detail`. Raw API payloads are in `out/raw.json`. Both are regenerated by `python3 run.py all`.

- **Minecraft** — official_mau, inputs `{'disclosed_mau': 170000000.0, 'as_of': '2021-10'}`, sources: [Xbox Wire](https://news.xbox.com/en-us/2021/10/16/minecraft-live-2021/)
- **PUBG: Battlegrounds** — steam_ccu, inputs `{'steam_concurrent_players': 637611.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 5.6, 'platforms': ['pc', 'console', 'mobile']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 4.32x
- **Overwatch 2** — steam_ccu, inputs `{'steam_concurrent_players': 495453.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 2.6, 'platforms': ['pc', 'console']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 7.7x
- **Counter-Strike 2** — steam_ccu, inputs `{'steam_concurrent_players': 175371.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 1.0, 'platforms': ['pc']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 8.27x
- **Apex Legends** — steam_ccu, inputs `{'steam_concurrent_players': 1148251.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 5.6, 'platforms': ['pc', 'console', 'mobile']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 7.79x
- **Souls-like (FromSoftware)** — steam_ccu, inputs `{'steam_concurrent_players': 56934.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 2.6, 'platforms': ['pc', 'console']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture)
- **Grand Theft Auto V** — steam_ccu, inputs `{'steam_concurrent_players': 357574.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 2.6, 'platforms': ['pc', 'console']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 4.71x
- **Dota 2** — steam_ccu, inputs `{'steam_concurrent_players': 86288.0, 'ccu_to_dau': 9.0, 'dau_to_mau': 3.2, 'pc_store_share': 1.0, 'platform_multiplier': 1.0, 'platforms': ['pc']}`, sources: [SYNTHETIC fixture (not Valve)](https://example.invalid/fixture) · ⚠ methods disagree 3.86x
