# OpenBoss Agent Core v1.0 — 产品需求文档（PRD）

> **版本**: v1.0.0  
> **日期**: 2026-05-08  
> **状态**: 初稿（待评审）  
> **定位**: Agent 核心引擎的实现蓝图，从已有资产逆向工程 + 前沿 Agent 工程实践综合提炼

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [逆向工程：从已有资产中提取的 Agent 范式](#2-逆向工程从已有资产中提取的-agent-范式)
   - 2.1 [源材料清单与角色映射](#21-源材料清单与角色映射)
   - 2.2 [核心发现：Agent 是一台 PDCA 状态机](#22-核心发现agent-是一台-pdca-状态机)
   - 2.3 [六大设计模式](#23-六大设计模式)
3. [系统架构设计](#3-系统架构设计)
   - 3.1 [架构总览](#31-架构总览)
   - 3.2 [架构原则](#32-架构原则)
   - 3.3 [模块依赖图](#33-模块依赖图)
4. [核心模块详设](#4-核心模块详设)
   - 4.1 [Constitution Engine（行为宪法引擎）](#41-constitution-engine行为宪法引擎)
   - 4.2 [State Manager（状态管理器）](#42-state-manager状态管理器)
   - 4.3 [Workflow Engine（工作流引擎）](#43-workflow-engine工作流引擎)
   - 4.4 [Context Engine（上下文引擎）](#44-context-engine上下文引擎)
   - 4.5 [Tool Pipeline（工具运行时管道）](#45-tool-pipeline工具运行时管道)
   - 4.6 [Verification System（验证系统）](#46-verification-system验证系统)
   - 4.7 [Lifecycle Manager（生命周期管理器）](#47-lifecycle-manager生命周期管理器)
   - 4.8 [Hook Bus（事件总线）](#48-hook-bus事件总线)
   - 4.9 [Prompt Assembly（提示词组装架构）](#49-prompt-assembly提示词组装架构)
   - 4.10 [Permission System（权限系统)](#410-permission-system权限系统)
5. [数据模型与文件协议](#5-数据模型与文件协议)
   - 5.1 [文件系统布局](#51-文件系统布局)
   - 5.2 [constitution.md 协议](#52-constitutionmd-协议)
   - 5.3 [task-manifest.json 协议](#53-task-manifestjson-协议)
   - 5.4 [session-log.md 协议](#54-session-logmd-协议)
   - 5.5 [memory/ 协议](#55-memory-协议)
6. [Agent 思维范式（Thinking Protocol）](#6-agent-思维范式thinking-protocol)
   - 6.1 [单轮思考框架](#61-单轮思考框架)
   - 6.2 [决策树](#62-决策树)
   - 6.3 [错误恢复协议](#63-错误恢复协议)
7. [API 设计](#7-api-设计)
8. [实施路线图](#8-实施路线图)
9. [风险与应对](#9-风险与应对)
10. [附录](#10-附录)

---

## 1. 执行摘要

OpenBoss Agent Core 是一个**通用的、文件驱动的 AI 编程智能体运行时**。它不是又一个编码工具的封装层——而是一套**可插入任何 LLM 后端的 Agent 行为控制框架**。

**核心理念：** Agent 的智能不来自模型本身，而来自**约束、流程、反馈和记忆**的系统化组合。这套系统的每一个组件都已在你的项目中以原型形态存在过：

| 已有资产 | 在 Agent Core 中的角色 | 成熟度 |
|---------|----------------------|-------|
| `CLAUDE.md` | Constitution（宪法/行为规范） | ✅ 生产验证过（31任务全通过） |
| `task.json` | Task Manifest（任务状态源） | ✅ 生产验证 |
| `progress.txt` | Session Log（会话日志/跨会话记忆） | ✅ 生产验证 |
| `run-automation.sh` | Workflow Loop 原型（PDCA 循环） | ✅ 原型可用 |
| `init.sh` | Lifecycle Init 原型 | ✅ 原型可用 |
| `architecture.md` | Domain Knowledge Base（领域知识库） | ✅ 可复用 |
| AgentCommander PRD | 多Agent编排蓝图 | 📐 设计完备 |
| 13个 Skills | Agent 工程最佳实践知识库 | 📚 理论完备 |

**本 PRD 的目标：** 将这些分散的原型和知识，整合为一个**内聚的、可扩展的、生产级**的 Agent 运行时系统。

---

## 2. 逆向工程：从已有资产中提取的 Agent 范式

### 2.1 源材料清单与角色映射

我们首先定义每个"驱动文件"在 Agent Core 架构中的精确角色：

```
┌─────────────────────────────────────────────────────────────┐
│                   Agent Core 文件角色映射                    │
├──────────────┬──────────────────┬──────────────────────────┤
│  源文件       │  Agent Core 角色 │  层级                     │
├──────────────┼──────────────────┼──────────────────────────┤
│ CLAUDE.md    │ Constitution     │ L1 行为宪法（约束层）      │
│ task.json    │ Task Manifest    │ L2 任务状态（状态层）      │
│ progress.txt │ Session Log      │ L3 会话日志（记忆层）      │
│ init.sh      │ Bootstrap        │ L4 初始化器（启动层）      │
│ run-auto.sh  │ Automation Loop  │ L5 自动化循环（调度层）    │
│ README.md    │ Project Context  │ L6 项目上下文（领域层）    │
│ architecture │ Domain KB        │ L7 领域知识库（知识层）    │
└──────────────┴──────────────────┴──────────────────────────┘
```

### 2.2 核心发现：Agent 是一台 PDCA 状态机

通过对所有源文件的深度分析，我们发现这个 Agent 的本质**不是一个聊天机器人，而是一台有限状态机驱动的 PDCA 循环机器**。

#### 状态机定义（从 CLAUDE.md 提取）

```
                    ┌─────────────────┐
                    │     INIT        │
                    │  (运行 init.sh)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
              ┌────→│   SELECT_TASK   │◄────┐
              │     │ (读取 task.json) │     │
              │     └────────┬────────┘     │
              │              │              │
              │              ▼              │
              │     ┌─────────────────┐     │
              │     │   IMPLEMENT     │     │
              │     │ (按照 steps 执行)│     │
              │     └────────┬────────┘     │
              │              │              │
              │              ▼              │
              │     ┌─────────────────┐     │
              │     │     VERIFY      │     │
              │     │(lint+build+test)│     │
              │     └────────┬────────┘     │
              │              │              │
              │        ┌─────┴─────┐        │
              │        │ PASS       │ FAIL   │
              │        ▼           ▼        │
              │  ┌──────────┐ ┌────────┐   │
              │  │ RECORD   │ │ RETRY  │   │
              │  │ COMMIT   │ │ 或     │   │
              │  └────┬─────┘ │ BLOCK  │   │
              │       │       └───┬────┘   │
              │       │           │        │
              └───────┘           └────────┘
```

#### 关键洞察

**洞察 #1：文件即状态，非内存**
Agent 不在变量中保存状态。`task.json` 是唯一的状态源（Source of Truth）。`progress.txt` 是不可变的追加日志（Append-Only Log）。这意味着：
- Agent 可以在任何时刻被杀掉、重启，不丢失状态
- 多个 Agent 实例可以安全地读写同一个文件系统（配合锁）
- 整个执行历史完全可追溯

**洞察 #2：Constitution 即代码**
CLAUDE.md 不是"建议"，而是**强制性的行为宪法**。它定义了：
- **工作流的步骤和顺序**（Step 1 → Step 6）
- **每步的验收标准**（lint 通过、build 成功、浏览器测试）
- **禁止行为列表**（不要跳过测试、不要假完成、不要删除任务）
- **阻塞处理协议**（何时停止、如何格式化阻塞信息、什么不能做）
- **原子提交规则**（一个 task 的所有变更必须在一个 commit 中）

这完全对应 **Behavior Institutionalization** 技能中的核心方法论：把期望的行为编码成可执行的 do/dont 规则集。

**洞察 #3：Verification-Gated Completion**
没有任何任务可以在没有证据的情况下被标记为"通过"。progress.txt 中的每条记录必须包含：
- What was done（具体做了什么）
- Testing（怎么测的、命令是什么、输出是什么）
- Notes（给未来 Agent 的备注）

这对应 **Verification Agent** 技能的模式：用命令支持的证据做判断，输出严格的 PASS/FAIL/PARTIAL 结论。

**洞察 #4：自动化循环是外部的，不是内部的**
`run-automation.sh` 揭示了一个关键设计决策：**PDCA 循环不在 Agent 内部，而在外部**。Agent 本身只关心"完成一个任务"。循环逻辑是 bash 脚本：
```bash
for run in 1..N:
  1. 读 task.json，找下一个 passes:false 的任务
  2. 启动 Claude Code 并注入 prompt
  3. 等 Claude Code 完成
  4. 检查 task.json 中是否有任务被标记为 passed
  5. 记录日志
  6. 继续下一轮或退出
```

这意味着 **Agent 是无状态的（stateless）、一次性的（ephemeral）、幂等的（idempotent）**。这是云原生设计的核心思想。

### 2.3 六大设计模式

从源材料和技能库中提炼出六大设计模式，它们构成了 Agent Core 的理论基石：

#### 模式一：File-Driven State Machine（文件驱动状态机）

```
原则: "Context Window = RAM（易失有限）, Filesystem = Disk（持久无限）"
来源: planning-with-files 技能 + 实际项目验证

实现要点:
- 所有重要状态写入文件，不在内存中维护
- task.json = 状态寄存器（可读写）
- progress.txt = 事件日志（仅追加）
- constitution.md = 只读约束（加载时解析）
- memory/ = 长期记忆（跨会话持久）

反模式:
- ❌ 用内存变量跟踪任务进度
- ❌ 用 TodoWrite API 做持久化（会话结束就丢失）
- ❌ 依赖 context window 保持目标（压缩后丢失）
```

#### 模式二：Constitution-Based Behavior Control（基于宪法的行为控制）

```
原则: "将期望行为编码为可执行的 do/dont 规则集，而非模糊的美德"
来源: behavior-institutionalization 技能 + CLAUDE.md 实践

实现要点:
- 从失败模式出发写规则，不从 aspirational values 出发
- 每条规则有明确的激活条件和作用范围
- 分层: Task Rules / Risky Actions / User Communication / Format / Truthfulness
- 内建防作弊条款（如：不许声称测试通过除非真的跑了命令）
- 定期修剪过期规则

规则示例（从 CLAUDE.md 提取并泛化）:
  DO:   在标记任务通过前运行 lint + build
  DO:   把代码、progress.txt、task.json 放在同一个 commit
  DO:   遇到阻塞时写入 progress.txt 并输出标准格式的阻塞信息
  DON'T: 删除或修改已完成的任务描述
  DON'T: 在未通过全部测试时标记 passes:true
  DON'T: 在阻塞状态下提交 git commit
  ESCALATE_WHEN: 缺少环境配置、外部依赖不可用、测试无法进行
```

#### 模式三：Verification-Gated Delivery（验证门控交付）

```
原则: "验证者的工作是打破信心，而不是强化信心"
来源: verification-agent 技能 + progress.txt 实践

实现要点:
- 每个任务完成后必须有独立验证阶段
- 验证必须使用命令作为证据（不能只读代码）
- 验证输出严格的三态结论: PASS / FAIL / PARTIAL
- PARTIAL 仅用于环境限制，不用于不确定性
- 验证者必须是只读的（不修改项目文件）

验证层级（从 CLAUDE.md 提取并增强）:
  Level 1 - 基线验证: npm run lint + npm run build
  Level 2 - 类型检查: TypeScript tsc --noEmit
  Level 3 - 功能验证: 浏览器测试（UI 变更必须）
  Level 4 - 对抗性探针: 边界值、并发、错误路径
  Level 5 - 回归验证: 确认旧功能未被破坏
```

#### 模式四：Atomic Commit Protocol（原子提交协议）

```
原则: "一个逻辑任务的产出必须在一次提交中原子性地提交"
来源: CLAUDE.md Step 6 + Git 最佳实践

实现要点:
- 每个任务对应恰好一个 git commit
- commit 必须包含: 代码变更 + progress.txt 更新 + task.json 状态更新
- commit message 格式: "[Task {id}] {title} - completed"
- 禁止: 空提交、部分提交、拆分提交
- 禁止: 修改已提交的任务描述或删除任务

提交前检查清单:
  ☐ 所有 steps 都已实现
  ☐ lint 无错误
  ☐ build 成功
  ☐ 浏览器测试通过（如果涉及 UI）
  ☐ progress.txt 已更新
  ☐ task.json 中该任务的 passes 已改为 true
  ☐ git add . 包含所有相关文件
```

#### 模式五：Blocking/Escalation Protocol（阻塞/升级协议）

```
原则: "知道何时停下来比知道如何继续更重要"
来源: CLAUDE.md § Blocking Issues + blast-radius-permission 技能

阻塞分类:

  ┌─────────────┬──────────────┬──────────────────────────────┐
  │ 类型         │ 示例          │ 正确操作                     │
  ├─────────────┼──────────────┼──────────────────────────────┤
  │ ENV_MISSING  │ .env 不存在   │ 写 progress.txt → 输出阻塞   │
  │              │              │ 信息 → STOP → 等待人工         │
  ├─────────────┼──────────────┼──────────────────────────────┤
  │ DEP_DOWN     │ 第三方 API 宕机│ 记录错误 → 标记任务为 blocked│
  │              │              │ → 继续下一个任务              │
  ├─────────────┼──────────────┼──────────────────────────────┤
  │ TEST_IMPOSSIBLE │ 需要真实账号 │ 同 ENV_MISSING             │
  ├─────────────┼──────────────┼──────────────────────────────┤
  │ PERMISSION_DENIED │ 无写权限 │ 报错 → STOP → 等待权限       │
  └─────────────┴──────────────┴──────────────────────────────┘

阻塞时的绝对禁令 (DON'T):
  ❌ 提交 git commit
  ❌ 将 passes 设为 true
  ❌ 假装任务已完成
  ❌ 静默跳到下一个任务而不记录

阻塞时的必须动作 (DO):
  ✅ 在 progress.txt 记录当前进度和原因
  ✅ 输出标准格式的阻塞信息（含已完成工作、原因、需要人工做什么）
  ✅ 停止当前任务
```

#### 模式六：Ephemeral Agent Pattern（临时 Agent 模式）

```
原则: "Agent 是无状态的 worker，不是有状态的 manager"
来源: run-automation.sh 架构 + agent-lifecycle-management 技能

实现要点:
- 每次 Agent 启动时都是全新的（无历史上下文）
- 通过文件系统恢复状态（读 task.json + progress.txt）
- 执行完一个任务后退出（不驻留）
- 外部调度器决定是否启动下一个 Agent
- 这使得 Agent 天然支持: 重试、并行、替换后端模型

为什么这种设计更好?
  1. 无状态 = 无 bug 的累积状态污染
  2. 一次性 = 每个 Agent 都有完整的 context window
  3. 幂等 = 重跑同一个 task 是安全的
  4. 可替换 = 今天用 Claude Code，明天换 GLM
```

---

## 3. 系统架构设计

### 3.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenBoss Agent Core                          │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  Scheduler (调度器)                         │    │
│  │   负责: 选择任务 → 启动 Agent → 收集结果 → 决定下一步       │    │
│  └────────────────────────┬────────────────────────────────────┘    │
│                           │ spawn                                   │
│                           ▼                                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │               Agent Runtime (单次执行)                       │    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │Constitution  │  │ State        │  │ Context Engine    │  │    │
│  │  │Engine        │  │ Manager      │  │ (上下文组装)      │  │    │
│  │  │(行为宪法)     │  │(状态管理)     │  │                   │  │    │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │    │
│  │         │                 │                    │             │    │
│  │         ▼                 ▼                    ▼             │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │              Workflow Engine (PDCA)                 │   │    │
│  │  │                                                     │   │    │
│  │  │  Plan → Select Task → Implement → Verify → Record  │   │    │
│  │  │                                     ↑    ↓         │   │    │
│  │  │                              ┌──────┘    └──────┐   │   │    │
│  │  │                              │  FAIL?     PASS?  │   │   │    │
│  │  │                              ▼            ▼     │   │   │    │
│  │  │                        ┌──────────┐ ┌──────────┐  │   │   │
│  │  │                        │ Retry/   │ │ Atomic   │  │   │   │
│  │  │                        │ Block    │ │ Commit   │  │   │   │
│  │  │                        └──────────┘ └──────────┘  │   │   │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │                              │                                │    │
│  │                              ▼                                │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │Tool Pipeline │  │Verification  │  │Hook Bus          │  │    │
│  │  │(工具管道)     │  │System        │  │(事件收集)        │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                  File System (持久层)                        │    │
│  │                                                              │    │
│  │  constitution.md  task-manifest.json  session-log.md         │    │
│  │  memory/MEMORY.md  memory/YYYY-MM-DD.md  artifacts/          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                LLM Adapter Layer (适配层)                    │    │
│  │   Claude API / GLM API / OpenAI API / Local Model ...       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 架构原则

| 原则 | 说明 | 来源 |
|------|------|------|
| **File-First State** | 所有状态以文件形式存在，内存只做缓存 | 已有项目验证 |
| **Constitution-Driven** | 行为由宪法文件驱动，不硬编码在程序中 | CLAUDE.md |
| **Ephemeral Workers** | Agent 无状态、一次性、由外部调度 | run-automation.sh |
| **Verification-Gated** | 所有交付物必须经过验证门控 | progress.txt |
| **Event-Sourced** | 所有操作通过事件日志可追溯 | Hook 系统 |
| **Adapter Pattern** | LLM 后端可插拔，不绑定特定厂商 | 可扩展性要求 |
| **Graceful Degradation** | 任何组件失败不会导致数据损坏 | 鲁棒性要求 |

### 3.3 模块依赖图

```
Level 0 (基础设施):
  File System ← 所有模块依赖

Level 1 (核心引擎):
  Constitution Engine ← 定义 Agent 能做什么/不能做什么
  State Manager ← 读写任务状态
  Prompt Assembly ← 组装发送给 LLM 的 prompt

Level 2 (运行时):
  Context Engine ← 依赖 Constitution + State + Prompt
  Workflow Engine ← 依赖 State + Context
  Tool Pipeline ← 依赖 Constitution（权限规则）
  Permission System ← 依赖 Constitution（安全规则）
  Hook Bus ← 独立运行，被其他模块调用

Level 3 (保障):
  Verification System ← 依赖 Tool Pipeline（需要运行命令）
  Lifecycle Manager ← 依赖 Workflow（管理启停）

Level 4 (编排):
  Scheduler ← 依赖 Lifecycle + State + Hook
```

---

## 4. 核心模块详设

### 4.1 Constitution Engine（行为宪法引擎）

**职责：** 解析、执行和 enforcing Agent 的行为宪法。

**对应源码：** CLAUDE.md → constitution.md（进化版）

**设计思路：**

Constitution Engine 不是简单的"读取 Markdown 文件"。它是一个**结构化的规则解析和执行引擎**，将自然语言的宪法文本编译为可在运行时查询的规则对象。

#### 4.1.1 Constitution 文件结构

```markdown
# ---
# version: "1.0"
# project: "openboss-agent-core"
# enforcement: "strict"  # strict | lenient | advisory
# ---

## 1. Identity（身份定义）
name: "OpenBoss Coder"
role: "全栈开发工程师"
scope: "实现、测试、提交代码任务"

## 2. Workflow（工作流 - 强制步骤）
### Phase 1: Initialize
- action: RUN_COMMAND
- command: "./init.sh" 或等价的初始化序列
- skip_condition: "环境已就绪（dev server running）"

### Phase 2: Select Task
- action: READ_STATE
- source: "task-manifest.json"
- selection_criteria:
    - passes == false
    - dependencies_satisfied == true
    - NOT blocked
    - highest priority first

### Phase 3: Implement
- action: EXECUTE_TASK
- rules:
    - MUST follow all steps in task.description
    - MUST follow existing code patterns
    - MUST NOT skip any step

### Phase 4: Verify
- action: VERIFICATION_GATE
- levels:
    - L1_BASELINE: ["npm run lint", "npm run build"]
    - L2_TYPECHECK: ["tsc --noEmit"]  # optional
    - L3_BROWSER: required_if: "task involves UI changes"
    - L4_ADVERSARIAL: optional
- failure_action: FIX_AND_RETRY | BLOCK_AND_REPORT

### Phase 5: Record
- action: APPEND_LOG
- target: "session-log.md"
- format: standardized template (see §5.4)

### Phase 6: Commit
- action: ATOMIC_COMMIT
- includes: [code_changes, session_log.md update, task-manifest.json update]
- message_format: "[Task {id}] {title} - completed"
- pre_conditions: ALL_VERIFICATION_PASSED

## 3. Rules（行为规则集）
### Task Execution Rules
- DO_IMPLEMENT_ALL_STEPS: "必须实现任务的所有步骤"
- DONT_SKIP_TESTING: "不得跳过测试直接标记完成"
- DONT_REMOVE_TASKS: "不得删除或修改已存在的任务描述"
- MUST_FOLLOW_PATTERNS: "必须遵循项目已有的代码风格和架构"

### Communication Rules
- REPORT_BLOCKING_STANDARDIZED: "阻塞时必须使用标准格式输出"
- LOG_EVERYTHING: "所有操作必须记录到 session-log.md"
- HONEST_REPORTING: "不得声称测试通过除非实际运行了命令"

### Safety Rules
- NO_COMMIT_WHEN_BLOCKED: "阻塞状态下禁止 git commit"
- NO_FALSE_COMPLETION: "不得虚假标记任务为完成"
- ASK_WHEN_UNSURE: "不确定时必须询问，不得猜测"

## 4. Blocking Conditions（阻塞条件定义）
### ENVIRONMENT_MISSING
 triggers:
   - ".env file not found"
   - "database not configured"
   - "dependencies not installed"
 action: STOP_AND_REPORT
 format: standard blocking template

### EXTERNAL_DEP_DOWN
 triggers:
   - "API returns 503"
   - "service timeout"
 action: MARK_BLOCKED_CONTINUE_NEXT

### TEST_IMPOSSIBLE
 triggers:
   - "requires real user account"
   - "requires specific hardware"
 action: STOP_AND_REPORT

## 5. Permissions（工具权限映射）
tools:
  Bash:
    allowed_patterns: ["npm *", "npx *", "git *", "cat *", "ls *", "mkdir *"]
    dangerous_patterns: ["rm -rf *", "sudo *", "> /dev/null"]
    requires_confirmation: true_for: dangerous_patterns
  Write:
    scope: "project_directory_only"
    protected_paths: [".env*", "*.key", "credentials*"]
  Edit:
    same_as_Write
  WebFetch:
    rate_limit: "10 req/min"
  Agent:
    max_depth: 2  # 子Agent最大嵌套层数
```

#### 4.1.2 引擎内部设计

```typescript
// 伪代码 - Constitution Engine 核心 interface

interface ConstitutionRule {
  id: string;
  type: 'DO' | 'DONT' | 'MUST' | 'ESCALATE' | 'PERMIT';
  scope: string;           // 哪个阶段生效
  condition?: string;      // 激活条件
  message: string;         // 规则内容
  antiCheat?: string;      // 防作弊条款
  sourceLine: number;      // 来源行号（用于调试）
}

interface ConstitutionDocument {
  version: string;
  metadata: ConstitutionMetadata;
  workflow: WorkflowPhase[];
  rules: ConstitutionRule[];
  blockingConditions: BlockingCondition[];
  permissions: PermissionMap;
}

class ConstitutionEngine {
  private document: ConstitutionDocument;

  // 解析 constitution.md → 结构化对象
  parse(markdown: string): ConstitutionDocument;

  // 查询给定阶段适用的所有规则
  getRulesForPhase(phase: WorkflowPhase): ConstitutionRule[];

  // 检查某个动作是否违反规则
  checkViolation(action: AgentAction): RuleViolation | null;

  // 获取阻塞条件定义
  getBlockingCondition(type: string): BlockingCondition;

  // 生成阶段指令（注入到 prompt 中）
  generatePhaseInstructions(phase: WorkflowPhase): string;

  // 生成完整 system prompt（静态部分）
  generateSystemPrompt(): string;  // 这是 prompt-cache-friendly 的稳定前缀
}
```

**关键设计决策：**

1. **Constitution 作为 Prompt 的稳定前缀**（参考 prompt-assembly-architecture 和 prompt-cache-economics 技能）：Constitution 的大部分内容是不变的，应该放在 prompt cache 的 static zone。只有任务相关的动态部分放在 dynamic zone。

2. **规则版本化**：每次修改 constitution.md 时递增版本号，方便追踪哪些规则变化导致了行为差异。

3. **Anti-Cheat 内建**：针对高频作弊模式的特殊检测（如：声称跑了测试但没贴输出）。

### 4.2 State Manager（状态管理器）

**职责：** 管理任务状态的读写，保证一致性和并发安全。

**对应源码：** task.json → task-manifest.json（进化版）

#### 4.2.1 数据结构设计

```typescript
interface TaskManifest {
  meta: {
    project: string;
    description: string;
    version: string;
    lastUpdated: ISO8601;
    totalTasks: number;
    completedTasks: number;
    blockedTasks: number;
  };
  tasks: Task[];
}

interface Task {
  // === 身份 ===
  id: number;                    // 任务序号（稳定的，不使用 UUID）
  title: string;                 // 简短标题
  description: string;           // 详细描述
  
  // === 步骤（验收标准）===
  steps: string[];               // 具体的执行步骤清单
  
  // === 状态 ===
  status: TaskStatus;            // 见下方枚举
  passes: boolean;               // 是否通过验证（最终判决）
  blocked: boolean;              // 是否被阻塞
  blockReason?: string;          // 阻塞原因
  
  // === 依赖 ===
  dependsOn: number[];           // 前置任务 ID 列表
  
  // === 分类 ===
  category: string;              // 分类标签
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  tags: string[];
  
  // === 时间戳 ===
  createdAt?: ISO8601;
  startedAt?: ISO8601;
  completedAt?: ISO8601;
  
  // === 执行元数据 ===
  assignee?: string;             // 分配给的 Agent ID
  attempts: number;              // 尝试次数
  lastError?: string;            // 最后一次错误
  sessionLogRef?: string;        // 关联的 session log 条目
}

type TaskStatus =
  | 'pending'        // 待处理（默认）
  | 'in_progress'    // 进行中（Agent 已选中并开始）
  | 'needs_input'    // 需要人工介入
  | 'blocked'        // 被阻塞（等待外部条件）
  | 'completed'      // 已完成（passes=true 且已 commit）
  | 'failed'         // 失败（多次重试后仍无法完成）
  | 'skipped';       // 跳过（人工决定不做）
```

#### 4.2.2 核心操作

```typescript
class StateManager {
  private manifestPath: string;
  private lock: FileLock | null = null;

  // === 读取操作（无锁，可频繁调用）===
  
  /** 获取完整 manifest */
  readManifest(): TaskManifest;
  
  /** 获取单个任务 */
  getTask(id: number): Task | undefined;
  
  /** 获取下一个待办任务（选择算法）*/
  getNextTask(): Task | null;
  
  /** 获取任务统计 */
  getStats(): TaskStats;

  // === 写入操作（需加锁）===
  
  /** 开始任务（pending → in_progress）*/
  startTask(id: number): void;
  
  /** 完成任务（in_progress → completed, passes=true）*/
  completeTask(id: number): void;
  
  /** 标记阻塞 */
  blockTask(id: number, reason: string): void;
  
  /** 标记失败 */
  failTask(id: number, error: string): void;
  
  /** 更新尝试次数 */
  incrementAttempts(id: number): void;

  // === 查询操作 ===
  
  /** 检查任务依赖是否满足 */
  areDependenciesMet(taskId: number): boolean;
  
  /** 获取 DAG 拓扑排序后的任务列表 */
  getTopologicallySortedTasks(): Task[];

  // === 一致性保证 ===
  
  private acquireLock(): FileLock;
  private releaseLock(): void;
  private validateManifest(manifest: TaskManifest): boolean;
}
```

#### 4.2.3 任务选择算法

```typescript
function selectNextTask(manifest: TaskManifest): Task | null {
  const candidates = manifest.tasks.filter(t => 
    t.status === 'pending' &&     // 还没开始
    !t.blocked &&                 // 未被阻塞
    t.passes === false &&         // 未通过
    areDependenciesMet(t.id)      // 依赖已满足
  );
  
  if (candidates.length === 0) return null;
  
  // 排序优先级:
  return candidates.sort((a, b) => {
    // 1. 优先级 P0 > P1 > P2 > P3
    const priorityOrder = { P0: 0, P1: 1, P2: 2, P3: 3 };
    const pDiff = priorityOrder[a.priority] - priorityOrder[b.priority];
    if (pDiff !== 0) return pDiff;
    
    // 2. 依赖数少的先做（让后续任务解锁更快）
    const aDependents = countDependents(a.id);
    const bDependents = countDependents(b.id);
    
    // 3. ID 小的先做（自然的执行顺序）
    return aDependents - bDependents || a.id - b.id;
  })[0];
}
```

### 4.3 Workflow Engine（工作流引擎）

**职责：** 执行 PDCA 循环，驱动 Agent 完成一个完整的任务周期。

**对应源码：** run-automation.sh 中的单次循环逻辑 + CLAUDE.md 的 6 个步骤

#### 4.3.1 PDCA 循环状态机

```typescript
type WorkflowPhase = 
  | 'INITIALIZE'
  | 'SELECT_TASK'
  | 'ANALYZE'        // 新增：深入理解任务
  | 'PLAN'           // 新增：制定实现方案
  | 'IMPLEMENT'      // 原 Step 3
  | 'VERIFY'         // 原 Step 4
  | 'RECORD'         // 原 Step 5
  | 'COMMIT'         // 原 Step 6
  | 'BLOCKED'        // 阻塞态
  | 'FAILED';        // 失败态

type WorkflowEvent =
  | { type: 'START' }
  | { type: 'TASK_SELECTED'; taskId: number }
  | { type: 'ANALYSIS_COMPLETE'; findings: string[] }
  | { type: 'PLAN_CREATED'; plan: ExecutionPlan }
  | { type: 'IMPLEMENTATION_DONE'; changes: FileChange[] }
  | { type: 'VERIFICATION_RESULT'; result: VerificationResult }
  | { type: 'RECORDED'; logEntry: LogEntry }
  | { type: 'COMMITTED'; commitHash: string }
  | { type: 'BLOCKED'; reason: string }
  | { type: 'MAX_RETRIES_EXCEEDED'; lastError: string }
  | { type: 'RETRY' };

// 完整的状态转移矩阵
const TRANSITIONS: Record<WorkflowPhase, WorkflowEvent[]> = {
  INITIALIZE:    ['START'],
  SELECT_TASK:   ['START'],
  ANALYZE:       ['TASK_SELECTED'],
  PLAN:          ['ANALYSIS_COMPLETE'],
  IMPLEMENT:     ['PLAN_CREATED', 'RETRY'],     // 允许从 VERIFY 失败后重试
  VERIFY:        ['IMPLEMENTATION_DONE', 'RETRY'],
  RECORD:        [{ type: 'VERIFICATION_RESULT'; result: 'PASS' }],
  COMMIT:        ['RECORDED'],
  BLOCKED:       [{ type: 'VERIFICATION_RESULT'; result: 'BLOCKED' }],
  FAILED:        ['MAX_RETRIES_EXCEEDED'],
};
```

#### 4.3.2 Workflow Engine 主循环

```typescript
class WorkflowEngine {
  constructor(
    private constitution: ConstitutionEngine,
    private stateManager: StateManager,
    private contextEngine: ContextEngine,
    private toolPipeline: ToolPipeline,
    private verifier: VerificationSystem,
    private logger: SessionLogger,
    private hookBus: HookBus,
  ) {}

  async runCycle(): Promise<WorkflowResult> {
    const MAX_RETRIES = 3;
    let retryCount = 0;
    let currentPhase: WorkflowPhase = 'INITIALIZE';

    try {
      // === PHASE 1: INITIALIZE ===
      currentPhase = 'INITIALIZE';
      await this.executeInitialize();

      // === PHASE 2: SELECT TASK ===
      currentPhase = 'SELECT_TASK';
      const task = this.stateManager.getNextTask();
      if (!task) {
        return { status: 'NO_MORE_TASKS' };
      }
      this.hookBus.emit('task:selected', { taskId: task.id });
      this.stateManager.startTask(task.id);

      // === PHASE 3: ANALYZE（新增 - 深度理解任务）===
      currentPhase = 'ANALYZE';
      const analysis = await this.analyzeTask(task);
      
      // === PHASE 4: PLAN（新增 - 制定方案）===
      currentPhase = 'PLAN';
      const plan = await this.createPlan(task, analysis);

      // === PHASE 5-8: IMPLEMENT → VERIFY → RECORD ===
      // （带重试的子循环）
      for (retryCount = 0; retryCount < MAX_RETRIES; retryCount++) {
        try {
          // IMPLEMENT
          currentPhase = 'IMPLEMENT';
          const changes = await this.implementTask(task, plan);
          
          // VERIFY
          currentPhase = 'VERIFY';
          const verifyResult = await this.verifier.verify(task, changes);
          
          if (verifyResult.verdict === 'PASS') {
            // RECORD
            currentPhase = 'RECORD';
            await this.logger.record(task, changes, verifyResult);
            
            // COMMIT
            currentPhase = 'COMMIT';
            const commitHash = await this.atomicCommit(task);
            
            this.stateManager.completeTask(task.id);
            return { 
              status: 'SUCCESS', 
              taskId: task.id, 
              commitHash,
              retries: retryCount 
            };
          } else if (verifyResult.verdict === 'BLOCKED') {
            currentPhase = 'BLOCKED';
            this.stateManager.blockTask(task.id, verifyResult.reason);
            await this.logger.reportBlocked(task, verifyResult);
            return { status: 'BLOCKED', taskId: task.id };
          }
          // else: FAIL → retry
          
        } catch (error) {
          if (retryCount >= MAX_RETRIES - 1) {
            currentPhase = 'FAILED';
            this.stateManager.failTask(task.id, error.message);
            return { status: 'FAILED', taskId: task.id, error };
          }
          // 应用 3-Strike Error Protocol
          await this.handleRetry(error, retryCount);
        }
      }

    } catch (fatalError) {
      this.hookBus.emit('workflow:fatal', { phase: currentPhase, error: fatalError });
      return { status: 'FATAL_ERROR', phase: currentPhase, error: fatalError.message };
    }
  }
}
```

#### 4.3.3 相比原始方案的改进点

原始 CLAUDE.md 的流程是 6 步线性流程。我们在保留其精华的基础上增加了以下关键改进：

| 原始步骤 | Agent Core 改进 | 理由 |
|---------|----------------|------|
| Step 1: Initialize | 保留 + 增加健康检查 | 检查 dev server 是否真正在运行 |
| Step 2: Select Task | 保留 + 增加 DAG 依赖解析 | 支持复杂任务依赖关系 |
| **— 无 —** | **新增 ANALYZE 阶段** | 在动手前先充分理解任务需求和上下文 |
| **— 无 —** | **新增 PLAN 阶段** | 制定实现方案，避免盲目开工 |
| Step 3: Implement | 保留 + 增加子步骤追踪 | 将大的 step 拆分为可追踪的微步骤 |
| Step 4: Test | 升级为多级验证门控 | L1 基线 → L2 类型 → L3 浏览器 → L4 对抗 |
| Step 5: Update Progress | 保留 + 结构化模板 | 统一日志格式，便于解析 |
| Step 6: Commit | 保留 + 原子性保证 | 预提交检查清单 |
| **— 无 —** | **新增 3-Strike 重试协议** | 系统化的错误恢复，而非随机重试 |

### 4.4 Context Engine（上下文引擎）

**职责：** 为每一轮 LLM 调用组装最优的上下文窗口内容。

**对应技能：** context-hygiene-system + prompt-assembly-architecture + prompt-cache-economics + planning-with-files

**核心挑战：** Context Window 是有限的资源（RAM），但项目信息是近乎无限的（Disk）。Context Engine 的核心能力是在两者之间做**最优权衡**。

#### 4.4.1 上下文分层模型

```
┌────────────────────────────────────────────────────────┐
│                 Context Window (LLM Input)              │
│                                                        │
│  ═══════════════════════════════════════════════════   │
│  STATIC ZONE (Cache-Friendly Prefix)                   │
│  ═══════════════════════════════════════════════════   │
│  [Constitution: Identity]        ~200 tokens  始终不变   │
│  [Constitution: Core Rules]      ~800 tokens  很少变    │
│  [Constitution: Workflow]        ~600 tokens  固定流程   │
│  [Project: Tech Stack]           ~300 tokens  不变       │
│  [Project: Conventions]          ~400 tokens  很少变    │
│  ─────────────────────────────────────────────           │
│  STATIC SUBTOTAL               ~2300 tokens              │
│  ═══════════════════════════════════════════════════   │
│                                                        │
│  ═══════════════════════════════════════════════════   │
│  DYNAMIC ZONE (Per-Turn Variance)                      │
│  ═══════════════════════════════════════════════════   │
│  [Current Task Description]     ~500 tokens  当前任务    │
│  [Relevant Architecture Docs]   ~1000 tokens 按需加载    │
│  [Recent Progress Log]          ~800 tokens  最近记录    │
│  [Session Memory]               ~400 tokens  本次会话记忆 │
│  [Long-term Memory]             ~300 tokens  关键经验    │
│  [Active File Contents]         ~2000 tokens 当前编辑的  │
│  [Tool Results]                 ~3000 tokens 动态获取    │
│  ─────────────────────────────────────────────           │
│  DYNAMIC SUBTOTAL              ~8000 tokens (varies)     │
│  ═══════════════════════════════════════════════════   │
│                                                        │
│  TOTAL BUDGET: ~10000-15000 tokens (model-dependent)    │
└────────────────────────────────────────────────────────┘
```

#### 4.4.2 上下文组装管线

```typescript
class ContextEngine {
  /**
   * 核心方法: 为当前轮组装完整的 prompt
   * 
   * 设计原则 (from prompt-assembly-architecture):
   * - Static prefix 尽可能长且稳定（cache hit率高）
   * - Dynamic tail 注入尽可能晚
   * - 使用显式的 boundary marker 分隔
   * - 返回 section 数组而非拼接字符串（便于调试/diff）
   */
  async assemblePrompt(
    phase: WorkflowPhase,
    task: Task | null,
    recentHistory: Message[],
    toolResults: ToolResult[],
  ): Promise<AssembledPrompt> {

    const sections: PromptSection[] = [];

    // ========== STATIC ZONE (cached) ==========
    
    // S1: Identity & Role
    sections.push({
      id: 'identity',
      stability: 'permanent',
      content: this.constitution.getIdentitySection(),
    });

    // S2: Core Behavior Rules
    sections.push({
      id: 'core-rules',
      stability: 'permanent',
      content: this.constitution.getCoreRulesSection(),
    });

    // S3: Workflow Instructions
    sections.push({
      id: 'workflow',
      stability: 'permanent',
      content: this.constitution.getWorkflowInstructions(phase),
    });

    // S4: Project Conventions
    sections.push({
      id: 'conventions',
      stability: 'session',
      content: await this.loadConventions(),
    });

    // ========== BOUNDARY MARKER ==========
    
    sections.push({
      id: 'boundary',
      stability: 'marker',
      content: '<!-- DYNAMIC_CONTEXT_BELOW -->',
    });

    // ========== DYNAMIC ZONE (per-turn) ==========
    
    // S5: Current Task
    if (task) {
      sections.push({
        id: 'current-task',
        stability: 'turn',
        content: this.formatTaskForPrompt(task),
      });
    }

    // S6: Relevant Context (smart retrieval)
    const relevantDocs = await this.retrieveRelevantContext(task, recentHistory);
    sections.push({
      id: 'context-docs',
      stability: 'turn',
      content: relevantDocs,
    });

    // S7: Recent Progress (last N entries from session-log.md)
    sections.push({
      id: 'recent-progress',
      stability: 'turn',
      content: await this.loadRecentProgress(5),  // 最近5条
    });

    // S8: Memory (long-term + session)
    sections.push({
      id: 'memory',
      stability: 'turn',
      content: await this.loadRelevantMemory(),
    });

    // S9: Tool Results (budgeted)
    const budgetedResults = this.budgetToolResults(toolResults);
    sections.push({
      id: 'tool-results',
      stability: 'turn',
      content: budgetedResults,
    });

    // S10: Conversation History (compacted if needed)
    const compactedHistory = this.compactHistoryIfNeeded(recentHistory);
    sections.push({
      id: 'history',
      stability: 'turn',
      content: compactedHistory,
    });

    return {
      sections,
      totalTokens: this.estimateTokens(sections),
      staticTokenCount: this.countStaticTokens(sections),
      boundaryIndex: sections.findIndex(s => s.id === 'boundary'),
    };
  }

  /**
   * Context Hygiene Passes (from context-hygiene-system skill)
   * 
   * 按顺序执行:
   * 1. Snip - 移除冗余的历史消息
   * 2. MicroCompact - 压缩相似的工具调用结果
   * 3. ContextCollapse - 将旧对话折叠为摘要
   * 4. AutoCompact - 全局压缩（当接近 token 上限时）
   */
  private compactHistoryIfNeeded(history: Message[]): Message[] {
    const currentSize = this.estimateTokenCount(history);
    const budget = this.getContextBudget();
    
    if (currentSize <= budget * 0.8) return history;  // 安全区
    
    // Pass 1: Snip（移除中间冗余）
    let result = this.snipPass(history);
    
    if (this.estimateTokenCount(result) <= budget) return result;
    
    // Pass 2: MicroCompact（合并连续同类操作）
    result = this.microcompactPass(result);
    
    if (this.estimateTokenCount(result) <= budget) return result;
    
    // Pass 3: ContextCollapse（旧对话 → 摘要）
    result = this.contextCollapsePass(result);
    
    if (this.estimateTokenCount(result) <= budget) return result;
    
    // Pass 4: AutoCompact（最后手段：全局摘要）
    return this.autocompactPass(result, budget);
  }
}
```

### 4.5 Tool Pipeline（工具运行时管道）

**职责：** 管理 Agent 的每一次工具调用，确保安全、可审计、可控。

**对应技能：** tool-runtime-pipeline + hook-governance-layer + blast-radius-permission + mcp-integration-plane

#### 4.5.1 工具调用生命周期

```
用户/Agent 请求
     │
     ▼
┌─────────────────┐
│ 1. RESOLVE      │  解析工具身份，附加元数据
│    Tool Identity │  (哪个工具？MCP 还是 builtin？)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. VALIDATE     │  校验输入参数是否符合 schema
│    Input        │  (参数类型正确？必填项齐全？)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. PRE-HOOKS    │  🔔 Hook Governance Layer
│    (PreToolUse) │  - 注入额外上下文
│                 │  - 修改输入
│                 │  - 权限预检
│                 │  - 阻止危险操作
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. PERMISSION   │  🔒 Blast Radius Permission
│    Resolution   │  - 规则匹配 (allow/ask/deny)
│                 │  - 安全检查 (bypass-immune)
│                 │  - 模式行为 (auto/plan/craft)
│                 │  - 爆炸半径评估
└────────┬────────┘
         │  ┌─ DENIED → 返回结构化拒绝
         │  └─ ASK → 等待用户确认
         ▼  ALLOWED
┌─────────────────┐
│ 5. EXECUTE      │  ⚡ 实际执行工具
│    Tool         │  - 记录开始时间
│                 │  - 设置超时
│                 │  - 捕获输出
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 6. NORMALIZE    │  统一输出格式
│    Result       │  (builtin 和 MCP 共享同一形状)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 7. POST-HOOKS   │  🔔 Hook Governance Layer
│  (PostToolUse)  │  - 记录遥测数据
│    or Failure   │  - 触发副作用
│                 │  - 进度更新提醒
└────────┬────────┘
         │
         ▼
    返回给 Agent
```

#### 4.5.2 权限决策流水线

```typescript
// From blast-radius-permission skill - 决策阶梯

interface PermissionDecision {
  action: 'ALLOW' | 'DENY' | 'ASK';
  reason: string;
  source: string;        // 哪一层做出的决策
  blastRadius: 'SAFE' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  requiresConfirmation: boolean;
}

async function resolvePermission(
  toolName: string,
  input: unknown,
  context: ExecutionContext,
): Promise<PermissionDecision> {

  // Layer 1: Rule-based Deny/Ask（最快、最严格）
  const ruleDecision = evaluateRules(toolName, input, [
    context.userSettings,    // 用户设置
    context.projectSettings, // 项目设置 (.claude/settings.json)
    context.localSettings,   // 本地设置
    context.sessionRules,    // 会话级规则
    context.cliGrants,       // CLI 授权
  ]);
  if (ruleDecision.action === 'DENY') return ruleDecision;
  if (ruleDecision.action === 'ASK') return ruleDecision;

  // Layer 2: Content-Specific Safety Checks（绕过免疫）
  const safetyCheck = evaluateSafetyChecks(toolName, input);
  if (safetyCheck.blocked) {
    return { action: 'DENY', reason: safetyCheck.reason, source: 'safety-check' };
  }

  // Layer 3: Mode Behavior
  const modeDecision = applyModeBehavior(
    ruleDecision,           // Layer 1 结果
    context.mode,           // craft / plan / ask
    context.dangerousRules, // 危险规则目录
  );

  // Layer 4: Sandbox Classifier
  if (modeDecision.action === 'ALLOW') {
    const sandboxResult = classifyForSandbox(toolName, input);
    if (!sandboxResult.isSafe) {
      // 非沙箱安全命令 → 需要确认或走 classifier
      return {
        action: sandboxResult.needsConfirmation ? 'ASK' : modeDecision.action,
        reason: sandboxResult.reason,
        source: 'sandbox-classifier',
        blastRadius: sandboxResult.blastRadius,
      };
    }
  }

  return {
    action: modeDecision.action || 'ALLOW',
    reason: 'All checks passed',
    source: 'permission-pipeline',
    blastRadius: classifyBlastRadius(toolName),
  };
}
```

### 4.6 Verification System（验证系统）

**职责：** 对 Agent 的工作产物进行独立、对抗性的验证。

**对应技能：** verification-agent

**核心哲学：** 验证者的工作是**打破信心**，不是强化信心。

#### 4.6.1 验证流程

```typescript
class VerificationSystem {
  
  async verify(task: Task, changes: FileChange[]): Promise<VerificationResult> {
    const checks: CheckResult[] = [];
    const tempDir = await this.createTempDir();  // 只能在临时目录操作！

    try {
      // ===== Level 1: Baseline (必选) =====
      checks.push(await this.runCheck('L1_LINT', {
        command: 'npm run lint',
        workingDir: this.projectRoot,
        expectedExitCode: 0,
      }));

      checks.push(await this.runCheck('L1_BUILD', {
        command: 'npm run build',
        workingDir: this.projectRoot,
        expectedExitCode: 0,
      }));

      if (!this.allPassed(checks)) {
        return this.buildResult(checks, 'FAIL');
      }

      // ===== Level 2: TypeCheck (可选) =====
      if (this.hasTypeScript()) {
        checks.push(await this.runCheck('L2_TYPECHECK', {
          command: 'npx tsc --noEmit',
          workingDir: this.projectRoot,
          expectedExitCode: 0,
        }));
      }

      // ===== Level 3: Browser Test (UI 相关必须) =====
      if (this.taskInvolvesUI(task)) {
        checks.push(await this.runCheck('L3_BROWSER', {
          type: 'browser_test',
          scenario: this.generateBrowserScenario(task, changes),
          tools: ['Playwright MCP', 'Browser Automation'],
        }));
      }

      // ===== Level 4: Adversarial Probe (可选但推荐) =====
      checks.push(...await this.runAdversarialProbes(task));

      // ===== 最终判定 =====
      const verdict = this.computeFinalVerdict(checks);
      return this.buildResult(checks, verdict);

    } finally {
      // 清理临时文件
      await this.cleanup(tempDir);
    }
  }

  /**
   * 对抗性探针 - 至少运行一种
   * 参考 verification-agent 技能: "Exercise the real system directly"
   */
  private async runAdversarialProbes(task: Task): Promise<CheckResult[]> {
    const probes: CheckResult[] [];

    // 根据任务类型选择探针策略
    const strategy = this.selectProbeStrategy(task);

    switch (strategy) {
      case 'frontend':
        // 探针: 不同屏幕尺寸下的渲染
        probes.push(await this.runCheck('A11Y_VIEWPORT', {
          command: '测试移动端 viewport 渲染',
        }));
        break;

      case 'backend':
        // 探针: 边界值输入
        probes.push(await this.runCheck('A12Y_EDGE_CASE', {
          command: '边界值和异常输入测试',
        }));
        break;

      case 'api':
        // 探针: 错误响应格式
        probes.push(await this.runCheck('A13Y_ERROR_PATH', {
          command: '错误路径和异常状态码测试',
        }));
        break;

      case 'infrastructure':
        // 探针: 幂等性和孤儿清理
        probes.push(await this.runCheck('A14Y_IDEMPOTENCY', {
          command: '重复执行和幂等性验证',
        }));
        break;
    }

    return probes;
  }
}
```

#### 4.6.2 验证报告格式

```markdown
### Verification Report: Task #{taskId} - {title}

**Timestamp:** 2026-05-08T11:00:00Z
**Verifier:** openboss-core/verification-engine-v1

---

#### Level 1: Baseline

##### Check: Lint
**Command:** `cd hello-nextjs && npm run lint`
**Output:** ✓ No errors, 3 warnings (pre-existing)
**Result: PASS**

##### Check: Build
**Command:** `cd hello-nextjs && npm run build`
**Output:** ✓ Build succeeded in 12.3s
**Result: PASS**

#### Level 3: Browser (required for UI task)

##### Check: Page Render
**Scenario:** Navigate to /projects and verify card layout
**Screenshot:** artifacts/verify-{taskId}-page.png
**Observation:** All 12 project cards rendered correctly
**Result: PASS**

##### Check: Interaction
**Scenario:** Click first card → navigate to detail page
**Observation:** Detail page loads with correct project data
**Result: PASS**

#### Level 4: Adversarial

##### Check: Empty State
**Scenario:** Delete all projects → verify empty state display
**Observation:** Empty state message shown correctly
**Result: PASS**

---

**Summary:** 5/5 PASS, 0 FAIL, 0 PARTIAL
**Verdict: PASS**
```

### 4.7 Lifecycle Manager（生命周期管理器）

**职责：** 管理 Agent 的创建、运行、暂停、恢复和销毁。

**对应技能：** agent-lifecycle-management

#### 4.7.1 生命周期状态图

```
              ┌───────────┐
         ┌───►│  CREATED  │
         │    └─────┬─────┘
         │          │ configure()
         │          ▼
         │    ┌───────────┐
         │    │ CONFIGURED│
         │    └─────┬─────┘
         │          │ start()
         │          ▼
         │    ┌───────────┐    abort()  ┌──────────┐
    resume()│   │ RUNNING   │───────────►│ ABORTED  │
         │    │           │             └──────────┘
         │    └─────┬─────┘
         │          │ complete() / error()
         │          ▼
         │    ┌───────────┐
         └────│  ENDED    │  ←── cleanup() always runs
              └───────────┘
                   │
                   ▼
              ┌───────────┐
              │ DISPOSED  │  (all resources released)
              └───────────┘
```

#### 4.7.2 生命周期管理关键设计

```typescript
interface AgentLifecycle {
  id: string;                    // 稳定的 Agent ID
  model: string;                 // 使用的 LLM 模型
  workingDirectory: string;      // 工作目录
  transcriptDir: string;         // 日志存储子目录
  status: LifecycleStatus;
  createdAt: Date;
  startedAt?: Date;
  endedAt?: Date;
  abortController: AbortController;
  metadata: {
    taskId?: number;              // 当前处理的任务
    totalTurns: number;           // 总轮次
    totalTokensUsed: number;      // Token 消耗
    toolCallCount: number;        // 工具调用次数
  };
}

class LifecycleManager {
  private activeAgents: Map<string, AgentLifecycle> = new Map();

  async spawn(config: AgentConfig): Promise<string> {
    const id = this.generateStableId();
    
    // 1. 创建 Agent 元数据
    const lifecycle: AgentLifecycle = {
      id,
      model: config.model,
      workingDirectory: config.workingDirectory,
      transcriptDir: path.join(config.logDir, id),
      status: 'CREATED',
      abortController: new AbortController(),
      metadata: { totalTurns: 0, totalTokensUsed: 0, toolCallCount: 0 },
    };

    // 2. Fork 上下文（移除父代不完整的 tool calls）
    const forkedContext = this.forkContext(config.parentContext);
    
    // 3. 按 Agent 类型裁剪上下文（read-only agent 不需要大状态）
    const trimmedContext = this.trimContextByRole(forkedContext, config.role);

    // 4. 加载启动资源
    await this.loadStartupResources(lifecycle, config);

    // 5. 注册到活跃列表
    this.activeAgents.set(id, lifecycle);

    // 6. 返回 ID
    return id;
  }

  async dispose(agentId: string): Promise<void> {
    const lifecycle = this.activeAgents.get(agentId);
    if (!lifecycle) return;

    // finally 块: 清理所有资源（参考 agent-lifecycle-management 技能）
    try {
      // 清理 MCP 连接
      await this.cleanupMcpClients(agentId);
      // 清理 Hooks
      await this.cleanupHooks(agentId);
      // 清理 Prompt Cache 追踪
      this.cleanupPromptCache(agentId);
      // 清理 Read File 缓存
      this.cleanupReadFileCache(agentId);
      // 清理 Transcript 映射
      this.cleanupTranscriptMappings(agentId);
      // 清理 Orphaned Todos
      this.cleanupOrphanedTodos(agentId);
    } finally {
      lifecycle.status = 'DISPOSED';
      this.activeAgents.delete(agentId);
    }
  }
}
```

### 4.8 Hook Bus（事件总线）

**职责：** 收集、路由和分发 Agent 运行过程中的所有事件。

**对应技能：** hook-governance-layer + planning-with-files hooks 配置

#### 4.8.1 事件类型定义

```typescript
type HookEventType =
  // === 生命周期事件 ===
  | 'lifecycle:spawn'          // Agent 创建
  | 'lifecycle:start'          // Agent 启动
  | 'lifecycle:complete'       // Agent 正常完成
  | 'lifecycle:abort'          // Agent 被中止
  | 'lifecycle:error'          // Agent 出错

  // === 工作流事件 ===
  | 'workflow:phase_change'    // 阶段切换
  | 'task:selected'            // 任务被选中
  | 'task:started'             // 任务开始
  | 'task:completed'           // 任务完成
  | 'task:blocked'             // 任务被阻塞
  | 'task:failed'              // 任务失败

  // === 工具事件（来自 hook-governance-layer）===
  | 'tool:pre_use'             // 工具调用前
  | 'tool:post_use'            // 工具调用成功后
  | 'tool:use_failure'         // 工具调用失败
  | 'tool:permission_result'   // 权限决策结果

  // === 验证事件 ===
  | 'verification:start'      // 验证开始
  | 'verification:check_done'  // 单项检查完成
  | 'verification:result'      // 验证最终结果

  // === 系统事件 ===
  | 'system:alert'             // 系统告警
  | 'system:resource_warning'  // 资源预警（token/时间）

interface HookEvent {
  type: HookEventType;
  timestamp: ISO8601;
  agentId: string;
  sessionId: string;
  payload: Record<string, unknown>;
  
  // 双通道输出
  channels: {
    http?: { endpoint: string; sent: boolean; responseStatus?: number };  // HTTP POST
    jsonl?: { filePath: string; written: boolean };                      // JSONL 文件
  };
}
```

#### 4.8.2 Hook 配置（从 planning-with-files 进化）

```yaml
# hooks.yaml (替代 .cursor/skills 中的 hooks.json)

hooks:
  # === 用户提交时：注入计划上下文 ===
  UserPromptSubmit:
    - id: inject_plan_context
      type: command
      condition: "task_plan.md exists"
      script: |
        echo '[plan-context] Current task:'
        head -50 task_plan.md
        echo ''
        echo '[plan-context] Recent progress:'
        tail -20 progress.md 2>/dev/null
        echo ''
        echo '[plan-context] Read findings.md for research context.'

  # === 工具调用前：显示当前任务上下文 ===
  PreToolUse:
    - id: show_task_on_tool_use
      matcher: "Write|Edit|Bash|Read|Glob|Grep"
      condition: "current_task is set"
      script: |
        TASK=$(cat .openboss/current-task.txt 2>/dev/null)
        if [ -n "$TASK" ]; then
          echo "--- [Current Task: $TASK] ---"
          cat .openboss/task-context.md 2>/dev/null | head -30
        fi

  # === 写操作后：提醒更新日志 ===
  PostToolUse:
    - id: remind_log_update
      matcher: "Write|Edit"
      condition: "task_in_progress"
      script: |
        echo '[log-reminder] Update session-log.md with what you just did.'
        echo '[log-reminder] If a phase completes, update task-manifest.json status.'

  # === 会话停止时：检查完整性 ===
  Stop:
    - id: completion_check
      type: command
      script: |
        # 检查是否有进行中的任务未记录
        # 检查是否有 uncommitted changes
        # 输出会话摘要

  # === 验证完成后：自动触发 commit 检查 ===
  Custom:
    - id: post_verification_gate
      trigger_event: "verification:result"
      condition: "verdict == PASS"
      script: |
        echo '[commit-gate] Verification PASSED. Ready for atomic commit.'
        echo '[commit-gate] Checklist: progress.txt updated? task.json updated? All files staged?'
```

### 4.9 Prompt Assembly（提示词组装架构）

**职责：** 构建 cache-friendly、可调试、模块化的系统提示词。

**对应技能：** prompt-assembly-architecture + prompt-cache-economics

已在 4.4 Context Engine 中详细描述其核心设计。此处补充 Section Registry 机制：

```typescript
/**
 * Section Registry - 所有 prompt 片段的注册表
 * 
 * 设计原则 (from prompt-assembly-architecture):
 * - 每个 section 有 stable ID
 * - 每个 section 标注稳定性级别和缓存归属
 * - 每个 section 记录依赖项（便于解释 cache miss）
 */

const SECTION_REGISTRY: Map<string, SectionDefinition> = new Map([
  // === PERMANENT (永不变化) ===
  ['identity',           { stability: 'permanent', cacheOwner: 'static', deps: [] }],
  ['core-rules',         { stability: 'permanent', cacheOwner: 'static', deps: [] }],
  ['safety-rules',       { stability: 'permanent', cacheOwner: 'static', deps: [] }],
  ['output-format',      { stability: 'permanent', cacheOwner: 'static', deps: [] }],
  
  // === SESSION (同一次运行期间稳定) ===
  ['workflow-current',   { stability: 'session',  cacheOwner: 'static', deps: ['phase'] }],
  ['project-conventions',{ stability: 'session',  cacheOwner: 'static', deps: ['config-files'] }],
  ['tech-stack',         { stability: 'session',  cacheOwner: 'static', deps: ['package.json'] }],
  
  // === TURN (每轮都可能变) ===
  ['current-task',       { stability: 'turn',    cacheOwner: 'dynamic', deps: ['task.json'] }],
  ['active-file',        { stability: 'turn',    cacheOwner: 'dynamic', deps: ['file-content'] }],
  ['recent-history',     { stability: 'turn',    cacheOwner: 'dynamic', deps: ['conversation'] }],
  ['tool-results',       { stability: 'turn',    cacheOwner: 'dynamic', deps: ['tool-calls'] }],
  ['memory',             { stability: 'turn',    cacheOwner: 'dynamic', deps: ['memory-files'] }],
  ['skill-instructions', { stability: 'turn',    cacheOwner: 'dynamic', deps: ['loaded-skills'] }],
  ['mcp-tools',          { stability: 'turn',    cacheOwner: 'dynamic', deps: ['mcp-connections'] }],
  
  // === MARKER (功能性分隔符) ===
  ['boundary',           { stability: 'marker',  cacheOwner: 'none',    deps: [] }],
]);
```

### 4.10 Permission System（权限系统）

**职责：** 基于宪法规则和安全策略，对每个工具调用进行细粒度的授权决策。

**对应技能：** blast-radius-permission

已在 4.5 Tool Pipeline 中详细描述了权限决策流水线。此处补充**危险规则目录**的概念：

```typescript
/**
 * Dangerous Rules Catalog (from blast-radius-permission skill)
 * 
 * 这些规则在 auto 模式下会被自动剥离，
 * 因为它们本质上关闭了所有安全评估。
 */

const DANGEROUS_RULES = [
  {
    pattern: 'Bash(*)',
    reason: '允许任意 shell 命令执行，等于完全关闭安全机制',
    blastRadius: 'CRITICAL',
    category: 'tool_allow_wildcard',
  },
  {
    pattern: 'PowerShell(iex:*)',
    reason: '允许远程脚本执行',
    blastRadius: 'CRITICAL',
    category: 'remote_code_execution',
  },
  {
    pattern: 'Agent(*)',
    reason: '允许无限嵌套子 Agent',
    blastRadius: 'HIGH',
    category: 'unbounded_delegation',
  },
  {
    pattern: 'Write(protected_path)',
    reason: '允许写入敏感文件',
    blastRadius: 'HIGH',
    category: 'sensitive_file_write',
  },
];

/**
 * Auto Mode Entry Procedure:
 * 进入 auto 模式时，必须先剥离所有危险规则
 */
function stripDangerousRules(permissions: PermissionSet): PermissionSet {
  return permissions.filter(p => 
    !DANGEROUS_RULES.some(d => matchPattern(p, d.pattern))
  );
}
```

---

## 5. 数据模型与文件协议

### 5.1 文件系统布局

```
{project_root}/
│
├── .openboss/                          # Agent Core 工作目录（gitignore）
│   ├── constitution.md                 # 行为宪法（= 进化版 CLAUDE.md）
│   ├── task-manifest.json              # 任务清单（= 进化版 task.json）
│   ├── session-log.md                  # 会话日志（= 进化版 progress.txt）
│   ├── current-task.txt                # 当前任务 ID（运行时状态）
│   ├── task-context.md                 # 当前任务的动态上下文
│   ├── hooks.yaml                      # Hook 配置
│   ├── config.yaml                     # Agent Core 配置
│   │
│   ├── memory/                         # 长期记忆
│   │   ├── MEMORY.md                   # 策选的长期记忆
│   │   └── 2026-05-08.md               # 每日日志
│   │
│   ├── transcripts/                    # Agent 执行记录
│   │   ├── {agent-id}/
│   │   │   ├── {session-id}.jsonl     # 完整对话 JSONL
│   │   │   └── metrics.json            # Token/时间指标
│   │
│   ├── artifacts/                      # 产出物
│   │   ├── verify-{task-id}/           # 验证截图/日志
│   │   └── plans/                      # 执行计划
│   │
│   └── logs/                           # 系统日志
│       ├── events.jsonl                # 所有事件
│       └── errors.jsonl                # 错误日志
│
├── constitution.md                     # 便捷链接 → .openboss/constitution.md
├── task-manifest.json                  # 便捷链接 → .openboss/task-manifest.json
├── session-log.md                      # 便捷链接 → .openboss/session-log.md
│
├── {actual_project_files...}           # 真实的项目文件
│   ├── src/
│   ├── package.json
│   └── ...
```

### 5.2 constitution.md 协议

这是 CLAUDE.md 的进化版。完整协议见 4.1.1 节。核心变化：

| CLAUDE.md (v1) | constitution.md (v2) | 变化理由 |
|---------------|---------------------|---------|
| 纯 Markdown 自然语言 | YAML Frontmatter + 结构化章节 | 机器可解析 |
| 固定 6 步流程 | 可配置的阶段 + 条件跳过 | 灵活性 |
| 规则混在段落中 | 分类规则集 + 激活条件 | 精确匹配 |
| 阻塞信息格式在正文中 | 结构化阻塞条件定义 | 标准化输出 |
| 无权限定义 | 完整的工具权限映射 | 安全可控 |
| 无版本号 | 语义化版本号 | 变更追踪 |

### 5.3 task-manifest.json 协议

这是 task.json 的进化版。完整接口定义见 4.2.1 节。核心变化：

| task.json (v1) | task-manifest.json (v2) | 变化理由 |
|---------------|------------------------|---------|
| 扁平任务列表 | 带 meta 信息的结构化文档 | 统计、版本控制 |
| 只有 passes 布尔值 | 多状态枚举 (pending/in_progress/blocked/completed/failed) | 精确状态跟踪 |
| 无依赖字段 | dependsOn 数组 + DAG 支持 | 任务编排 |
| 无优先级 | P0-P3 四级优先级 | 调度决策 |
| 无时间戳 | created/started/completed 时间戳 | 性能分析 |
| 无重试计数 | attempts 字段 | 错误恢复 |

**向后兼容：** 系统应能自动将旧版 task.json 迁移到新格式。

### 5.4 session-log.md 协议

这是 progress.txt 的进化版。保留原有的优秀品质（Append-Only、结构化模板），增加机器可解析性：

```markdown
# Session Log

## 2026-05-08T11:00:00Z - Task #24: 项目详情页 - 图片生成阶段

**Meta:**
- Agent: openboss-core/v1
- Session: sess_abc123
- Duration: 18m32s
- Turns: 15
- Tokens: 45230
- Retries: 0
- Verdict: PASS

### What was done:
- 创建 components/scene/SceneImageCard.tsx 分镜图片卡片组件
- 创建 components/scene/SceneImageList.tsx 图片列表组件
- 更新 app/projects/[id]/page.tsx 添加图片阶段视图
- 实现图片生成状态展示 (pending/processing/completed/failed)
- 实现「重新生成」和「确认」按钮
- 实现批量生成功能（顶部按钮）
- 实现批量确认功能（底部按钮）

### Files changed:
- `src/components/scene/SceneImageCard.tsx` (NEW, 142 lines)
- `src/components/scene/SceneImageList.tsx` (NEW, 218 lines)
- `src/app/projects/[id]/page.tsx` (MODIFIED, +15 lines)

### Testing:

#### L1: Baseline
- **Lint:** `npm run lint` → ✓ 0 errors
- **Build:** `npm run build` → ✓ success in 12.3s

#### L3: Browser
- **Page Load:** /projects/{id} renders with image stage → ✓
- **Image Cards:** 7 cards displayed correctly → ✓
- **Generate Button:** visible and clickable → ✓
- **Confirm Button:** visible after generation → ✓
- **Screenshots:** artifacts/verify-24-*.png

#### L4: Adversarial
- **Empty State:** no images yet shows pending state → ✓

### Notes:
- 图片生成调用 POST /api/generate/image/:sceneId API
- 使用轮询机制（每 5 秒）检查生成状态
- 确认后进入视频生成阶段
- SceneImageList 与 SceneVideoList 结构对称，可参考 Task 25

---
```

### 5.5 memory/ 协议

```markdown
<!-- memory/MEMORY.md - 长期记忆（策选的、高价值的信息）-->

# Long-Term Memory

## Project Conventions
- TypeScript strict mode + functional components + Tailwind CSS
- API Route → DAL → AI Service 三层架构
- Supabase Storage bucket: `project-media`, path: `{userId}/{projectId}/{fileName}`

## Learned Patterns
- Storage bucket 为私有时必须使用签名 URL (createSignedUrl)，不能用 getPublicUrl
- 火山引擎视频生成为异步任务模式：create → poll → download
- 前端轮询需要在 useEffect 中恢复（处理页面刷新场景）

## Failure Patterns (Anti-Patterns)
- ❌ window.location.reload() 是解决 React 状态不同步的最快方式但要谨慎使用
- ❌ 不要在 finally 块中重置 UI 状态（页面刷新后不需要）
- ✅ 确认操作后一定要刷新页面以反映新的 project stage

## Preferences (User)
- 偏好深色模式（dark mode fixed）
- 喜欢结构化的进度反馈
- 重视浏览器实测胜于纯 lint/build 通过
```

---

## 6. Agent 思维范式（Thinking Protocol）

这一章定义 Agent 在执行过程中的**思考框架**。这不是代码层面的设计，而是 Agent（LLM）在被驱动时应该遵循的认知协议。

### 6.1 单轮思考框架

每一轮 Agent 执行时，都应该按以下框架组织思维：

```
┌─────────────────────────────────────────────────────────┐
│                   THINKING FRAMEWORK                     │
│                                                          │
│  1. WHERE AM I?（定位）                                  │
│     ├─ 当前阶段？(从 current-task.txt 或 workflow state) │
│     ├─ 当前进度？(已完成的 steps / 总 steps)              │
│     └─ 有无阻塞？(检查 task status)                      │
│                                                          │
│  2. WHAT SHOULD I DO?（决策）                             │
│     ├─ Constitution 中适用于当前阶段的规则有哪些？         │
│     ├─ 下一步行动是什么？（查 task.steps[n]）              │
│     ├─ 这一步是否需要工具调用？哪个工具？                  │
│     └─ 是否需要先读取文件/搜索代码来理解上下文？            │
│                                                          │
│  3. WHAT DO I ALREADY KNOW?（回忆）                       │
│     ├─ session-log.md 中最近的记录说了什么？              │
│     ├─ memory/MEMORY.md 中有什么相关经验？                │
│     ├─ architecture.md 中有什么相关架构信息？              │
│     └─ 当前的 conversation history 中有什么？             │
│                                                          │
│  4. WHAT COULD GO WRONG?（预判）                          │
│     ├─ 这个操作可能违反什么 Constitution 规则？            │
│     ├─ 爆炸半径有多大？（修改影响范围）                    │
│     ├─ 如果失败了，回退方案是什么？                        │
│     └─ 是否需要用户确认？                                 │
│                                                          │
│  5. EXECUTE & VERIFY（执行与验证）                        │
│     ├─ 调用工具                                           │
│     ├─ 检查结果                                           │
│     ├─ 符合预期吗？                                       │
│     └─ 如果不符合，进入错误恢复协议                       │
│                                                          │
│  6. RECORD（记录）                                        │
│     ├─ 这一步做了什么？                                   │
│     ├─ 结果是什么？                                       │
│     ├─ 有什么值得未来 Agent 知道的？                       │
│     └─ 更新 memory（如有长期价值的信息）                   │
└─────────────────────────────────────────────────────────┘
```

### 6.2 决策树

```
START
  │
  ├─ 有 current task 吗？
  │   ├─ NO → 读 task-manifest.json → 选下一个 → SET_CURRENT
  │   └─ YES → 继续
  │
  ├─ 当前任务状态？
  │   ├─ blocked → 输出阻塞信息 → STOP
  │   ├─ completed → 选下一个 → SET_CURRENT
  │   └─ pending/in_progress → 继续
  │
  ├─ 下一步是什么？（查 task.steps[current_step_index]）
  │   ├─ 是代码编写 → 读现有代码了解模式 → 写代码
  │   ├─ 是测试 → 执行验证命令 → 检查结果
  │   ├─ 是文档 → 写/更新文档
  │   ├─ 是提交 → 检查前置条件 → atomic commit
  │   └─ 不确定 → 读 Constitution 相关章节 → 再决策
  │
  ├─ 操作完成了吗？
  │   ├─ 成功 → 记录到 progress → current_step_index++
  │   ├─ 失败 → 进入错误恢复协议 (§6.3)
  │   └─ 需要确认 → 询问用户 / 检查 Constitution
  │
  ├─ 所有 steps 都完成了？
  │   ├─ YES → 进入 VERIFICATION 阶段
  │   └─ NO → 回到"下一步是什么？"
  │
  └─ VERIFICATION 结果？
      ├─ PASS → RECORD → COMMIT → 选下一个任务
      ├─ FAIL → 重试（如果在限制内）或 BLOCK
      └─ BLOCKED → 写阻塞信息 → 选下一个或 STOP
```

### 6.3 错误恢复协议（3-Strike Error Protocol）

源自 progress.txt 中积累的真实经验和 planning-with-files 技能的 3-Strike 协议：

```
ATTEMPT 1: Diagnose & Fix（诊断与修复）
  ├─ 仔细阅读错误信息
  ├─ 识别根本原因（root cause），不是表面症状
  ├─ 应用针对性的修复
  └─ 记录到 session-log.md

ATTEMPT 2: Alternative Approach（另辟蹊径）
  ├─ 还是同样的错误？
  ├─ 换一个不同的方法
  │   ├─ 不同的工具？（Read → Glob → Grep）
  │   ├─ 不同的库/API？
  │   └─ 不同的实现方式？
  ├─ ⚠️ 永远不要完全重复上一次失败的操作
  └─ 记录到 session-log.md

ATTEMPT 3: Broader Rethink（重新思考）
  ├─ 质疑前提假设
  │   ├─ 我对需求的理解正确吗？
  │   ├─ 当前的技术方案合适吗？
  │   └─ 是否需要更新计划？
  ├─ 搜索解决方案（WebSearch / 读文档）
  ├─ 考虑是否需要更新 task-manifest.json（调整 steps）
  └─ 记录到 session-log.md

AFTER 3 FAILURES: Escalate to User（升级给用户）
  ├─ 整理我尝试过的所有方法和结果
  ├─ 附上具体的错误信息和命令输出
  ├─ 解释我的判断和建议
  └─ 等待用户指示
```

---

## 7. API 设计

Agent Core 对外暴露两类 API：

### 7.1 内部 API（模块间调用）

```typescript
// === Workflow Engine API ===
interface IWorkflowEngine {
  runCycle(): Promise<WorkflowResult>;
  getCurrentPhase(): WorkflowPhase;
  getStatus(): WorkflowStatus;
  abort(): void;
}

// === State Manager API ===
interface IStateManager {
  getNextTask(): Task | null;
  startTask(id: number): void;
  completeTask(id: number): void;
  blockTask(id: number, reason: string): void;
  getStats(): TaskStats;
}

// === Context Engine API ===
interface IContextEngine {
  assemblePrompt(phase: WorkflowPhase, task: Task, ...): Promise<AssembledPrompt>;
  compactHistory(history: Message[]): Message[];
  loadMemory(): Promise<MemoryBundle>;
}

// === Verification API ===
interface IVerificationSystem {
  verify(task: Task, changes: FileChange[]): Promise<VerificationResult>;
  runAdversarialProbes(task: Task): Promise<CheckResult[]>;
}

// === Hook Bus API ===
interface IHookBus {
  emit(event: HookEvent): void;
  on(eventType: HookEventType, handler: EventHandler): void;
  getEvents(filter?: EventFilter): HookEvent[];
}
```

### 7.2 外部 API（CLI / SDK）

```bash
# CLI 命令设计

# 初始化项目（= 进化版 init.sh）
openboss init [--template starter|fullstack|ai-app]

# 运行单个任务
openboss run --task 24 [--model claude-opus-4]

# 运行自动化循环（= 进化版 run-automation.sh）
openboss loop --max-runs 10 [--concurrency 2] [--mode auto|manual]

# 查看状态
openboss status                    # 全局状态
openboss status --task 24          # 单个任务状态
openboss status --log              # 最近日志

# 管理任务
openboss tasks list                # 列出所有任务
openboss tasks add <file.json>     # 从文件添加任务
openboss tasks block 24 <reason>   # 手动阻塞
openboss tasks unblock 24          # 取消阻塞
openboss tasks reset 24            # 重置任务状态

# 管理宪法
openboss constitution show         # 显示当前宪法
openboss constitution edit         # 编辑宪法
openboss constitution validate      # 验证宪法格式

# 验证
openboss verify --task 24          # 验证指定任务
openboss verify --all              # 验证所有已完成任务

# 内存管理
openboss memory write "<content>"  # 写入长期记忆
openboss memory search "<query>"   # 搜索记忆
openbosS memory compact            # 压缩/整理记忆
```

---

## 8. 实施路线图

### Phase 0: Foundation（第 1 周）— 核心原型

**目标：** 能够在一个简单项目上复刻 run-automation.sh 的完整能力。

| # | 任务 | 产出 | 验收标准 |
|---|------|------|---------|
| 0.1 | Constitution Parser | 能解析 Markdown + YAML Frontmatter | 读取 CLAUDE.md 输出结构化规则对象 |
| 0.2 | State Manager | 读写 task-manifest.json | 支持 task-json 向后兼容迁移 |
| 0.3 | Session Logger | 结构化的 session-log.md | 输出符合 §5.4 协议 |
| 0.4 | Workflow Engine v1 | 最小 PDCA 循环 | INIT → SELECT → IMPLEMENT → VERIFY → RECORD → COMMIT |
| 0.5 | CLI Skeleton | `openboss run` 和 `openboss loop` | 能在 hello-nextjs 上跑通一个 task |

**里程碑 M0：** 用 openboss 完成一个简单的代码任务（如"添加一个新页面"），全程无需人工干预。

### Phase 1: Intelligence（第 2-3 周）— 智能增强

**目标：** 加入分析、规划、上下文管理和错误恢复能力。

| # | 任务 | 产出 | 验收标准 |
|---|------|------|---------|
| 1.1 | Context Engine | 上下文组装管线 | Static/Dynamic 分层，boundary marker |
| 1.2 | Memory System | memory/ 目录读写 | MEMORY.md + 每日日志 |
| 1.3 | Analyze Phase | 任务分析能力 | 输出 findings（涉及的文件、依赖、风险）|
| 1.4 | Plan Phase | 执行计划生成 | 输出ExecutionPlan（微步骤列表）|
| 1.5 | 3-Strike Protocol | 错误恢复框架 | 3次重试 + 升级机制 |
| 1.6 | Hook Bus v1 | 基础事件收集 | JSONL + console 双通道输出 |

**里程碑 M1：** Agent 能自主处理中等复杂任务（如"实现一个 CRUD API"），遇到错误能自行恢复。

### Phase 2: Robustness（第 4-5 周）— 鲁棒性与安全

**目标：** 生产级的验证、权限和安全保障。

| # | 任务 | 产出 | 验收标准 |
|---|------|------|---------|
| 2.1 | Verification System | 多级验证引擎 | L1-L4 四级验证 + 对抗探针 |
| 2.2 | Permission System | 权限决策流水线 | 4层决策阶梯 + 危险规则剥离 |
| 2.3 | Tool Pipeline | 完整工具调用链 | 7 阶段 pipeline + 遥测 |
| 2.4 | Lifecycle Manager | 生命周期管理 | spawn → run → abort → dispose |
| 2.5 | Constitution Validator | 宪法校验工具 | 规则冲突检测、过期警告 |

**里程碑 M2：** Agent 能安全地运行在 auto 模式下，不会因误操作破坏项目。

### Phase 3: Scale（第 6-8 周）— 扩展与集成

**目标：** 多任务并行、多 Agent 编排、可视化界面。

| # | 任务 | 产出 | 验收标准 |
|---|------|------|---------|
| 3.1 | Multi-Task Parallel | 并行执行引擎 | DAG 调度 + 资源锁 |
| 3.2 | Agent Commander | 多 Agent 编排 | 角色定义 + 通信协议 + tmux 隔离 |
| 3.3 | Web Dashboard | React 管理界面 | 任务看板 + 实时日志 + Agent 监控 |
| 3.4 | WebSocket Realtime | Socket.IO 实时推送 | 状态同步 + 事件流 |
| 3.5 | MCP Integration | MCP 工具接入层 | stdio/SSE/HTTP 多传输 |

**里程碑 M3：** 完整的 AgentCommander 平台雏形，能同时管理多个 Agent 协作开发。

### Phase 4: Polish（第 9-10 周）— 打磨与优化

**目标：** 性能优化、体验完善、文档齐全。

| # | 任务 | 产出 | 验收标准 |
|---|------|------|---------|
| 4.1 | Prompt Cache Optimization | Cache 命中率 > 80% | Stable prefix 最大化 |
| 4.2 | Context Hygiene | 自适应压缩 | Snip → MicroCompact → Collapse → AutoCompact |
| 4.3 | Skill System | 可插拔技能包 | 发现、加载、forked execution |
| 4.4 | Telemetry & Analytics | 执行分析面板 | Token 消耗、时间分布、成功率 |
| 4.5 | Full Documentation | 用户手册 + API 文档 + 架构文档 | 新用户能 30 分钟内跑通 demo |

**里程碑 M4：** 发布 v1.0.0，可用于真实项目开发。

---

## 9. 风险与应对

| 风险 | 影响 | 概率 | 应对策略 |
|------|------|------|---------|
| LLM 输出不稳定性（同一 prompt 行为不一致） | 高 | 高 | Constitution 强约束 + Verification 门控 + 重试协议 |
| Context Window 溢出（大型项目上下文超限） | 中 | 高 | Context Hygiene 四级压缩 + File-First 模式 |
| 并发写入冲突（多 Agent 同时改文件） | 高 | 中 | 文件锁 + DAG 调度 + 冲突检测 |
| 工具调用安全（auto 模式下误操作） | 高 | 中 | Permission 4层决策 + 危险规则剥离 + Blast Radius 评估 |
| 过度工程（功能蔓延导致复杂度失控） | 中 | 中 | 严格遵循 MVP 路线图，每 Phase 有明确里程碑 |
| 供应商锁定（绑定特定 LLM） | 低 | 低 | LLM Adapter Layer 抽象，支持多后端 |

---

## 10. 附录

### 附录 A: 从 CLAUDE.md 到 constitution.md 的迁移指南

```bash
# 自动迁移脚本概念
# 1. 读取 CLAUDE.md
# 2. 提取 ## MANDATORY → Workflow 段落
# 3. 提取 ### Step X → Phase 定义
# 4. 提取 **DO/**DON'T/**规则 → Rules 段落
# 5. 提取 ⚠️ 阻塞处理 → Blocking Conditions
# 6. 提取 ## Commands → Tools/Prompts
# 7. 提取 ## Coding Conventions → Project Conventions
# 8. 包装 YAML frontmatter
# 9. 输出 constitution.md
```

### 附录 B: 从 task.json 到 task-manifest.json 的迁移

```javascript
// 迁移函数
function migrateTaskJson(old: LegacyTaskJson): TaskManifest {
  return {
    meta: {
      project: old.project,
      description: old.description,
      version: "2.0.0",
      lastUpdated: new Date().toISOString(),
      totalTasks: old.tasks.length,
      completedTasks: old.tasks.filter(t => t.passes).length,
      blockedTasks: 0,
    },
    tasks: old.tasks.map(t => ({
      ...t,
      status: t.passes ? 'completed' : 'pending',
      blocked: false,
      dependsOn: [],          // 需手动补充
      category: t.category || 'general',
      priority: inferPriority(t.id),  // 按 ID 推断
      tags: [],
      attempts: 0,
      assignee: undefined,
    })),
  };
}
```

### 附录 C: 术语对照表

| 术语 | 来源 | 定义 |
|------|------|------|
| Constitution | behavior-institutionalization | Agent 行为宪法，定义 do/dont 规则 |
| Task Manifest | task.json 进化 | 任务状态源，结构化的任务清单 |
| Session Log | progress.txt 进化 | Append-Only 的会话执行日志 |
| PDCA Loop | run-automation.sh | Plan → Do → Check → Act 循环 |
| Ephemeral Agent | agent-lifecycle-management | 无状态、一次性的 Worker Agent |
| Context Hygiene | context-hygiene-system | 上下文窗口健康管理 |
| Tool Pipeline | tool-runtime-pipeline | 工具调用的 7 阶段执行链 |
| Verification Gate | verification-agent | 独立、对抗性的验证门控 |
| Blast Radius | blast-radius-permission | 操作的影响范围评估 |
| Hook Governance | hook-governance-layer | 基于 Hook 的事件治理层 |
| Prompt Assembly | prompt-assembly-architecture | Cache-friendly 的提示词构建 |
| Static/Dynamic Boundary | prompt-cache-economics | Prompt 中稳定/变化内容的分隔线 |
| 3-Strike Protocol | planning-with-files | 三次失败的错误恢复协议 |
| File-Driven State | planning-with-files | 文件系统即数据库的设计模式 |

### 附录 D: 参考文献与致谢

1. **Anthropic - Effective Harnesses for Long-Running Agents** — 启发了 auto-coding-agent-demo 项目
2. **Claude Code Source Code (docs/markdown/)** — 45 章 Agent 源码学习材料，提供了 Context/Tools/Security/Multi-Agent 的理论支撑
3. **auto-coding-agent-demo Skills (13个)** — Agent 工程最佳实践的系统性知识库
4. **planning-with-files Skill** — 文件驱动规划的完整方法论
5. **AgentCommander PRD** — 多 Agent 编排平台的完整设计蓝图
6. **OpenBoss hello-nextjs 项目** — 经过 31 个任务验证的完整 Agent 工作流实战案例

---

> **文档结束**
> 
> *本 PRD 由 OpenBoss Agent Core 分析团队生成*
> *基于对 6 个源文件 + 13 个 Agent 工程技能 + 1 份设计文档的综合逆向分析*
> *日期: 2026-05-08*
