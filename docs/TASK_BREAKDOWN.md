# OpenBoss 任务拆解清单

> 基于 PRD V2.0（主从架构分布式 Agent 自动化执行系统）的精细任务拆解
> 生成时间：2026-05-14
> 总计：**120 个原子任务**，横跨 4 个迭代周期

---

## 任务编号说明

- `P1-` = Iteration 1（核心框架）
- `P2-` = Iteration 2（多Agent调度 + BDD）
- `P3-` = Iteration 3（Web面板 + 监控告警）
- `P4-` = Iteration 4（测试 + 优化 + 部署）

每个任务遵循 TDD 原则：先写测试 → 实现 → 验证通过 → Git 提交

---

## ═══ Iteration 1：核心框架搭建（2 周）═══

### 阶段 1.0：项目初始化与基础设施

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-001 | 创建 Python 项目结构：agent_automation_system/ 目录、__init__.py、README.md | P0 | 0.5h | - |
| P1-002 | 创建 requirements.txt：libtmux, pydantic, pyyaml, gitpython, psutil, fastapi, uvicorn, websockets, pytest, pytest-asyncio | P0 | 0.5h | - |
| P1-003 | 创建 pyproject.toml：项目元数据、依赖声明、开发依赖 | P0 | 0.5h | - |
| P1-004 | 创建 .env.example 环境变量模板（覆盖 PRD 10.1 所有配置） | P0 | 0.5h | - |
| P1-005 | 创建 .gitignore（Python、IDE、.env、__pycache__、logs/） | P0 | 0.5h | - |
| P1-006 | 创建 Makefile：install / test / lint / run / clean 命令 | P1 | 0.5h | P1-002 |
| P1-007 | 配置 pytest：创建 pytest.ini / conftest.py 基础配置 | P0 | 0.5h | P1-002 |

### 阶段 1.1：数据模型与文件系统层

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-008 | 创建 data/ 目录结构：data/backup/ 子目录初始化脚本 | P0 | 0.5h | - |
| P1-009 | 创建 logs/ 目录结构及 .gitkeep 占位文件 | P0 | 0.5h | - |
| P1-010 | 定义 Task 数据模型：pydantic model（id, title, description, bdd, test_script, dependencies, suggested_role, priority, status 等） | P0 | 1h | - |
| P1-011 | 定义 TaskJSON 数据模型：project_name, created_by, created_at, total_tasks, tasks 列表 | P0 | 0.5h | P1-010 |
| P1-012 | 定义 ProgressEntry 数据模型：task_id, status, role, started, finished, git_sha, git_msg, error, retry | P0 | 0.5h | P1-010 |
| P1-013 | 实现 task.json 读写器：TaskFileManager.read_tasks() / write_tasks() | P0 | 1.5h | P1-011 |
| P1-014 | 实现 progress.txt 读写器：ProgressManager.read_progress() / write_entry() / update_status() | P0 | 1.5h | P1-012 |
| P1-015 | 实现 memory.md 读写器：MemoryManager.read() / append() / search() | P1 | 1h | - |
| P1-016 | 实现日志管理器：LogManager.write_log(level, agent_id, message)，自动创建按日期分割的日志文件 | P0 | 1h | - |
| P1-017 | 编写 TaskFileManager 单元测试 | P0 | 1h | P1-013 |
| P1-018 | 编写 ProgressManager 单元测试 | P0 | 1h | P1-014 |
| P1-019 | 编写 MemoryManager 单元测试 | P1 | 1h | P1-015 |
| P1-020 | 编写 LogManager 单元测试 | P0 | 1h | P1-016 |

