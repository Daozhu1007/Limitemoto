---
name: limititemoto
description: 音游手元素材流水线（Limitime 的手元 workflow）。把手机传来（小米互传/相册导出）的手元视频+成绩截图自动识别曲目、按谱面定数归档进 D:\Daozh\Videos、配游戏原版音频、并可驱动 RhythmAlign 出 _synced.mp4。当用户提到"整理手元/新的一批手元/小米互传的文件/手元归档/识别截图配视频/找音频/track.mp3/舞萌或Arcaea素材准备"时使用。B站发布类需求属于本流水线末端，必须人工确认后才执行。
---

# Limitemoto — 手元素材流水线

Limitime + Temoto(手元) + Workflow。解决从"手机传上来一堆文件"到"归档完毕可发布"的全流程。
判断层（识别、命名、决策）由 agent 做，执行层用本 skill 的 scripts 和两个公开 API。

## 归档规范（用户既定约定，必须遵守）

- 舞萌: `D:\Daozh\Videos\舞萌手元\<定数 13.x>\<歌名>\歌名.jpg + 歌名.mp3 + 歌名.mp4`，对齐产物为 `歌名_synced.mp4`
- **13.x 是谱面定数（MASTER/Re:MASTER 的 level_value），不是游戏版本！**
- Arcaea: `D:\Daozh\Videos\Arcaea手元\<小写歌名>\`，Pure Memory 的素材加 `_PM` 后缀（如 `lastgoodbye_PM.mp4`）
- 同一首歌多次尝试: `歌名_1.mp4`、`歌名_2.mp4`、最好成绩用后缀标记
- 歌名风格: 罗马字/官方英文（brainjacksyndrome、DanceRobotDance、RED）或社区中文昵称（转生苹果、白妄想、宙天）；拿不准就用截图上显示的曲名
- 用户不需要提前确认归档操作（可逆），但**发布（B站）永远先给用户预览标题/简介/标签，等确认才执行**

## 流程六步

### ① 传输（人工） — 用户用小米互传传到 `D:\Download\XiaomiShare`（或指定目录）

### ② 扫描配对 + 识别

```bash
python <skill目录>/scripts/pair_scan.py <目录>       # stdout 出 JSON
```

- 照片唯一可信时间 = **EXIF DateTimeOriginal**（文件名和 mtime 都是传输时刻，无用）
- 视频: 文件名 `VID_YYYYMMDD_HHMMSS` = 录制开始，`+mvhd时长` = 结束；照片通常在视频结束后 **1~6 秒**
- unpaired_videos: 没照片配的视频 → 用 imageio_ffmpeg 抽帧识别（`-ss 8` 取开头 + `-sseof -20` 取结尾）
- `--out scan.json` 落盘备查

**识别（agent 用 Read 看图）：**
- maimai 结果屏: 环形屏幕 + SSS+ + 达成率%，曲名在中央偏上的横条里
- Arcaea 结果页: 曲名大字居中，PURE/LOST 记数
- 曲名看不清 → PIL 裁剪曲名栏区域放大 3~6 倍再看（结果屏中部横条）
- **警惕浊点假名**: ビビデバ vs ヒビデバ、うぇいびー vs うぇいうぃー，放大确认浊点/半浊点
- 分辨同名曲的 DX/旧版: 成绩屏有 DX 徽标；定数表里认 folderName 带 `[DX]` 的条目

### ③ 定数分桶（决定进哪个 13.x 文件夹）

落雪 API（同 FluentMai 所用）:

```
GET https://maimai.lxns.net/api/v0/maimai/song/list?notes=true
```

- `difficulties.dx` 数组: index 0-4 = Basic/Advanced/Expert/**MASTER(3)**/**Re:MASTER(4)**，取 `level_value` 即定数
- 13.x 文件夹不存在就创建；新歌定数可能是整数（如 13.0）或未定，如实告知用户
- LXNS 拿到的 `id`（官方歌曲 ID）直接用于第④步 shortid

### ④ 拿音频（游戏原版剪辑）

```bash
python <skill目录>/scripts/awmc_get.py "<曲名关键词>" -o <歌名文件夹>
python <skill目录>/scripts/awmc_get.py -i <shortid> -o <歌名文件夹>   # 按ID
python <skill目录>/scripts/awmc_get.py --refresh                      # 刷新曲库缓存(7天)
```

- 站点: **`https://download.wmc.pub/`**（AWMC-MaiArchive，awmc.cc 已弃用）。**必须走 clash 代理 127.0.0.1:7897**，直连会挂起数分钟
- shortid = "1" + 官方歌曲ID 补零 6 位（RED 1868 → `011868`）
- 产物 track.mp3 = 游戏内实际播放的剪辑版音频（无按键音）；用包内 `maidata.txt` 的 `&title=` 核对曲名
- 整包/曲绘/背景视频: `--zip --novideo`、`bg.png`、`pv.mp4` 路由见 awmc_get.py 文件头注释
- **fallback**（站点挂了/曲不在）: YouTube 外部出力/譜面確認用渲染视频 = 游戏版音源（yt-dlp `-x --audio-format mp3 --ffmpeg-location <imageio_ffmpeg路径>`；搜曲名+外部出力，认准 めーがす/SAT:S/ざっくま 等渲染 up 主或官方频道），渲染版比游戏版多几秒首尾静音，不影响对齐

