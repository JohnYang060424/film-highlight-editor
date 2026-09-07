# film-highlight-editor

把完整影视剧剪裁成「蒙太奇骨架 + 深度解说转场」精华版，并交付 B 站三件套（成片 + 封面 + 文案）的自动化剪辑流水线。
本仓库同时是 WorkBuddy 的 Agent 技能（技能定义见 [`SKILL.md`](./SKILL.md)）。

> **Film Highlight Editor** — an automated pipeline that condenses a full movie / TV episode into a
> *"montage skeleton + in-depth narration transition"* highlight version and delivers the Bilibili
> three-piece set (final video + cover + copy). This repository is also a WorkBuddy agent skill
> (skill definition in [`SKILL.md`](./SKILL.md)).

---

## 中文文档

### 它能做什么
- 输入一整部影片（或一批影片），输出约 10–30 分钟、信息密度高、带故事脉络片头与解说转场的精华版（实测 141min 长片 → 12.6min）；
- 自动交付 **B 站三件套**：成片、**爆款大字封面**（左图右双行大标题、白铺垫黄爆点，render_cover.py 模板+vision 五查）、标题简介标签文案，外加剪辑报告与生产台账；
- 配套 **21 个 Python 脚本**，覆盖摸底（全片 ASR + 接触表）→ 切点吸附 → 探针目核 → 切香肠式分段截取 → 百炼 TTS 解说 → 滚动解说卡 → 拼接 → 音画同步质检 → 水印 → 交付自检全流程；
- **v14.1 单会话全流程**：一个会话从读片到交付跑完一部片（已废除早期双模型 handoff/队列协议）；一切决策落盘到 `projects/<片名>/`，失败隔离、断点可续、批量可跑。

### 核心特性
- **切香肠式分段截取**：单命令同切视频/音频、解码重编码，从精确时点起，根除「关键帧回吸」导致的音画错位（A 类问题）。
- **帧网格量化归一化拼接**（`assemble.py --mode normalize`）：每段量化到整数帧、视频/音频硬裁等长后 concat 重编码，根除逐边界累积漂移（B 类问题，实测 ±0.2ms 零累积）。
- **切点吸附 / 切点探针 / 找字游戏双兜底**：尾音截断、台词切一半等顽疾的自动化根治。
- **品牌工业化**：故事脉络片头 prologue、3s 片头 / 5s 片尾、右上角水印，素材内置且可重渲染。
- **内容风控**：片源广告 / 二维码扫描、片头片尾硬排除（厂标 / 演职员字幕 / 片尾曲一律不进成片）。
- **交付质量闸**：数字自检（`check_delivery.py`）、音画同步三级验证（`verify_sync.py` + `qc_env_check.py`）。

### 目录结构
```
film-highlight-editor/
├── SKILL.md              # 技能定义（v14.1 单会话全流程，含完整工作流与已知坑）
├── README.md             # 本文件（中英文双语）
├── LICENSE               # MIT © 上海翔远工作室 · MilesYang
├── CHANGELOG.md          # 版本记录
├── .gitignore
├── .env.example          # 交付配置模板（仅占位，不含任何密钥）
├── scripts/              # 21 个配套脚本（详见 SKILL.md「配套脚本」表）
├── projects/             # 生产数据目录（README=章法规范；数据本体不入库）
├── brand/                # 品牌资产：logo / 水印 / 片头片尾视频 / 音效 + 构建脚本
├── models/               # 语音识别模型目录（见 models/README.md，二进制不入库）
└── examples/             # 数据格式示例（clips_snap / order 等）
```

