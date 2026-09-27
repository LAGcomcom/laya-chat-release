# Laya 聊天决策助手 - 一键部署版

双击 `install.bat` 即可全自动安装（Python 环境 → 依赖 → 模型 → 配置向导），装完双击 `start.bat` 启动。

## 它是什么

聊天窗口旁挂的回复辅助：本地 OCR 读屏 → **本地 Laya 模型**判断意图/情绪/紧张度 → 大模型起草 3 条候选回复 → Laya 排序 → 一键填入输入框，**发送永远手动**。

判断环节跑在你自己显卡上（免费、离线、隐私不出本机），只有起草走你自己的 API key（几厘钱一条）。

## 环境要求

- Windows 10 1903+ / 11
- NVIDIA 显卡（GTX 1060+，无 N 卡自动退回 CPU 模式，速度变慢）
- 磁盘空间约 8GB（PyTorch ~2.5GB + 模型 ~3.5GB）
- 一个 OpenAI 兼容 API key（商汤 SenseNova / DeepSeek 官方均可，安装时填一次）

## 文件说明

| 文件 | 作用 |
|---|---|
| install.bat | 一键安装入口（自动装 Python，如缺失） |
| install.py | 安装主逻辑（可重复运行，已完成的步骤自动跳过） |
| start.bat | 安装完成后生成，双击启动助手 |
| jev-chat-windows/ | 助手程序本体（OCR 悬浮窗 + 三段式决策引擎） |

## 常见问题

- **装到一半断了？** 重新双击 install.bat，断点续装。
- **想换起草模型/key？** 删掉 `jev-chat-windows/config.json` 里的 `_key_saved` 字段再跑 install.bat，或直接在助手设置页里改。
- **判断模型能不能更准？** 可以，用你自己的对话数据微调 Laya（RLCD），准确率还能再上一个台阶。