**Arcaea**（游戏内基本用曲师完整版——风险在"选对版本"，不在"找游戏剪辑"）:

1. 小写缩写 → 官方曲名: `ytsearch "<缩写> arcaea"` 交叉确认（历史案例: chelsta→Chelsea、onestepcloser→One Step Closer (Mameyudoufu feat. 藍月なくる)、tabootearsup→taboo tears you up 2017 (REDALiCE)、Code_Oblivion→Code: Oblivion、gimme→Gimme Caramel Popcorn!）
2. **多命中必须消歧**: 缩写歧义（gimme 曾同时命中 GIMME DA BLOOD 和 Gimme Caramel Popcorn!）→ 抽帧看选曲画面/曲名牌: `ffmpeg -ss 3 -i video.mp4 -frames:v 1`，再加 `-ss 25` 一帧
3. 音源优先级: **曲师本人频道**（YouTube/SoundCloud/Bandcamp）> lowiro 官方 > 高播放转载
   - 曲师改题常见（キャラメルポップコーンたべたいよ〜 → Arcaea 题为 Gimme Caramel Popcorn!）: 按曲师名搜原题；完整版可直接用——RhythmAlign 的 offset 估计天然处理游戏版从完整版截取的偏移
   - Arcaea 无 maimai 式大剪歌，但注意同名 remix/别 version
4. 下载同 fallback 链路，文件名与 mp4 同名（`歌名.mp3`）
5. **最后防线**: RhythmAlign 对不上会 low-confidence 拒绝输出——被拒绝先怀疑音源版本拿错，而不是去调参数
6. **YouTube bot 检测三层应对**（2026-10-05 实战: "Sign in to confirm you're not a bot"）:
   - 根治①: 装 deno（JS runtime）进 PATH —— winget 无此包，从 github.com/denoland/deno/releases 下 `deno-x86_64-pc-windows-msvc.zip` 解压 deno.exe 到 `~/bin`。装完 android client 流会解除 SABR 限制（111→206kbps）
   - 应急②: `--extractor-args "youtube:player_client=android"` —— 无需登录态，配 deno 可达 ~206kbps/44.1kHz（对齐足够；web client 的 48kHz/227kbps 更好）
   - 无效③: cookies-from-browser edge（浏览器运行时锁库，yt-dlp#7271）；web client 即便 +deno+代理 仍可能 bot 检测（IP 信誉，登录态才是终极解）
   - 库内已有同源文件时: 新下产物先 ffprobe 对比码率/时长，码率不占优就不覆盖

**联动曲特例**（曲师不在 Arcaea 生态，如 Last Goodbye/Undertale）: OST 官方频道就是"曲师本人"级别的一手源。**组曲混剪是最大陷阱**——搜 Last Goodbye 时 6 个结果里 3 个是 Hopes And Dreams+Save The World+Last Goodbye 连播（420s+），另有翻弹/Cover 片段；认准官方频道 + 时长吻合手元（视频时长 - 20s 前后操作 ≈ 曲长）。端到端实证: lastgoodbye 官方 OST(139s) × find_offset → 置信通过（offset 5.6s = 进曲准备段）。

### ⑤ 归位（agent 执行，无需确认）

建 `<定数>/<歌名>/` → 照片视频改名迁入（`mv`）→ 音频命名 `歌名.mp3`。
坑: 跨盘移动用 `shutil.move`（`os.replace` 会 WinError 17）；Windows Python 不认 git-bash 的 `/tmp`。

### ⑥ 加工与发布

- RhythmAlign（用户的项目，`D:\Code\RhythmAlign`）:
  `auto_sync.py` 是函数库 — `find_offset(video_path, music_path)` 返回偏移，`mix_and_export(video_path, music_path, offset, output_path)` 出成品。产物命名 `歌名_synced.mp4`
- 发布（v2，未建）: bilibili-api 上传，**定 时 发 布 与 上 传 前 必 须 人工确认**

## 故障诊断思路（案例沉淀）

- 站点"打不开"先分清是谁的锅: check-host.net 多节点测（全球超时=站点挂，与本地无关）；单机超时=试代理/换 DNS/真实浏览器
- 小 CDN 会用 TLS 指纹/挂起对待裸 HTTP 客户端: curl/urllib 全挂不代表浏览器也挂，反之亦然
- Windows + git-bash 环境: `/tmp` 映射到 `%TEMP%`，但 Windows Python 进程不认 `/tmp` 字面路径

## 版本史

- v0.1 (2026-10-04): pair_scan + awmc_get + 本 skill；当期批次 9 首全流程实测跑通