### 配音引擎（默认推荐）
主力 TTS 走 `scripts/tts_bailian.py` = 阿里云百炼 **qwen3-tts-flash**，默认音色 **「燕铮莺 Bellona」**（作者听样定版推荐：女声、播报感清晰、叙事有温度，实测适合年代片/剧情片解说；一段话一段音频，断点续传+重试+manifest 记账）。想定制专属音色：推荐百炼 **cosyvoice-v3.5** 做声音复刻（3–10 秒样本即可克隆出你的 voice_id，经 DashScope voice-enrollment + SpeechSynthesizer 接入；两线音色表不通用）。百炼 key 申请见 [阿里云百炼](https://bailian.console.aliyun.com/)，新用户有免费额度。

### 环境依赖
- **ffmpeg** ≥ 4.x（须支持 libx264 / AAC；拼接质检用 ffprobe）。
- **Python** ≥ 3.11，建议使用隔离的虚拟环境（managed venv）。
- Python 依赖：`Pillow`、`numpy`、`requests`、`edge-tts`、`rapidocr_onnxruntime`、`vosk`。
- **语音识别模型** `vosk-model-small-cn-0.22`：解压后放到 `models/vosk-zh/`，下载方式见 [`models/README.md`](./models/README.md)。

### 安装
```bash
git clone https://github.com/JohnYang060424/film-highlight-editor.git
cd film-highlight-editor

# 1) 准备语音识别模型（详见 models/README.md）
#    解压 vosk-model-small-cn-0.22 到 models/vosk-zh/

# 2) 创建虚拟环境并安装依赖
python -m venv .venv && .venv/Scripts/activate     # Windows
#   source .venv/bin/activate                      # macOS / Linux
pip install Pillow numpy requests edge-tts rapidocr_onnxruntime vosk
```

### 快速开始
1. 生产数据放在仓库内 `projects/<片名>/`：`source/`（调研与台词本）、`work/`（中间产物）、`output/`（交付物）；原片本体放仓库外你的片源目录（GB 级不入库，路径记 `projects/batch_list.md` 台账）。目录章法见 [`projects/README.md`](./projects/README.md)。
2. 运行 `scripts/full_asr.py` 出全片带时间戳台词本 + `scripts/contact_sheet.py` 摸底抽帧。
3. 按 [`SKILL.md`](./SKILL.md) 的「流程」逐步执行：广告扫描 → 联网研究定骨架 → 切点吸附 → 探针目核 → 分段截取 → TTS → 转场 → 拼接 → 质检 → 水印 → 交付自检。
4. 交付（对象存储 / 通知）为**可选**，详见下方「配置」。

### 配置（交付步骤，全部可选）
交付与通知的 URL、Key 等**一律走环境变量**，绝不写死在脚本或文档里。复制 `.env.example` 为 `.env` 后填写：

```bash
cp .env.example .env
# 编辑 .env：仅当启用对象存储 / 通知时才填写；留空则跳过对应步骤
```

- `DASHSCOPE_API_KEY`：阿里云百炼 key（**主力配音 tts_bailian.py 必需**；申请见百炼控制台）。
- `OSS_*`：对象存储（阿里云 OSS / AWS S3 / 兼容 S3 的服务）交付前缀与凭证。
- `NOTIFY_*`：交付后通知（私人剪贴板 / 消息机器人等）的目标与凭证。

### 安全与隐私
本仓库**不含任何密钥、AccessKey、私有 URL 或用户私有内容**。原始技能中的 OSS 凭证、私人剪贴板 API Key 与私有域名已被移除；相关能力改为通过环境变量注入。模型二进制（约 66MB）按社区惯例不入库，改为下载说明。

### 许可证与署名
[MIT License](./LICENSE) © 2026 **上海翔远工作室（Shanghai Xiangyuan Studio）· MilesYang**。

---

## English Documentation

### What it does
- Takes a full movie (or a batch) and produces a ~10–30 min high-density highlight cut with a story-prologue
  and narration transitions (field test: 141-min feature → 12.6-min cut, zero A/V drift).
- Auto-delivers the **Bilibili three-piece set**: final video, cover, title/description/tags copy, plus an
  editing report and a production ledger.
- Ships **21 Python scripts**: scouting (full-film ASR + contact sheets) → cut snapping → probe review →
  sausage-style segment cutting → Bailian TTS narration → scrolling caption cards → assembly → A/V sync QA →
  watermark → delivery self-check.
- **v14.1 single-session pipeline**: one agent session runs a film end-to-end (the earlier two-model
  handoff/queue protocol is retired); every decision is persisted under `projects/<film>/` for failure
  isolation, resumability and batching.

### Voice engine (default recommendation)
Primary TTS is `scripts/tts_bailian.py` on Aliyun Bailian **qwen3-tts-flash**, default voice **「燕铮莺 Bellona」**
(the author-auditioned pick: a clear, warm female narration voice that suits period/drama films). Want your own
voice? We recommend Bailian **cosyvoice-v3.5** voice cloning (a 3–10 s sample yields your own voice_id via
DashScope voice-enrollment + SpeechSynthesizer; the two engines' voice tables are not interchangeable).

### Key features
- **Sausage-style segment cutting**: one command cuts video+audio together, decode-reencode from the exact
  timestamp — eliminates A-class A/V drift caused by keyframe pull-back.
- **Frame-grid quantized normalized assembly** (`assemble.py --mode normalize`): each segment quantized to
  integer frames, video/audio hard-trimmed to equal length, then concat-reencoded — eliminates B-class
  cumulative drift (measured ±0.2ms, zero accumulation).
- **Cut snapping / cut probe / "word-game" dual fallback**: automated fixes for tail-speech truncation and
  mid-line cuts.
- **Brand industrialization**: story prologue, 3s intro / 5s outro, top-right watermark — assets included and re-renderable.
- **Content safety**: source ad / QR-code scanning, hard exclusion of intros/outros (studio logos, credits,
  end themes never enter the cut).
- **Delivery gates**: numeric self-check (`check_delivery.py`), three-level A/V sync verification
  (`verify_sync.py` + `qc_env_check.py`).

### Repository layout
See the tree above. `SKILL.md` is the authoritative workflow + known-pitfalls doc; `scripts/` holds the 20 tools.

### Requirements
- **ffmpeg** ≥ 4.x (libx264 / AAC; ffprobe for QA).
- **Python** ≥ 3.11 in an isolated venv.
- Python deps: `Pillow`, `numpy`, `requests`, `edge-tts`, `rapidocr_onnxruntime`, `vosk`.
- **ASR model** `vosk-model-small-cn-0.22`: extract into `models/vosk-zh/` (see [`models/README.md`](./models/README.md)).

### Install
```bash
git clone https://github.com/JohnYang060424/film-highlight-editor.git
cd film-highlight-editor

# 1) Prepare the ASR model (see models/README.md)
#    extract vosk-model-small-cn-0.22 into models/vosk-zh/

# 2) Create venv and install deps
python -m venv .venv && source .venv/bin/activate   # macOS / Linux
#   .venv\Scripts\activate                            # Windows
pip install Pillow numpy requests edge-tts rapidocr_onnxruntime vosk
```

### Quick start
1. Production data lives in-repo under `projects/<film>/` (`source/` research, `work/` intermediates, `output/`
   deliverables); the GB-size original stays outside the repo (path recorded in `projects/batch_list.md`).
   See [`projects/README.md`](./projects/README.md) for the layout spec.
2. Run `scripts/full_asr.py` for a timestamped transcript and `scripts/contact_sheet.py` to scout frames.
3. Follow the "流程 / Workflow" section in [`SKILL.md`](./SKILL.md): ad scan → research & skeleton → cut snap →
   probe review → segment cut → TTS → transition → assemble → QA → watermark → delivery self-check.
4. Delivery (object storage / notify) is **optional** — see Configuration below.

### Configuration (delivery steps, all optional)
Delivery / notify URLs and keys are injected **only via environment variables**, never hardcoded.
Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
# edit .env: fill only if you enable object-storage / notify; leave blank to skip those steps
```

- `DASHSCOPE_API_KEY`: Aliyun Bailian key (**required** by the primary TTS `tts_bailian.py`).
- `OSS_*`: object storage (Aliyun OSS / AWS S3 / S3-compatible) delivery prefix and credentials.
- `NOTIFY_*`: post-delivery notify (private clipboard / bot) target and credentials.

### Security & privacy
This repository contains **no secrets, AccessKeys, private URLs, or private user content**. The original OSS
credentials, private-clipboard API key, and private domains have been removed; those capabilities are now
driven by environment variables. The ASR model binary (~66MB) is excluded from the repo per community practice
and provided as a download.

### License & attribution
[MIT License](./LICENSE) © 2026 **Shanghai Xiangyuan Studio · MilesYang**.