### 阶段 1.2：tmux 集成模块

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-021 | 实现 TmuxManager 基础类：检测 tmux 可用性、获取 tmux 版本 | P0 | 1h | - |
| P1-022 | 实现会话管理：create_session(name) / kill_session(name) / list_sessions() / session_exists(name) | P0 | 1.5h | P1-021 |
| P1-023 | 实现窗口管理：create_window(session, name, cmd) / kill_window(session, window) / list_windows(session) | P0 | 1.5h | P1-021 |
| P1-024 | 实现命令发送：send_keys(session, window, keys) / send_command(session, window, cmd) | P0 | 1h | P1-023 |
| P1-025 | 实现终端输出捕获：capture_pane(session, window) / capture_pane_history(session, window, lines) | P0 | 1h | P1-023 |
| P1-026 | 实现 Agent 窗口命名规范：format_agent_window_name(role, seq) → "agent_{role}_{seq}" | P1 | 0.5h | P1-023 |
| P1-027 | 编写 TmuxManager 会话管理单元测试（使用 mock） | P0 | 1h | P1-022 |
| P1-028 | 编写 TmuxManager 窗口管理单元测试（使用 mock） | P0 | 1h | P1-023 |
| P1-029 | 编写 TmuxManager 命令发送和输出捕获单元测试 | P0 | 1h | P1-024, P1-025 |

### 阶段 1.3：Git 版本管理模块

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-030 | 实现 GitManager 基础类：初始化仓库、检测工作目录状态 | P0 | 1h | - |
| P1-031 | 实现 git add + commit：commit_changes(task_id, role, description)，格式 [task-{id}] {role}: {description} | P0 | 1h | P1-030 |
| P1-032 | 实现 git status 检查：has_uncommitted_changes() / get_last_commit_hash() | P1 | 0.5h | P1-030 |
| P1-033 | 实现 git diff 查看：get_diff_since_commit(hash) | P1 | 0.5h | P1-030 |
| P1-034 | 实现 Git 操作重试机制：失败最多重试 3 次 | P0 | 0.5h | P1-031 |
| P1-035 | 编写 GitManager 单元测试（使用临时 git 仓库 fixture） | P0 | 1.5h | P1-031, P1-032 |

### 阶段 1.4：Sub-Agent 基类

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-036 | 设计 SubAgent 基类接口：execute(task) → SubAgentResult | P0 | 1h | P1-010 |
| P1-037 | 实现 SubAgent 生命周期管理：initialize() → execute() → verify() → commit() → cleanup() | P0 | 2h | P1-036 |
| P1-038 | 实现 Harness 约束加载：load_harness(harness_path) → 解析 md 文件为约束规则 | P0 | 1h | - |
| P1-039 | 实现 Sub-Agent 角色注入：inject_role(role_name, task_description, harness_content) | P0 | 1h | P1-037, P1-038 |
| P1-040 | 实现 Claude Code CLI 启动：start_cli(session, window, prompt) 通过 tmux send-keys | P0 | 1.5h | P1-024 |
| P1-041 | 实现执行结果检测：监控 CLI 输出判断任务完成/失败 | P0 | 2h | P1-040 |
| P1-042 | 实现超时控制：task 超时后终止 CLI 进程 | P0 | 1h | P1-041 |
| P1-043 | 编写 SubAgent 基类单元测试 | P0 | 1.5h | P1-037 |

### 阶段 1.5：Master Agent 核心

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-044 | 设计 MasterAgent 类：接收需求 → 创建 PM Sub-Agent → 接收 task.json → 调度 Sub-Agent | P0 | 1.5h | P1-037 |
| P1-045 | 实现 Master Agent 启动流程：注入 main-rules.md、初始化 tmux 主会话、启动 CLI | P0 | 1.5h | P1-044, P1-022 |
| P1-046 | 实现任务 DAG 分析：build_dag(tasks) → 依赖图、拓扑排序、并行度分析 | P0 | 2h | P1-011 |
| P1-047 | 实现调度策略：select_next_task(dag, completed_ids) → 考虑依赖和优先级 | P0 | 1.5h | P1-046 |
| P1-048 | 实现 Sub-Agent 创建与委派：dispatch_task(task) → 创建 tmux 窗口、注入角色、发送指令 | P0 | 2h | P1-039, P1-023 |
| P1-049 | 实现执行进度监控：poll_sub_agent_status() → 检查 progress.txt 和 task.json 更新 | P0 | 1.5h | P1-014, P1-013 |
| P1-050 | 实现失败处理：on_task_failed(task) → 暂停任务流、记录错误、通知 OpenClaw | P0 | 1.5h | P1-044 |
| P1-051 | 实现断点恢复：restore_from_progress() → 读取 progress.txt 确定断点、恢复调度 | P0 | 2h | P1-014 |
| P1-052 | 编写 DAG 分析单元测试：各种依赖图场景 | P0 | 1h | P1-046 |
| P1-053 | 编写调度策略单元测试：优先级、并行度、依赖约束 | P0 | 1h | P1-047 |
| P1-054 | 编写断点恢复单元测试：模拟各种中断场景 | P0 | 1h | P1-051 |

