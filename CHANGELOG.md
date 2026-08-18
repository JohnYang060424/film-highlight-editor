# Changelog

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
