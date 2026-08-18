# 语音识别模型 / ASR Model

`tail_guard.py`（找字游戏双兜底，尾音截断根治）依赖中文语音识别模型 **vosk-model-small-cn-0.22**。

> `tail_guard.py` (the "word-game" dual fallback that fixes tail-speech truncation) needs the Chinese ASR
> model **vosk-model-small-cn-0.22**.

该模型为第三方开源模型（Apache 2.0），体积约 66MB，**不纳入本仓库**。请自行下载后放到本目录：

> The model is a third-party open-source model (Apache 2.0), ~66MB, and is **not committed** to this repo.
> Download it and place it here:

```
models/vosk-zh/        <- 解压后的模型目录 / extracted model directory
├── am/
├── conf/
├── graph/
├── ivector/
├── README
└── ...
```

## 下载 / Download

从官方源获取 `vosk-model-small-cn-0.22`（alphacep / Alpha Cephei 发布的 Kaldi 模型）：

> Get `vosk-model-small-cn-0.22` from the official source (Kaldi model published by alphacep / Alpha Cephei):

- 官网模型页 / Official model page: https://alphacephei.com/vosk/models
- 或 / or via `vosk` 工具链下载（按官方文档）/ via the `vosk` toolchain (follow official docs)

下载后解压，将目录重命名为 `vosk-zh` 并放到 `models/` 下：

> After downloading, extract and rename the directory to `vosk-zh`, then place it under `models/`:

```bash
# 示例（请以官方最新链接为准 / example — use the official latest link）
curl -L -o vosk-model-small-cn-0.22.zip https://alphacephei.com/vosk/model/vosk-model-small-cn-0.22.zip
unzip vosk-model-small-cn-0.22.zip
mv vosk-model-small-cn-0.22 ../film-highlight-editor/models/vosk-zh
```

## 说明 / Notes
- 模型名是 `vosk-model-small-cn-0.22`（不是 `zh`），解压后重命名为 `vosk-zh` 以匹配脚本路径 `../models/vosk-zh`。
- 若模型缺失，`tail_guard.py` 会自动跳过 ASR 层（仅保留 OCR 层），不影响其他环节。
- 该模型仅用于判断「片段结尾是否有人在说话」，不要求转写准确。

> - The model name is `vosk-model-small-cn-0.22` (not `zh`); rename to `vosk-zh` to match the script path.
> - If the model is missing, `tail_guard.py` skips the ASR layer automatically (OCR layer remains); other steps are unaffected.
> - The model only detects "is someone speaking at the segment tail" — exact transcription is not required.
