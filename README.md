# Limitemoto

**Limitime + Temoto(手元) + Workflow** —— 音游手元素材流水线。

把"手机传来的一堆视频和截图"变成"归档完毕、音频就位、随时可发布"的手元库，全程由 AI agent 执行。
本仓库是这个流水线的**知识层（SKILL.md）+ 执行层（scripts/）**，设计为以 agent skill 的形态使用，
不做成独立软件 —— 因为流水线里真正难的判断（看截图认曲名、认日语浊点、同名曲消歧、站点挂了找备用源）
恰恰是 AI 随手能干而写死规则最脆弱的部分。

## 流水线

```
① 手机 → 小米互传传到电脑（人工，省不了）
② pair_scan.py 按 EXIF×视频时长自动配对 → agent 看截图识别曲目
③ 落雪 API 查谱面定数 → 定归档文件夹（舞萌手元/13.x）
④ awmc_get.py 从 AWMC-MaiArchive 拿游戏原版音频 track.mp3（备用: YouTube 外部出力）
⑤ 归位改名 → 舞萌手元/13.x/歌名/{jpg, mp3, mp4}
⑥ RhythmAlign (github.com/Daozhu1007/RhythmAlign) 加工出 _synced.mp4 → B站发布（人工确认）
```

## scripts

| 脚本 | 作用 |
|---|---|
| `pair_scan.py` | 扫描素材目录，EXIF DateTimeOriginal × 视频文件名起始+mvhd时长 贪心配对，输出 JSON |
| `awmc_get.py` | AWMC-MaiArchive (download.wmc.pub) 客户端：搜索/按ID下载 track.mp3+maidata/整包zip，曲库缓存 |

## 使用方式

作为 agent skill 安装（junction 或复制到 agent 的 skills 目录）:

```
mklink /J "%USERPROFILE%\.agents\skills\limititemoto" "D:\Code\Limitemoto"
```

SKILL.md 里写死了归档规范、两个公开 API（落雪定数表 / wmc.pub 谱面站）、以及一路踩过来的坑
（EXIF 才可信、定数不是版本号、代理直连差异、假名浊点……）。

## 为什么不是软件/MCP/RhythmAlign插件？

- 独立软件：内嵌视觉模型识别截图 = 大炮打每周一只的鸟
- RhythmAlign 插件：RhythmAlign 是发布的产品，该保持"视频+音频→synced"的纯粹；私人管线不进产品
- MCP：skill + CLI 已经覆盖文件批处理场景，MCP 只在多客户端远程调用时才值得
- skill + 脚本：判断给 AI，精密逻辑（二进制解析、API 客户端）沉淀为验证过的脚本，两边各干擅长的事

## License

个人工作流工具，未设开源许可（默认保留所有权利）。