### 阶段 1.6：Harness 规则文件

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-055 | 编写 harness/main-rules.md：Master Agent 编排者/老板角色约束（按 PRD 6.4.1） | P0 | 1h | - |
| P1-056 | 编写 harness/sub-rules.md：Sub-Agent 通用角色约束（按 PRD 6.4.2） | P0 | 1h | - |
| P1-057 | 编写 harness/validate-rules.md：验证规则（测试验收标准） | P1 | 0.5h | - |
| P1-058 | 编写 harness/pm-rules.md：Product Manager Agent 专属约束（BDD 沟通规则） | P1 | 0.5h | - |
| P1-059 | 编写 harness/dev-rules.md：Senior Developer Agent 专属约束（编码规范、提交规则） | P1 | 0.5h | - |
| P1-060 | 编写 harness/qa-rules.md：Test Engineer Agent 专属约束（测试编写规范） | P1 | 0.5h | - |

### 阶段 1.7：集成验证

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P1-061 | 端到端冒烟测试：Master Agent 启动 → 创建 1 个 Sub-Agent → 执行简单任务 → 更新 progress.txt | P0 | 3h | P1-045, P1-048 |
| P1-062 | 集成测试：tmux 会话创建/销毁 + CLI 启动/关闭 完整流程 | P0 | 2h | P1-022, P1-040 |
| P1-063 | 集成测试：文件系统状态流转（task.json → progress.txt → memory.md） | P0 | 1.5h | P1-013, P1-014, P1-015 |
| P1-064 | 集成测试：Git 提交流程验证（代码变更 → commit → hash 记录） | P0 | 1.5h | P1-031 |

---

## ═══ Iteration 2：多 Agent 并行调度 + BDD 工作流（2 周）═══

### 阶段 2.1：Product Manager Agent

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P2-001 | 实现 ProductManagerAgent 类：继承 SubAgent 基类，注入 pm-rules.md | P0 | 1h | P1-037 |
| P2-002 | 实现 BDD 需求精炼：refine_requirement(raw_need) → Given-When-Then 结构化描述 | P0 | 2h | P2-001 |
| P2-003 | 实现需求沟通循环：communicate_with_user(bdd_draft) → 用户反馈 → 迭代修改 → 确认 | P0 | 2h | P2-002 |
| P2-004 | 实现任务拆解：decompose_requirement(confirmed_bdd) → 原子 task 列表 | P0 | 2h | P2-003 |
| P2-005 | 实现 task.json 生成：generate_task_json(tasks) → 完整的 task.json 文件 | P0 | 1.5h | P2-004, P1-013 |
| P2-006 | 实现测试脚本编写：generate_test_script(task) → 根据任务类型生成 Playwright/API/数据测试脚本 | P0 | 2h | P2-004 |
| P2-007 | 编写 ProductManagerAgent 单元测试：BDD 生成、任务拆解、task.json 格式 | P0 | 1.5h | P2-005 |

