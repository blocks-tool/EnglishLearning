# 英语学习助手（Qt 桌面版）

两个可独立运行的离线桌面应用，共用一个启动台：

- **单词本学习助手**：单词本管理、批量导入、自动释义与例句、三档掌握状态、卡片式学习。
- **口语学习助手**：分组树管理文章/音频/视频，文章朗读与跟读评分，音视频字幕与逐句跟读。

界面基于 **PyQt5（Qt 5）**，朗读语音使用 **Piper TTS**（本地神经网络模型），
识别、评测、词典全部离线运行。

## 快速开始

```bat
pip install -r requirements.txt
python main.py
```

也可以直接双击：

- `启动.bat`：打开启动台
- `启动单词本.bat`：只打开单词本助手
- `启动口语.bat`：只打开口语助手

运行前请确认以下本地资源已就位（见「数据与模型」）：

- `data/ecdict.db`：ECDICT 离线词典（音标、中文释义），
  下载：<https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip>
  （解压后将其中的 `ecdict.db` 放入 `data/` 目录）
- `voices/*.onnx` + `*.onnx.json`：Piper 语音模型
- `data/models/vosk-model-small-en-us-0.15/`：字幕识别模型（缺失时生成字幕会尝试自动下载）

## 单词本学习助手

- **单词本管理**：新建、重命名、删除；名称唯一，按创建顺序排列。
- **批量导入**：弹框内粘贴多行单词，自动去重；逐个查询 ECDICT 生成音标、
  中文释义，并生成例句卡片。
- **例句来源**：内置六级真题与英文期刊（The Economist / Nature / BBC News 等）
  例句库，命中时标注真实来源；未命中时按词性生成模板例句，并注明「本地生成」。
- **掌握状态**：陌生 / 模糊 / 熟悉，表格双击可循环切换，右键可精确标记。
- **学习模式**：开始学习时勾选要练的状态，默认「陌生 + 模糊」；也可全量学习。
  卡片支持发音、显示释义与例句、快捷键 `1/2/3` 标记、空格/方向键翻卡。

## 口语学习助手

- **学习库树**：分组 → 文章 / 音频 / 视频，支持新建、重命名、删除、右键导入。
- **文章**：粘贴文本导入；按句朗读（Piper 全文合成），可调阅读速度、
  暂停/恢复、向前/向后 n 秒（默认 5 秒），点击句子可跳转。
- **文章跟读**：自动按英文句号断句；逐句播放原音 → 麦克风跟读 → 自动评分，
  并列出得分偏低的单词及音标。
- **音频 / 视频**：可调倍速、暂停/恢复、±n 秒；音视频可离线生成字幕
  （Vosk），也可导入 SRT；字幕支持字号与双语/英文/中文显示。
- **音视频跟读**：跟读面板同步显示字幕与播放器，可按句播放、录音、评分。
- **格式兼容**：若系统缺少 MP4（H.264/AAC）解码器，应用会用 ffmpeg 自动
  转成可播放的 WMV/WAV（结果缓存在 `data/cache/media`，时间轴不变）。

## 目录结构

```
main.py                 启动台
vocab/                  单词本助手（窗口、导入弹框、学习卡）
speaking/               口语助手（分组树、文章视图、媒体视图、跟读窗口）
core/
  paths.py              统一目录
  db_vocab.py           单词本数据库（data/app.db）
  db_speaking.py        口语分组与素材数据库（data/speaking.db）
  dictionary.py         ECDICT 查询
  examples.py           例句库与例句生成
  tts.py                Piper 合成与缓存
  audio.py              录音、波形、MFCC/DTW 发音评测
  asr.py                Vosk 字幕识别、ffmpeg 音频提取、SRT 解析
  media.py              媒体格式兼容转码
  textutil.py           断句与时间格式化
  tasks.py              线程池后台任务
  ui.py                 主题、通用控件
legacy_ctk/             早期 CustomTkinter 版本（仅存档，不再使用）
```

## 数据与模型

| 路径 | 说明 |
| --- | --- |
| `data/app.db` | 单词本与单词数据 |
| `data/speaking.db` | 分组、文章、音视频素材与字幕 |
| `data/ecdict.db` | ECDICT 离线词典（表 `stardict`），[下载](https://github.com/skywind3000/ECDICT/releases/download/1.0.28/ecdict-sqlite-28.zip)后解压放入 |
| `voices/en_US-hfc_female-medium.onnx` | Piper 英文语音模型 |
| `data/models/vosk-model-small-en-us-0.15/` | 离线字幕识别模型 |
| `data/cache/tts/` | Piper 合成缓存 |
| `data/cache/record/` | 跟读录音（仅本地保存） |
| `data/cache/media/` | 兼容格式转码缓存 |
| `data/media/` | 导入的音频 / 视频副本 |

## 发音评分说明

评分不使用云端服务：把参考音与用户录音分别提取 MFCC 特征，做 DTW 对齐，
综合频谱相似度、时长比例与录音能量得到总分；再按单词时长切分对齐结果，
给出低分单词与 IPA。分数 60 以下建议放慢语速、逐词跟读。

## 说明

- 全部功能离线可用；首次生成字幕若缺少 Vosk 模型，会提示并尝试下载（约 40 MB）。
- 录音只保存在本地 `data/cache/record`，不会上传。
- 旧版 CustomTkinter 代码已移入 `legacy_ctk/` 作为存档，与当前版本互不依赖。
