# Changelog

## v2.0 (2026-09-07)
- **v14.1 单会话全流程**：废除双模型（max/flash）handoff 与 batch_queue 文件传递协议——一个会话从读片跑到交付；失败隔离/断点续跑改由 `projects/batch_list.md` 台账 + 磁盘产物承担。
- **工业化目录收敛进仓库**：生产数据统一 `projects/<片名>/{source,work,output}` 三级（规范见 `projects/README.md`，数据本体 .gitignore 不入库）。
- **配音引擎换代**：主力从 edge-tts 换成阿里云百炼 `tts_bailian.py`（qwen3-tts-flash，默认音色「燕铮莺 Bellona」，作者听样定版）；推荐用 cosyvoice-v3.5 声音复刻定制音色（voice-enrollment → SpeechSynthesizer）。`tts_batch.py`（edge-tts）保留为离线备胎。
- 新增脚本：`full_asr.py`（vosk 全片带时间戳台词本，中文路径自动 junction）、`tts_bailian.py`（逐帧剥头拼 PCM、断点续传、manifest 记账）。脚本 19→20（删除过时 `cut_segments.py`、`render_brand_v1_legacy.py`）。
- `cut_sync.py` 新增 `--vf` letterbox 透传（宽银幕 1920×808 源片不拉伸）；`tail_guard.py` 修 vosk 非 ASCII 路径 + 新增 `--brand-ok` 品牌水印白名单；`check_delivery.py` 修原片时长误判。
- SKILL.md §11 坑位大扩充（v14.1 实测 11 条：Bellona≠cosyvoice 418、qwen3-tts 流式帧假时长、60s 墙锚点系统性偏移必三步定剪、drawtext segfault 走 PIL 等）。
- 实测战果：冯小刚《抓特务》141min → 12.6min 精华版，音画漂移 0.000s，verify_sync L1/L2 全 PASS。

---

## v1.0 (2026-08-18)
- 首次公开开源发布（first public open-source release）。
- 包含 v13.5 技能：双模型（强/弱）分工批处理 handoff 协议。
- 收录 19 个配套脚本、品牌资产（logo / 水印 / 片头片尾 / 音效 + 构建脚本）。
- 语音识别模型 `vosk-model-small-cn-0.22` 改为下载说明（二进制不入库，约 66MB）。
- **安全脱敏**：移除原始技能中的 OSS AccessKey/Secret、私人剪贴板 API Key 与私有域名；对象存储与通知交付改为通过环境变量（`.env.example`）配置，文档与脚本中不留任何密钥或私有 URL。
- 文档中文化 + 英文双语（README / LICENSE / CHANGELOG）。

---

## v1.0 (2026-08-18) — English
- First public open-source release.
- Ships the v13.5 skill with the two-model (strong/weak) handoff batch protocol.
- Includes 19 helper scripts and brand assets (logo / watermark / intro & outro / audio + build scripts).
- ASR model `vosk-model-small-cn-0.22` provided as a download (binary excluded from repo, ~66MB).
- **Security sanitization**: removed the original OSS AccessKey/Secret, private-clipboard API key and private
  domains; object-storage and notify delivery now use environment variables (`.env.example`) — no secrets or
  private URLs remain in docs or scripts.
- Bilingual docs (README / LICENSE / CHANGELOG) in Chinese and English.