### 阶段 2.2：Specialized Sub-Agents

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P2-008 | 实现 SeniorDeveloperAgent：继承 SubAgent 基类，注入 dev-rules.md，专注于编码实现 | P0 | 1.5h | P1-037 |
| P2-009 | 实现 TestEngineerAgent：继承 SubAgent 基类，注入 qa-rules.md，专注于测试验证 | P0 | 1.5h | P1-037 |
| `P2-010` | 实现 SeniorScreenwriterAgent：继承 SubAgent 基类，专注于文案创作 | P1 | 1h | P1-037 |
| P2-011 | 实现 DataAnalystAgent：继承 SubAgent 基类，专注于数据处理 | P1 | 1h | P1-037 |
| P2-012 | 实现 BrowserTaskAgent：继承 SubAgent 基类，集成 Playwright CLI 进行浏览器操作 | P1 | 1.5h | P1-037 |
| P2-013 | 实现 APIRequestAgent：继承 SubAgent 基类，专注于 API 调用和接口测试 | P1 | 1h | P1-037 |
| P2-014 | 实现 Agent 工厂：AgentFactory.create(role_name) → 根据角色名创建对应 Sub-Agent 实例 | P0 | 1h | P2-008~P2-013 |
| P2-015 | 编写 AgentFactory 单元测试：角色创建、角色映射、无效角色处理 | P0 | 1h | P2-014 |

### 阶段 2.3：并行调度引擎

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P2-016 | 实现并行任务调度器：ParallelScheduler，基于 DAG 并行分发无依赖的 task | P0 | 2h | P1-046 |
| P2-017 | 实现并发控制：Semaphore 限制最大并发 Sub-Agent 数量（可配置 MAX_CONCURRENT_AGENTS） | P0 | 1.5h | P2-016 |
| P2-018 | 实现任务队列管理：TaskQueue，FIFO + 优先级排序 + 依赖过滤 | P0 | 1.5h | P2-016 |
| P2-019 | 实现并行执行监控：监控多个 Sub-Agent 同时运行的状态 | P0 | 2h | P2-016 |
| P2-020 | 实现高风险任务排序：标识数据库迁移/架构变更类 task，延迟执行 | P1 | 1h | P2-018 |
| P2-021 | 编写 ParallelScheduler 单元测试：2-agent 并行、3-agent 并行、依赖阻塞 | P0 | 1.5h | P2-016 |

### 阶段 2.4：BDD + TDD 闭环

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P2-022 | 实现 BDD 验证器：BDDValidator.verify(task_result, bdd_spec) → pass/fail | P0 | 1.5h | P1-010 |
| P2-023 | 实现测试运行器：TestRunner.execute(test_script_path) → 运行 Playwright/pytest 测试 | P0 | 2h | - |
| P2-024 | 实现测试结果解析：parse_test_output(output) → 统一结构（passed, failed, errors） | P0 | 1h | P2-023 |
| P2-025 | 实现 TDD 闭环：Sub-Agent 完成编码 → 运行测试 → 测试通过才 commit → 否则回退 | P0 | 2h | P2-023, P1-031 |
| P2-026 | 编写 BDDValidator 单元测试：各种 Given-When-Then 场景 | P0 | 1h | P2-022 |
| P2-027 | 编写 TestRunner 单元测试：模拟测试通过/失败场景 | P0 | 1h | P2-023 |

### 阶段 2.5：Git 集成完善

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P2-028 | 实现每个 task 完成后自动 git commit：Sub-Agent 成功 → commit → 更新 progress.txt | P0 | 1h | P1-031, P1-014 |
| P2-029 | 实现 commit message 格式化：[task-{id}] {role}: {description}，与 PRD 4.7 一致 | P0 | 0.5h | P2-028 |
| P2-030 | 实现失败时不 commit：测试失败 → 记录错误 → 更新 task.json 状态 → 不 commit | P0 | 0.5h | P2-025 |
| P2-031 | 实现执行报告生成：generate_execution_report() → 包含每个 task 的状态、commit hash、执行时间 | P1 | 1.5h | P1-014, P1-013 |
| P2-032 | 编写 Git 集成场景测试：成功 commit / 失败不 commit / 重试 commit | P0 | 1h | P2-028 |

---

## ═══ Iteration 3：Web 管理面板 + 监控告警（2 周）═══

