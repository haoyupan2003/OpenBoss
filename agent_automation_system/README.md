# OpenBoss

> 主从架构分布式 Agent 自动化执行系统

## 简介

OpenBoss 是一个基于主从架构的分布式 Agent 自动化执行系统，通过 Master Agent 统一调度多个 Sub-Agent（PM / Dev / QA / Validate），利用 tmux 管理终端会话，驱动 Claude Code CLI 完成从需求分析到代码交付的全流程自动化。

## 核心特性

- **主从架构**：Master Agent 负责任务调度，Sub-Agent 负责具体执行
- **tmux 集成**：通过 tmux 管理多个 Agent 终端会话
- **DAG 调度**：基于任务依赖关系自动分析并行度，最大化执行效率
- **BDD 驱动**：Given-When-Then 格式精化需求，TDD 闭环验证
- **Harness 约束**：通过规则文件约束 Agent 行为，确保输出质量
- **Git 集成**：每个任务独立提交，格式化 commit message
- **OpenClaw 监控**：进程检测、超时处理、资源监控、告警推送

## 项目结构

```
OpenBoss/
├── agent_automation_system/      # 核心 Python 包
│   ├── __init__.py
│   ├── models/                   # 数据模型（Task, Progress, Memory）
│   ├── tmux_manager/             # tmux 集成模块
│   ├── git_manager/              # Git 版本管理模块
│   ├── agents/                   # Agent 实现（Master / Sub-Agent）
│   ├── scheduler/                # DAG 调度器
│   ├── monitor/                  # OpenClaw 监控模块
│   └── web/                      # FastAPI Web 后端
├── data/                         # 运行时数据（task.json, progress.txt, memory.md）
├── logs/                         # 日志目录
├── docs/                         # 文档
├── sample/                       # 示例文件
└── tests/                        # 测试
```

## 快速开始

```bash
# 安装依赖
pip install -e .

# 或使用 Makefile
make install
```

## 技术栈

- Python 3.11+
- libtmux / pydantic / GitPython / psutil
- FastAPI / uvicorn / websockets
- pytest / pytest-asyncio / Playwright

## 许可证

MIT License