### 阶段 3.1：Web 后端 API

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-001 | 创建 FastAPI 应用骨架：app/main.py、路由注册、CORS 配置 | P0 | 1h | - |
| P3-002 | 实现 WebSocket 连接管理：ConnectionManager，支持多客户端实时推送 | P0 | 2h | P3-001 |
| P3-003 | 实现 Agent 状态 API：GET /api/agents → 返回所有 Agent 实时状态（从 progress.txt + tmux 读取） | P0 | 1.5h | P3-001 |
| P3-004 | 实现任务进度 API：GET /api/tasks → 返回 task.json + progress.txt 合并数据 | P0 | 1.5h | P3-001 |
| P3-005 | 实现任务详情 API：GET /api/tasks/{id} → 单个任务的完整信息和执行历史 | P1 | 1h | P3-004 |
| P3-006 | 实现需求提交 API：POST /api/requirements → 接收用户原始需求并启动 PM Agent | P0 | 1.5h | P3-001 |
| P3-007 | 实现 BDD 确认 API：POST /api/bdd/confirm → 用户确认 BDD 描述 | P0 | 1h | P3-001 |
| P3-008 | 实现 BDD 修改 API：POST /api/bdd/feedback → 用户反馈修改 BDD | P1 | 1h | P3-007 |
| P3-009 | 实现终端输出 API：GET /api/terminal/{agent_id} → 返回 tmux 终端实时输出 | P0 | 1.5h | P3-001 |
| P3-010 | 实现指令下发 API：POST /api/terminal/{agent_id}/command → 向指定 Agent 终端发送指令 | P0 | 1h | P3-009 |
| P3-011 | 实现告警历史 API：GET /api/alerts → 返回历史告警记录 | P1 | 1h | P3-001 |
| P3-012 | 实现修复方案提交 API：POST /api/recovery → 用户提交修复方案，恢复任务流 | P0 | 1.5h | P3-001 |
| P3-013 | 编写 API 单元测试：覆盖所有端点的正常/异常场景 | P0 | 2h | P3-003~P3-012 |
| P3-014 | 实现 WebSocket 实时推送：Agent 状态变更 → 推送给所有连接的客户端 | P0 | 2h | P3-002 |

### 阶段 3.2：Web 前端 - 基础框架

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-015 | 创建 React/Vue 前端项目骨架：Vite + TypeScript + Tailwind CSS | P0 | 1h | - |
| P3-016 | 实现前端路由配置：Dashboard / Agents / Tasks / Terminal / BDD / Alerts 页面 | P0 | 1h | P3-015 |
| P3-017 | 实现 API 客户端封装：统一请求封装、错误处理、类型定义 | P0 | 1.5h | P3-015 |
| P3-018 | 实现 WebSocket 客户端：自动重连、状态同步、消息分发 | P0 | 2h | P3-015 |
| P3-019 | 实现全局状态管理：Agent 列表、Task 列表、当前执行状态 | P0 | 1.5h | P3-017 |
| P3-020 | 实现暗色/亮色主题切换 | P1 | 1h | P3-015 |

### 阶段 3.3：Web 前端 - 核心页面

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-021 | 实现 Dashboard 页面布局：顶部状态摘要 + Agent 卡片列表 + 任务进度概览 | P0 | 2h | P3-019 |
| P3-022 | 实现 Agent 状态卡片组件：运行中/等待中/已完成/失败 状态标识、角色标签 | P0 | 1.5h | P3-021 |
| P3-023 | 实现任务进度看板组件：看板视图（待执行/执行中/已完成/失败）+ 进度百分比 | P0 | 2h | P3-021 |
| P3-024 | 实现任务依赖图可视化：DAG 可视化、高亮当前执行路径 | P1 | 2h | P3-023 |
| P3-025 | 实现嵌入式终端组件：连接 tmux 会话、实时输出显示、指令输入框 | P0 | 2.5h | P3-018 |
| P3-026 | 实现 BDD 需求交互组件：Given-When-Then 展示、用户确认/修改/拒绝操作 | P0 | 2h | P3-017 |
| P3-027 | 实现告警通知中心组件：历史告警列表、待处理标记、告警详情 | P1 | 1.5h | P3-019 |
| P3-028 | 实现需求提交页面：文本输入 + 提交按钮 → 启动 PM Agent | P0 | 1.5h | P3-017 |
| P3-029 | 实现修复方案提交组件：查看失败详情 → 输入修复方案 → 恢复执行 | P0 | 1.5h | P3-017 |

### 阶段 3.4：OpenClaw 监控模块

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-030 | 实现 OpenClaw 进程检测：monitor.py - 定期检查所有 Claude Code CLI 进程存活 | P0 | 2h | - |
| P3-031 | 实现执行超时检测：每个 task 设定最大执行时间，超时标记异常 | P0 | 1.5h | P3-030 |
| P3-032 | 实现资源使用监控：CPU / 内存 / 磁盘使用率检测，超出阈值告警 | P0 | 1.5h | P3-030 |
| P3-033 | 实现 OpenClaw 配置加载：config.yaml 解析（check_interval, timeout, thresholds） | P0 | 1h | - |
| P3-034 | 实现 OpenClaw 主循环：定时检查 → 检测异常 → 触发告警 | P0 | 2h | P3-030~P3-033 |
| P3-035 | 编写 monitor.py 单元测试：进程存活检测、超时检测、资源监控 | P0 | 1.5h | P3-034 |

### 阶段 3.5：告警推送模块

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-036 | 实现告警消息格式化：format_alert(level, task_info, error_info) → 统一告警消息 | P0 | 1h | - |
| P3-037 | 实现企业微信 Webhook 推送：send_wecom_alert(message) | P0 | 1.5h | P3-036 |
| P3-038 | 实现钉钉 Webhook 推送：send_dingtalk_alert(message) | P0 | 1.5h | P3-036 |
| P3-039 | 实现 Slack Webhook 推送：send_slack_alert(message) | P1 | 1h | P3-036 |
| P3-040 | 实现告警重试机制：推送失败重试 3 次、间隔 60 秒 | P0 | 1h | P3-037~P3-039 |
| P3-041 | 实现 Master Agent 反向通知接口：Master Agent 通知 OpenClaw 触发告警 | P0 | 1h | P3-036 |
| P3-042 | 编写告警推送单元测试：各渠道 mock 测试、重试逻辑测试 | P0 | 1.5h | P3-040 |

### 阶段 3.6：Web + OpenClaw 集成

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P3-043 | 实现后端读取 OpenClaw 状态：告警 API 对接 OpenClaw 数据 | P0 | 1h | P3-011, P3-034 |
| P3-044 | 实现前端告警实时推送：WebSocket 推送新告警到前端 | P0 | 1.5h | P3-014, P3-027 |
| P3-045 | 实现 Master Agent 与 Web 面板双向通信：状态同步 + 指令下发 | P0 | 2h | P3-014, P3-010 |
| P3-046 | 端到端集成测试：需求提交 → PM 拆解 → 用户确认 → 任务执行 → 完成报告 | P0 | 3h | P3-045 |
| P3-047 | 端到端集成测试：任务失败 → OpenClaw 告警 → 用户修复 → 恢复执行 | P0 | 3h | P3-046 |

---

## ═══ Iteration 4：测试 + 优化 + 部署（1-2 周）═══

### 阶段 4.1：单元测试完善

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-001 | 编写 tmux 集成模块完整测试套件：会话/窗口/命令/输出 全覆盖 | P0 | 2h | P1-029 |
| P4-002 | 编写 Sub-Agent 生命周期完整测试：启动→执行→验证→提交→退出 | P0 | 2h | P1-043 |
| P4-003 | 编写 Master Agent 调度完整测试：单任务/多任务并行/依赖链/失败恢复 | P0 | 2h | P1-054 |
| P4-004 | 编写文件系统层完整测试：并发读写、格式校验、异常恢复 | P0 | 1.5h | P1-020 |
| P4-005 | 编写 OpenClaw 完整测试：进程检测/超时/资源监控/告警推送 | P0 | 1.5h | P3-035 |
| P4-006 | 编写 Web API 完整测试：所有端点 200/400/404/500 场景 | P0 | 2h | P3-013 |
| P4-007 | 配置代码覆盖率报告：pytest-cov，目标覆盖率 ≥ 80% | P1 | 1h | P4-001~P4-006 |

### 阶段 4.2：集成测试

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-008 | 集成测试：Master Agent 崩溃 → 重启 → 断点恢复 | P0 | 2h | P1-051 |
| P4-009 | 集成测试：Sub-Agent 进程崩溃 → OpenClaw 检测 → 告警 → Master 恢复 | P0 | 2h | P3-034 |
| P4-010 | 集成测试：任务执行超时 → 终止进程 → 告警 → 人工介入 | P0 | 2h | P3-031 |
| P4-011 | 集成测试：资源耗尽 → 暂停新任务 → 等待释放 → 自动恢复 | P0 | 1.5h | P3-032 |
| P4-012 | 集成测试：Git 操作失败 → 重试 3 次 → 标记失败 → 人工介入 | P0 | 1.5h | P1-034 |
| P4-013 | 集成测试：tmux 会话异常 → 检测 → 重启 → 恢复 | P0 | 1.5h | P1-022 |
| P4-014 | 集成测试：多 Agent 并行执行 → 独立 Git 提交 → 无冲突 | P0 | 2h | P2-016 |

### 阶段 4.3：BDD 验收测试

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-015 | BDD 验收：Given 用户在 Web 面板提交需求 → When 系统启动 PM Agent → Then PM Agent 输出 task.json | P0 | 2h | P2-001 |
| P4-016 | BDD 验收：Given task.json 已确认 → When Master Agent 调度 → Then 按依赖顺序执行所有 task | P0 | 2h | P1-047 |
| P4-017 | BDD 验收：Given Sub-Agent 执行任务 → When 测试通过 → Then git commit + 更新 progress.txt | P0 | 1.5h | P2-025 |
| P4-018 | BDD 验收：Given Sub-Agent 执行任务 → When 测试失败 → Then 暂停任务流 + 触发告警 | P0 | 1.5h | P1-050 |
| P4-019 | BDD 验收：Given 收到告警 → When 用户提交修复方案 → Then 从失败 task 重新执行 | P0 | 2h | P3-012 |

### 阶段 4.4：性能优化

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-020 | 性能优化：progress.txt 写入使用文件锁防止并发冲突 | P0 | 1.5h | P1-014 |
| P4-021 | 性能优化：task.json 读取使用缓存，避免频繁磁盘 IO | P1 | 1h | P1-013 |
| P4-022 | 性能优化：WebSocket 推送使用增量更新，减少带宽消耗 | P1 | 1h | P3-014 |
| P4-023 | 性能优化：tmux 输出捕获使用增量读取，避免全量截取 | P1 | 1h | P1-025 |
| P4-024 | 性能优化：OpenClaw 检测使用事件驱动而非轮询（进程 inotify） | P2 | 1.5h | P3-030 |
| P4-025 | 性能基准测试：单 Agent 执行延迟、多 Agent 并行吞吐量、内存占用 | P0 | 2h | P4-020~P4-024 |

### 阶段 4.5：安全加固

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-026 | 安全：Web 面板仅监听 localhost，禁止公网暴露 | P0 | 0.5h | P3-001 |
| P4-027 | 安全：API 请求添加认证 Token 验证 | P1 | 1h | P3-001 |
| P4-028 | 安全：tmux 会话隔离，防止 Agent 跨窗口操作 | P1 | 1h | P1-023 |
| P4-029 | 安全：文件系统路径校验，防止路径遍历攻击 | P1 | 1h | P1-013 |
| P4-030 | 安全：环境变量敏感信息不记录到日志 | P1 | 0.5h | P1-016 |

### 阶段 4.6：部署与文档

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-031 | 编写部署脚本：install.sh - 自动检查依赖、安装 Python 包、初始化目录 | P0 | 1.5h | - |
| P4-032 | 编写启动脚本：start.sh - 启动 Master Agent + OpenClaw + Web Server | P0 | 1h | - |
| P4-033 | 编写停止脚本：stop.sh - 优雅停止所有进程 | P0 | 0.5h | - |
| P4-034 | 编写 systemd 服务配置：openboss-agent.service + openclaw.service + web-panel.service | P1 | 1h | - |
| P4-035 | 编写 Docker 配置：Dockerfile + docker-compose.yml | P1 | 2h | - |
| P4-036 | 编写用户手册：系统安装、配置、使用指南 | P1 | 3h | - |
| P4-037 | 编写开发者文档：架构说明、API 文档、扩展指南 | P1 | 3h | - |
| P4-038 | 编写运维手册：日常运维、告警处理、故障排查 | P1 | 2h | - |
| P4-039 | 创建项目 README.md：项目介绍、快速开始、技术栈 | P0 | 1h | - |
| P4-040 | 编写 CHANGELOG.md：版本变更记录 | P2 | 0.5h | - |

### 阶段 4.7：最终验证

| 编号 | 任务 | 优先级 | 预估 | 依赖 |
|------|------|--------|------|------|
| P4-041 | 完整端到端测试：从需求输入到全部任务完成的完整工作流 | P0 | 4h | P4-014 |
| P4-042 | 完整端到端测试：包含失败恢复的完整工作流 | P0 | 3h | P4-019 |
| P4-043 | 完整端到端测试：Master Agent 崩溃恢复的完整工作流 | P0 | 2h | P4-008 |
| P4-044 | 性能压测：5+ Agent 并行执行的稳定性和资源占用 | P0 | 2h | P4-025 |
| P4-045 | 安全审计：检查所有安全措施是否到位 | P1 | 2h | P4-030 |
| P4-046 | 代码质量审查：lint 通过、覆盖率达标、无严重 warning | P0 | 2h | P4-007 |
| P4-047 | 文档完整性检查：所有文档与代码实际行为一致 | P1 | 2h | P4-039 |
| P4-048 | 最终发版：打 tag、生成 release notes、归档 | P0 | 1h | P4-046 |

---

## ═══ 统计汇总 ═══

| 迭代 | 任务数 | 预估总工时 | 核心产出 |
|------|--------|-----------|---------|
| **Iter 1** | 64 | ~82h | main_agent.py, base_subagent.py, tmux 集成, progress.txt, harness 文件 |
| **Iter 2** | 32 | ~44h | task.json 格式, PM Agent, 并行调度器, Git 集成, BDD+TDD 闭环 |
| **Iter 3** | 47 | ~65h | Web 前后端, OpenClaw 监控告警, 移动端告警集成, 失败恢复机制 |
| **Iter 4** | 48 | ~60h | 测试套件, 性能优化, 安全加固, 部署脚本, 文档 |
| **总计** | **191** | **~251h** | 完整的分布式 Agent 自动化执行系统 |

### 关键路径（Critical Path）

```
P1-001 → P1-010 → P1-013 → P1-046 → P1-047 → P1-048 → P1-045 → P1-061
→ P2-001 → P2-005 → P2-016 → P2-019 → P2-025
→ P3-001 → P3-014 → P3-045 → P3-046
→ P4-041 → P4-048
```

### 风险点

1. **Claude Code CLI 集成**：CLI 行为可能随版本变化，需要预留适配层
2. **tmux 兼容性**：不同 OS 的 tmux 版本行为差异，需做好版本检测
3. **并发安全**：多 Agent 并行写文件可能冲突，需要文件锁机制
4. **WebSocket 稳定性**：长时间运行的 WebSocket 连接需要心跳和重连机制
5. **Agent 行为不确定性**：AI Agent 的输出不完全可控，Harness 约束需持续优化
