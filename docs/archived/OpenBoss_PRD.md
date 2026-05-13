---
AIGC: {"Label":"1","ContentProducer":"001191110108MA01KP2T5U00000","ProduceID":"d76cecbf8511c015a75a967b4739de17","ReservedCode1":"","ContentPropagator":"001191110108MA01KP2T5U00000","PropagateID":"d76cecbf8511c015a75a967b4739de17","ReservedCode2":""}
---

# OpenBoss — 超级 Agent 一人公司平台

## 产品需求文档（PRD）

> **版本**: v2.1  
> **日期**: 2026-05-12  
> **状态**: 初稿（含实战验证）  
> **定位**: 从 Agent 核心引擎到一人公司全栈 AI 操作系统的完整蓝图  
> **前置资产**: AI-Coding-Agent-PRD / AgentCommander PRD / OpenBoss Agent Core PRD / harness.md  
> **实战验证**: Spring FES Video 项目（31 个任务全部由 AI 在 10 小时内完成）

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [产品愿景：一人公司操作系统](#2-产品愿景一人公司操作系统)
3. [已有资产逆向分析与整合策略](#3-已有资产逆向分析与整合策略)
4. [OpenBoss 全景架构](#4-openboss-全景架构)
5. [核心概念体系](#5-核心概念体系)
   - 5.1 [Spec-Agentic（规范驱动的智能体范式）](#51-spec-agentic规范驱动的智能体范式)
   - 5.2 [Prompt Engineering Pipeline（提示词工程管线）](#52-prompt-engineering-pipeline提示词工程管线)
   - 5.3 [Context Engineering（上下文工程）](#53-context-engineering上下文工程)
   - 5.4 [Harness Engineering（约束工程）](#54-harness-engineering约束工程)
   - 5.5 [OpenClaw（开放式爪印协议）](#55-openclaw开放式爪印协议)
   - 5.6 [Hermes Agent（信使智能体）](#56-hermes-agent信使智能体)
6. [Agent Core 核心引擎（Phase 1 雏形）](#6-agent-core-核心引擎phase-1-雏形)
   - 6.1 [Constitution Engine（行为宪法引擎）](#61-constitution-engine行为宪法引擎)
   - 6.2 [State Manager（状态管理器）](#62-state-manager状态管理器)
   - 6.3 [Workflow Engine（工作流引擎）](#63-workflow-engine工作流引擎)
   - 6.4 [Context Engine（上下文引擎）](#64-context-engine上下文引擎)
   - 6.5 [Tool Pipeline（工具运行时管道）](#65-tool-pipeline工具运行时管道)
   - 6.6 [Verification System（验证系统）](#66-verification-system验证系统)
   - 6.7 [Prompt Assembly（提示词组装架构）](#67-prompt-assembly提示词组装架构)
   - 6.8 [Permission System（权限系统）](#68-permission-system权限系统)
   - 6.9 [Hook Bus（事件总线）](#69-hook-bus事件总线)
   - 6.10 [Lifecycle Manager（生命周期管理器）](#610-lifecycle-manager生命周期管理器)
7. [Scheduler 编排引擎（Phase 2）](#7-scheduler-编排引擎phase-2)
   - 7.1 [任务调度器](#71-任务调度器)
   - 7.2 [多 Agent 协作（Swarm）](#72-多-agent-协作swarm)
   - 7.3 [并发控制与隔离](#73-并发控制与隔离)
   - 7.4 [tmux 会话管理](#74-tmux-会话管理)
8. [一人公司场景设计（Phase 3）](#8-一人公司场景设计phase-3)
   - 8.1 [产品研发全链路自动化](#81-产品研发全链路自动化)
   - 8.2 [市场营销 Agent](#82-市场营销-agent)
   - 8.3 [运营客服 Agent](#83-运营客服-agent)
   - 8.4 [财务法务 Agent](#84-财务法务-agent)
   - 8.5 [知识管理 Agent](#85-知识管理-agent)
9. [数据模型与文件协议](#9-数据模型与文件协议)
10. [Agent 思维范式（Thinking Protocol）](#10-agent-思维范式thinking-protocol)
11. [技术选型](#11-技术选型)
12. [实施路线图](#12-实施路线图)
13. [风险与应对](#13-风险与应对)
14. [附录 A：实战验证分析（Spring FES Video 项目）](#14-附录-a实战验证分析spring-fes-video-项目)
15. [附录 B：与现有资产的关系映射](#15-附录-b与现有资产的关系映射)

---

## 1. 执行摘要

OpenBoss 是一个**以 Agent Core 引擎为心脏、以 Spec-Agentic 范式为骨架、以一人公司场景为终极目标的超级 AI Agent 操作系统**。它不是一个单纯的编码工具，也不是简单的多 Agent 编排平台——它是一套**从 Agent 基础运行时到企业级 AI 自动化管线的完整技术栈**。

### 1.1 核心理念

> Agent 的智能不来自模型本身，而来自**约束（Constitution）、流程（Workflow）、反馈（Feedback）和记忆（Memory）**的系统化组合。OpenBoss 将这四个维度工程化，使其成为可组合、可扩展、可度量的技术组件。

### 1.2 与现有资产的关系

OpenBoss 不是一个从零开始的项目。它是对以下已有资产的**战略性整合与架构升级**：

| 已有资产 | 当前定位 | 在 OpenBoss 中的角色 | 升级方向 |
|---------|---------|---------------------|---------|
| `AI-Coding-Agent-PRD.md` | 单 Agent 编码智能体设计（参考 Claude Code） | **单 Agent 运行时**的设计蓝图 | 增加多模态、非编码场景、可插拔 LLM |
| `AgentCommander PRD` | 多 Agent 编排指挥平台 | **Scheduler 编排层**的设计蓝图 | 增加一人公司场景、跨域协作 |
| `OpenBoss Agent Core PRD` | Agent 核心引擎（宪法/状态机/PDCA） | **Agent Core** 的直接前身 | 增加 Spec/Harness/Hermes 层 |
| `harness.md` | BDD/TDD 测试驱动约束 | **Harness Engineering** 的原型 | 扩展为全链路约束工程 |

### 1.3 三个核心问题

1. **为什么叫 OpenBoss？** — "Open" 代表开源、开放协议（OpenClaw）、可插拔架构；"Boss" 代表你是 Boss，AI 是你的员工。你是这个一人公司的 Boss，OpenBoss 是你的 AI 操作系统。
2. **为什么不直接用现有 Agent 框架？** — 现有框架（LangChain、AutoGen、CrewAI 等）解决的是"如何调用 LLM"的问题。OpenBoss 解决的是"如何让 LLM 在真实项目中可靠地、可追踪地、可复现地完成复杂工作"的问题。区别在于：前者是胶水层，后者是操作系统。
3. **核心目标是什么？** — **先搞出 Agent 核心的可靠雏形（Phase 1），再扩展为编排平台（Phase 2），最终实现一人公司全栈自动化（Phase 3）。**

---

## 2. 产品愿景：一人公司操作系统

### 2.1 一人公司的定义

"一人公司"不是真的只有一个人，而是**一个人的判断力 + AI 的执行力**。OpenBoss 的终极愿景是：一个有产品判断力的人，借助 OpenBoss 的 AI Agent 阵列，完成从产品定义、技术研发、设计交付、市场推广到运营客服的全链路工作。

### 2.2 愿景分层

```
┌──────────────────────────────────────────────────────────────────┐
│                    OpenBoss 一人公司愿景分层                       │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 3: 一人公司场景层                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ 产品研发  │ │ 市场营销  │ │ 运营客服  │ │ 财务法务  │            │
│  │ Agent    │ │ Agent    │ │ Agent    │ │ Agent    │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                  │
│  Layer 2: 编排调度层 (Scheduler)                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  多 Agent 协作 / 任务 DAG / 并发控制 / Feedback Loop     │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  Layer 1: Agent Core 引擎层  ← 当前阶段核心目标                   │
│  ┌────────────────────────────────────────────────────────┐     │
│  │  Constitution │ State │ Workflow │ Context │ Tool       │     │
│  │  Prompt │ Permission │ Hook │ Verification │ Lifecycle  │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  Layer 0: 工程范式层                                              │
│  ┌──────┐ ┌──────┐ ┌────────┐ ┌─────────┐ ┌──────┐ ┌──────┐   │
│  │ Spec │ │Prompt│ │ Context│ │ Harness │ │Open  │ │Hermes│   │
│  │Agentic│ │ Eng  │ │ Eng    │ │ Eng     │ │ Claw │ │Agent │   │
│  └──────┘ └──────┘ └────────┘ └─────────┘ └──────┘ └──────┘   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 核心价值主张

| 维度 | 价值描述 |
|------|----------|
| **可靠性** | 基于宪法引擎的强制行为约束，杜绝 Agent "幻觉"和"自欺欺人" |
| **可追溯性** | 文件驱动的状态管理，每一次操作都有完整的事件日志 |
| **可扩展性** | 从单 Agent 到多 Agent，从编码到全业务线，渐进式扩展 |
| **可插拔性** | LLM 后端可替换（Claude/GPT/GLM/本地模型），工具链可自定义 |
| **工程化** | 将 Prompt/Context/Harness 从"玄学"变为可度量、可迭代的工程管线 |

---

## 3. 已有资产逆向分析与整合策略

### 3.1 源材料全景图

通过对四份已有资产的深度分析，我们提取出以下关键架构发现：

**发现 1：Agent 本质上是一台 PDCA 状态机**

从 `OpenBoss Agent Core PRD` 和 `AgentCommander PRD` 中一致发现的架构模式：Agent 不是聊天机器人，而是**有限状态机驱动的 PDCA（Plan-Do-Check-Act）循环机器**。所有已有设计都围绕以下循环展开：

```
读取任务 → 理解需求 → 制定方案 → 执行实现 → 验证测试 → 记录提交 → 下一个任务
```

**发现 2：文件即状态是验证过的最佳实践**

所有已有项目中，`task.json` 是唯一的状态源（Source of Truth），`progress.txt` 是不可变的追加日志。这意味着 Agent 可以在任何时刻被杀掉、重启而不丢失状态——这在生产环境中已被 31 个任务的完整执行所验证。

**发现 3：行为宪法（Constitution）是控制 Agent 的核心手段**

`CLAUDE.md` 的实践证明：将期望行为编码为可执行的 do/dont 规则集，比依赖 prompt 引导有效得多。这直接催生了 Spec-Agentic 范式。

**发现 4：Harness 约束（BDD/TDD）是实现可靠性的关键**

`harness.md` 揭示的 BDD + TDD 双重约束模式表明：Agent 的可靠性不来自更聪明的模型，而来自更严格的约束。

**发现 5：上下文工程是效率的瓶颈**

`AI-Coding-Agent-PRD` 中详细设计的上下文管理系统证明：Context Window 是最稀缺的资源，上下文组装策略直接决定了 Agent 的效率和质量。

### 3.2 整合策略

OpenBoss 不是简单地将四份文档"合在一起"，而是进行**架构级整合**：

| 整合维度 | 策略 | 产出 |
|---------|------|------|
| **架构统一** | 统一为四层架构（工程范式 → Agent Core → Scheduler → 场景） | 消除重复设计，明确层次边界 |
| **接口标准化** | 定义统一的工具接口、状态接口、事件接口 | 模块可独立替换和测试 |
| **概念升级** | 将分散的设计模式提炼为六大工程范式（见第5章） | 从"经验"升级为"方法论" |
| **渐进路线** | Phase 1 聚焦 Agent Core，Phase 2 扩展到编排，Phase 3 覆盖全场景 | 降低初期复杂度，快速验证 |

---

## 4. OpenBoss 全景架构

### 4.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OpenBoss 全景架构                             │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Layer 3: 场景层（一人公司 Agent 阵列）                       │    │
│  │                                                              │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │    │
│  │  │Coder    │ │Designer │ │Marketer │ │Support  │  ...      │    │
│  │  │Agent    │ │Agent    │ │Agent    │ │Agent    │           │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │    │
│  │       └───────────┴───────────┴───────────┘                  │    │
│  │                         │                                    │    │
│  └─────────────────────────┼────────────────────────────────────┘    │
│                            │                                        │
│  ┌─────────────────────────▼────────────────────────────────────┐    │
│  │  Layer 2: 编排调度层（Scheduler / AgentCommander）            │    │
│  │                                                              │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │  │ Task     │  │ Feedback │  │ Concurren│  │ Hermes   │    │    │
│  │  │ Scheduler│  │ Loop     │  │ cy Ctrl  │  │ Bus      │    │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │    │
│  │  │ tmux Mgr │  │ Git Wf   │  │ Monitor  │                  │    │
│  │  └──────────┘  └──────────┘  └──────────┘                  │    │
│  └─────────────────────────┬────────────────────────────────────┘    │
│                            │                                        │
│  ┌─────────────────────────▼────────────────────────────────────┐    │
│  │  Layer 1: Agent Core 引擎层                                  │    │
│  │                                                              │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │Constitution  │  │ State        │  │ Context Engine    │  │    │
│  │  │Engine        │  │ Manager      │  │                   │  │    │
│  │  │(行为宪法)     │  │(状态管理)     │  │(上下文组装)       │  │    │
│  │  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │    │
│  │         │                 │                    │             │    │
│  │         ▼                 ▼                    ▼             │    │
│  │  ┌─────────────────────────────────────────────────────┐   │    │
│  │  │              Workflow Engine (PDCA)                  │   │    │
│  │  │  Analyze → Plan → Implement → Verify → Record →     │   │    │
│  │  │  Commit (带 3-Strike 重试协议)                       │   │    │
│  │  └─────────────────────────────────────────────────────┘   │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │Tool Pipeline │  │Verification  │  │Prompt Assembly   │  │    │
│  │  │(工具管道)     │  │System(验证)  │  │(提示词组装)      │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │    │
│  │  │Permission    │  │Hook Bus      │  │Lifecycle Manager │  │    │
│  │  │System(权限)   │  │(事件总线)    │  │(生命周期)        │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────┘  │    │
│  └─────────────────────────┬────────────────────────────────────┘    │
│                            │                                        │
│  ┌─────────────────────────▼────────────────────────────────────┐    │
│  │  Layer 0: 工程范式层                                          │    │
│  │                                                              │    │
│  │  ┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌────┐  │    │
│  │  │ Spec  │ │Prompt │ │Context │ │Harness │ │Open  │ │Herm│  │    │
│  │  │Agentic│ │ Eng   │ │ Eng    │ │ Eng    │ │ Claw │ │ es │  │    │
│  │  └───────┘ └───────┘ └────────┘ └────────┘ └──────┘ └────┘  │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  持久层：File System + LLM Adapter                           │    │
│  │  constitution.md │ task-manifest.json │ session-log.md       │    │
│  │  memory/ │ artifacts/ │ Claude/GLM/OpenAI API               │    │
│  └──────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 架构原则

| 原则 | 说明 | 来源 |
|------|------|------|
| **File-First State** | 所有状态以文件形式存在，内存只做缓存。Agent 可随时被杀掉重启而不丢失状态 | 已有项目验证 |
| **Constitution-Driven** | 行为由宪法文件驱动，不硬编码在程序中。规则可版本化、可审计 | CLAUDE.md 实践 |
| **Ephemeral Workers** | Agent 无状态、一次性、由外部调度。每次启动都是全新的，通过文件系统恢复状态 | run-automation.sh |
| **Verification-Gated** | 所有交付物必须经过验证门控。不允许没有证据的"完成"声明 | progress.txt 实践 |
| **Event-Sourced** | 所有操作通过事件日志可追溯。支持回放、调试和审计 | Hook 系统 |
| **Adapter Pattern** | LLM 后端可插拔，不绑定特定厂商。今天用 Claude，明天换 GLM | 可扩展性要求 |
| **Spec-First** | 先定义规范（Spec），再生成实现。Agent 基于规范工作，而非自由发挥 | Spec-Agentic 范式 |
| **Harness-Gated** | 用 BDD/TDD 双重约束保障质量。Agent 的每一步都受自动化测试约束 | harness.md |
| **Graceful Degradation** | 任何组件失败不会导致数据损坏。系统具备完善的错误恢复协议 | 鲁棒性要求 |

### 4.3 模块依赖图

```
Level 0 (基础设施):
  File System ← 所有模块依赖
  LLM Adapter ← 所有需要 LLM 推理的模块依赖

Level 1 (核心引擎):
  Constitution Engine ← 定义 Agent 能做什么/不能做什么
  State Manager ← 读写任务状态
  Prompt Assembly ← 组装发送给 LLM 的 prompt
  Permission System ← 控制工具调用权限

Level 2 (运行时):
  Context Engine ← 依赖 Constitution + State + Prompt
  Workflow Engine ← 依赖 State + Context + Constitution
  Tool Pipeline ← 依赖 Constitution(权限) + Permission
  Hook Bus ← 独立运行，被其他模块调用

Level 3 (保障):
  Verification System ← 依赖 Tool Pipeline（需要运行命令）
  Lifecycle Manager ← 依赖 Workflow Engine（管理启停）

Level 4 (编排):
  Scheduler ← 依赖 Lifecycle + State + Hook
  Hermes Bus ← 依赖 Hook Bus（跨 Agent 通信）
  Concurrency Controller ← 依赖 State + Hook

Level 5 (场景):
  Coder/Designer/Marketer/Support Agent ← 依赖 Agent Core + Scheduler
```

---

## 5. 核心概念体系

OpenBoss 引入六大工程范式（Engineering Paradigm），它们是整个系统的理论基础和方法论指导。这些范式不是抽象的理论——每一个都直接对应具体的模块设计和实现。

### 5.1 Spec-Agentic（规范驱动的智能体范式）

#### 5.1.1 定义

Spec-Agentic 是 OpenBoss 的核心设计哲学：**Agent 的一切行为都应基于显式的规范（Specification），而非隐式的提示词引导**。规范是"意图的确定性表达"，它消除歧义、约束行为、提供验证基准。

#### 5.1.2 核心思想

传统 Agent 的运作方式是：
```
用户模糊意图 → LLM 自由发挥 → 不可预测的结果
```

Spec-Agentic 的运作方式是：
```
用户意图 → Spec（确定性规范）→ Agent 基于规范执行 → 可验证的结果
```

#### 5.1.3 Spec 的三种类别

| 类别 | 描述 | 示例 |
|------|------|------|
| **Constitution Spec** | Agent 的行为宪法（全局规则） | "禁止跳过测试直接标记完成" |
| **Task Spec** | 单个任务的执行规范（BDD 格式） | task.json 中的 steps + 验收标准 |
| **Output Spec** | 产出物的质量规范 | "API 响应时间 < 200ms，错误码符合 REST 规范" |

#### 5.1.4 Spec 生命周期

```
需求文档（PRD）
    │
    ▼ Planner Agent
任务 Spec（task-manifest.json）
    │
    ▼ 逐任务分解
BDD 场景（Given/When/Then）
    │
    ▼ Coder Agent 实现
代码实现
    │
    ▼ Verification Agent
验证结果（PASS/FAIL/PARTIAL）
    │
    ▼ 通过 → Atomic Commit
    │ 失败 → Retry Protocol
    ▼
完成
```

#### 5.1.5 在 OpenBoss 中的实现

Spec-Agentic 在系统中的直接体现是 **Constitution Engine**（第6.1节）。Constitution 文件就是最高优先级的 Spec，它定义了 Agent 的身份、工作流步骤、行为规则、阻塞条件和权限映射。此外，task-manifest.json 中的每个任务都是一个小型 Spec，包含明确的 steps 和验收标准。

### 5.2 Prompt Engineering Pipeline（提示词工程管线）

#### 5.2.1 定义

在 OpenBoss 中，Prompt Engineering 不是"写好一段 system prompt 然后不动"，而是一条**持续的、可度量、可迭代的工程管线**。每一个发给 LLM 的 prompt 都是经过精心组装的产物，包含多个来源、多个层级的内容。

#### 5.2.2 Prompt 三层架构

参考 `AI-Coding-Agent-PRD` 中的上下文管理和 `OpenBoss Agent Core PRD` 中的 Prompt Assembly 设计，OpenBoss 采用三层 Prompt 架构：

```
┌────────────────────────────────────────────────────────────┐
│                   Prompt Window (LLM Input)                  │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│  LAYER 1: STATIC ZONE (Prompt Cache 友好前缀)               │
│  ═══════════════════════════════════════════════════════   │
│  [Constitution: Identity + Rules]     ~2K tokens  几乎不变  │
│  [Constitution: Workflow Steps]       ~1K tokens  几乎不变  │
│  [Constitution: Permissions]          ~500 tokens 几乎不变   │
│  [Tool Schemas]                       ~3K tokens  工具集稳定 │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│  LAYER 2: SEMI-STATIC ZONE (低频变化)                       │
│  ═══════════════════════════════════════════════════════   │
│  [Project Context / README]           ~2K tokens  项目级    │
│  [Architecture Knowledge]             ~3K tokens  架构文档   │
│  [Memory: Long-term Knowledge]        ~2K tokens  跨会话    │
│  [Recent Session Log Summary]         ~1K tokens  进度日志   │
│                                                             │
│  ═══════════════════════════════════════════════════════   │
│  LAYER 3: DYNAMIC ZONE (每次请求变化)                       │
│  ═══════════════════════════════════════════════════════   │
│  [Current Task Spec]                 ~1K tokens  当前任务   │
│  [Related Source Files]               ~10K tokens 相关代码   │
│  [Recent Conversation History]        ~20K tokens 对话历史   │
│  [Tool Call Results]                  ~5K tokens  工具结果   │
│  [Error Outputs / Logs]               ~2K tokens  错误日志   │
│  [Safety Margin]                      ~5K tokens  安全余量   │
│                                                             │
│  Total: ~47K tokens (假设 200K 上下文窗口，使用约 23%)       │
└────────────────────────────────────────────────────────────┘
```

#### 5.2.3 Prompt Cache 经济学

借鉴 prompt-cache-economics 技能，OpenBoss 的 Prompt 设计遵循以下缓存优化原则：

| 策略 | 说明 | 预期节省 |
|------|------|----------|
| **Static Prefix 稳定化** | Constitution 和 Tool Schema 放在最前面，几乎不变 | 减少约 40% 的重复计算 |
| **Dynamic Zone 滚动** | 对话历史使用滑动窗口，超出预算时触发 Compact | 控制总 token 使用在预算内 |
| **按需注入** | 源代码文件只在相关时注入，不一次性加载整个代码库 | 减少 60%+ 的无效上下文 |
| **去重优化** | 同一文件同一范围多次读取时返回存根引用 | 避免重复内容占位 |

#### 5.2.4 Prompt 版本管理

每个 prompt 模板都有版本号，记录在 `constitution.md` 的 frontmatter 中。当 Constitution 更新时，版本号递增，便于追踪哪些 prompt 变化导致了行为差异。

### 5.3 Context Engineering（上下文工程）

#### 5.3.1 定义

Context Engineering 是 OpenBoss 中最关键的工程实践。它的核心挑战是：**Context Window 是有限的资源（类比 RAM），但项目信息是近乎无限的（类比 Disk）**。Context Engine 的职责是在两者之间做最优权衡。

#### 5.3.2 上下文 = RAM，文件系统 = Disk

这是 OpenBoss 最核心的类比（源自 planning-with-files 技能）：

```
Context Window (RAM):
  - 容量有限（200K tokens ≈ 150K 字）
  - 易失性（每次会话结束后清空）
  - 速度快（LLM 可以直接"看到"）
  - 成本高（按 token 计费）

File System (Disk):
  - 容量无限（TB 级）
  - 持久性（写入后永久存在）
  - 速度相对慢（需要 Agent 主动读取）
  - 成本低（本地存储几乎免费）
```

#### 5.3.3 上下文组装策略

Context Engine 在每次 LLM 调用前执行以下组装流程：

```typescript
interface ContextAssemblyRequest {
  task: Task;                          // 当前任务
  phase: WorkflowPhase;                // 当前工作流阶段
  conversationHistory: Message[];      // 对话历史
  availableTokenBudget: number;        // 可用 token 预算
}

interface ContextAssemblyResult {
  staticPrompt: string;       // LAYER 1: 稳定前缀（宪法 + 工具 Schema）
  semiStaticContext: string;  // LAYER 2: 半静态上下文（项目 + 记忆 + 日志）
  dynamicContext: string;     // LAYER 3: 动态上下文（任务 + 代码 + 工具结果）
  totalTokens: number;
  cacheHitTokens: number;     // 命中缓存的 token 数
  compressionApplied: boolean; // 是否触发了压缩
}
```

#### 5.3.4 上下文压缩策略

当上下文接近 token 上限时，Context Engine 触发压缩（Compact）操作：

| 压缩策略 | 触发条件 | 方法 | 保留规则 |
|---------|---------|------|---------|
| **滑动窗口** | 对话历史超过 N 轮 | 保留最近 N 轮，压缩早期对话 | 最后 3 轮完整保留 |
| **关键信息提取** | 压缩早期对话 | 调用轻量级 LLM 生成摘要 | 错误信息、用户明确要求保留 |
| **去重优化** | 同一文件多次读取 | 返回存根引用 | 首次读取返回完整内容 |
| **源代码裁剪** | 文件过大 | 只保留相关函数/类 | 保留 import、类型定义、export |

#### 5.3.5 跨会话记忆管理

长期记忆采用 `memory/` 目录管理：

```
memory/
├── MEMORY.md          # 核心记忆文件（项目级知识、决策记录）
├── 2026-05-12.md      # 按日期的详细工作日志
├── decisions/
│   ├── arch-001.md    # 架构决策记录（ADR 格式）
│   └── arch-002.md
└── lessons/
    ├── error-patterns.md   # 错误模式库
    └── best-practices.md   # 最佳实践库
```

记忆管理采用**重要性评分 + 滑动窗口**相结合的策略：高优先级任务、核心架构决策会获得更高的评分，其详细信息被保留更长的时间。当总 token 量超过预算时，优先丢弃重要性评分低的内容。

### 5.4 Harness Engineering（约束工程）

#### 5.4.1 定义

Harness Engineering 是 OpenBoss 的质量保障体系。其核心理念来自 `harness.md`：**Agent 的可靠性不来自更聪明的模型，而来自更严格的约束。** 约束（Harness）是套在 Agent 上的"安全带和护栏"，确保 Agent 的每一步都在可控范围内。

#### 5.4.2 双重约束模型

```
┌─────────────────────────────────────────────────────────┐
│                Harness 双重约束模型                       │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  BDD 约束（行为约束）                              │  │
│  │                                                   │  │
│  │  task.json 中的 steps 就是 BDD 场景:              │  │
│  │  Given: 已有代码库和依赖                           │  │
│  │  When: 执行当前任务                                │  │
│  │  Then: 产出物满足验收标准                          │  │
│  │                                                   │  │
│  │  作用: 确保 Agent 做了"对的事情"                   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │  TDD 约束（实现约束）                              │  │
│  │                                                   │  │
│  │  测试代码先于实现代码:                             │  │
│  │  1. 根据 task.json 写测试                          │  │
│  │  2. 运行测试（应该失败）                           │  │
│  │  3. 实现功能使测试通过                             │  │
│  │  4. 重构（如果必要，避免屎山）                     │  │
│  │                                                   │  │
│  │  作用: 确保 Agent "正确地做事"                     │  │
│  └───────────────────────────────────────────────────┘  │
│                                                          │
│  BDD 回答 "做什么" → TDD 回答 "怎么做对"                │
│  两者交叉验证，形成闭环                                  │
└─────────────────────────────────────────────────────────┘
```

#### 5.4.3 Harness 在系统中的体现

| 约束类型 | 系统模块 | 实现方式 |
|---------|---------|---------|
| 行为约束 | Constitution Engine | do/dont 规则集、阻塞条件、权限映射 |
| 验证约束 | Verification System | 五级验证门控（L1 基线 → L5 回归） |
| 状态约束 | State Manager | 文件锁、乐观并发控制、DAG 依赖检查 |
| 上下文约束 | Context Engine | Token 预算控制、压缩策略、去重优化 |
| 提交约束 | Workflow Engine | Atomic Commit Protocol、预提交检查清单 |
| 安全约束 | Permission System | Allow/Deny/Ask 规则引擎、沙箱隔离 |

#### 5.4.4 Anti-Cheat 机制

Agent 有一个常见问题：**自欺欺人**（声称做了某事但实际没做）。Harness Engineering 内建了 Anti-Cheat 机制：

| 作弊模式 | 检测方式 | 防御措施 |
|---------|---------|---------|
| 声称跑了测试但没贴输出 | 检查工具调用记录中是否有测试命令 | 要求提供完整的命令输出 |
| 跳过失败的测试只报告通过的 | 要求提供全量测试输出 | 自动解析测试报告中的失败数 |
| 假标记任务完成 | 检查 task.json 中 passes 字段 | 只允许 Verification System 修改 passes |
| 修改已有任务描述 | 监控 task-manifest.json 的变更 | Constitution 中明令禁止 |

### 5.5 OpenClaw（开放式爪印协议）

#### 5.5.1 定义

OpenClaw 是 OpenBoss 的**开放式互操作协议**，定义了 Agent 之间、Agent 与外部系统之间的标准通信接口。"Claw"（爪印）象征 Agent 留下的标准化足迹——每一步操作都是可追踪、可验证的。

#### 5.5.2 设计目标

| 目标 | 描述 |
|------|------|
| **互操作性** | 不同的 Agent 实现（Claude Code、Cursor、自定义 Agent）可以通过 OpenClaw 协议互通 |
| **可追溯性** | 所有操作以标准化的事件格式记录，支持回放和审计 |
| **可扩展性** | 协议支持自定义事件类型和工具定义，不限制 Agent 的能力边界 |
| **安全性** | 协议内建权限检查和签名验证机制 |

#### 5.5.3 协议栈

```
┌─────────────────────────────────────────────┐
│  OpenClaw Protocol Stack                    │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ L4: Application Protocol              │   │
│  │  - Task Protocol (任务分配与报告)      │   │
│  │  - Message Protocol (Agent 间消息)     │   │
│  │  - Event Protocol (事件通知)          │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ L3: Tool Protocol                     │   │
│  │  - Tool Schema (工具定义标准)         │   │
│  │  - Tool Invocation (调用协议)         │   │
│  │  - Tool Result (结果格式)             │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ L2: Transport                         │   │
│  │  - HTTP POST (实时事件上报)           │   │
│  │  - JSONL File (持久化日志)            │   │
│  │  - WebSocket (实时推送)               │   │
│  │  - Stdio (tmux 会话通信)             │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ L1: Encoding                          │   │
│  │  - JSON (结构化数据)                  │   │
│  │  - JSONL (追加日志)                   │   │
│  │  - Markdown (人类可读文档)             │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

#### 5.5.4 标准事件格式

```typescript
interface OpenClawEvent {
  // 协议版本
  protocol: 'openclaw/v1';
  
  // 事件元数据
  eventId: string;        // UUID
  timestamp: ISO8601;     // 事件时间
  sessionId: string;      // 会话 ID
  agentId: string;        // Agent ID
  
  // 事件内容
  type: EventType;        // 事件类型
  payload: unknown;       // 事件数据
  
  // 追踪信息
  traceId: string;        // 链路追踪 ID（用于关联多个事件）
  parentEventId?: string; // 父事件 ID（用于事件树）
}

type EventType =
  // Agent 生命周期事件
  | 'agent.created'
  | 'agent.started'
  | 'agent.stopped'
  | 'agent.error'
  // 任务事件
  | 'task.selected'
  | 'task.started'
  | 'task.completed'
  | 'task.failed'
  | 'task.blocked'
  // 工具事件
  | 'tool.before_call'
  | 'tool.after_call'
  | 'tool.error'
  // 工作流事件
  | 'workflow.phase_changed'
  | 'workflow.retry'
  | 'workflow.completed'
  // 通信事件
  | 'message.sent'
  | 'message.received'
  // 系统事件
  | 'system.alert'
  | 'system.heartbeat';
```

### 5.6 Hermes Agent（信使智能体）

#### 5.6.1 定义

Hermes Agent 是 OpenBoss 中的**跨 Agent 通信代理**。它的名字来源于希腊神话中的信使神 Hermes。在多 Agent 协作场景中，Hermes 负责消息路由、协议转换、冲突调解和状态同步。

#### 5.6.2 核心职责

| 职责 | 描述 | 触发场景 |
|------|------|---------|
| **消息路由** | 将消息从发送者路由到正确的接收者 | Agent A 需要通知 Agent B 任务完成 |
| **协议转换** | 在不同 Agent 实现之间转换消息格式 | Claude Code Agent ↔ 自定义 Agent 通信 |
| **冲突调解** | 当多个 Agent 修改同一文件时，协调冲突解决 | 并行开发中的文件冲突 |
| **状态同步** | 将一个 Agent 的状态变更同步给相关方 | 任务状态变更通知 |
| **消息聚合** | 将多个 Agent 的更新聚合为统一的状态报告 | 定时向 Boss 汇报进度 |
| **优先级仲裁** | 当多个 Agent 同时请求同一资源时，按优先级裁决 | 并发执行中的资源竞争 |

#### 5.6.3 消息协议

```typescript
type HermesMessage =
  | { type: 'task_handoff'; from: string; to: string; task: TaskRef; summary: string }
  | { type: 'code_review_request'; from: string; to: string; files: string[]; prUrl?: string }
  | { type: 'review_result'; from: string; to: string; taskId: number; verdict: 'approved' | 'rejected' | 'needs_changes'; comments: string[] }
  | { type: 'conflict_notification'; files: string[]; agents: string[]; suggestedResolution?: string }
  | { type: 'status_broadcast'; from: string; status: AgentStatus; currentTask?: TaskRef }
  | { type: 'escalation'; from: string; to: 'boss'; task: TaskRef; reason: string; needsHumanInput: boolean }
  | { type: 'knowledge_share'; from: string; topic: string; content: string; relevance: string[] };
```

#### 5.6.4 在架构中的位置

Hermes Agent 是 Layer 2（编排调度层）的核心组件，它桥接了 Agent Core 层和场景层。在 Phase 1（单 Agent）中，Hermes 不是必需的。在 Phase 2（多 Agent）中，Hermes 是实现 Agent 间协作的关键基础设施。

---

## 6. Agent Core 核心引擎（Phase 1 雏形）

> **本章是当前阶段的核心交付物。Agent Core 是 OpenBoss 的心脏，所有上层功能都建立在这个引擎之上。**

### 6.1 Constitution Engine（行为宪法引擎）

#### 6.1.1 职责

解析、执行和 enforcing Agent 的行为宪法。它是 Spec-Agentic 范式的直接实现——将规范编译为可在运行时查询和执行的规则对象。

#### 6.1.2 Constitution 文件结构

```markdown
---
version: "1.0"
project: "openboss"
enforcement: "strict"  # strict | lenient | advisory
---

## 1. Identity（身份定义）
name: "OpenBoss Agent"
role: "全栈开发工程师 + 产品助手"
scope: "代码实现、测试、文档、自动化任务"

## 2. Workflow（强制工作流）
### Phase 1: Initialize
- action: HEALTH_CHECK
- checks: ["dev server running", "dependencies installed"]
- skip_condition: "环境已就绪"

### Phase 2: Select Task
- action: READ_STATE
- source: "task-manifest.json"
- selection_criteria:
    - passes == false
    - dependencies_satisfied == true
    - NOT blocked
    - highest priority first

### Phase 3: Analyze
- action: DEEP_UNDERSTAND
- goals: ["理解任务需求", "阅读相关代码", "识别技术约束"]

### Phase 4: Plan
- action: CREATE_PLAN
- output: "implementation plan"

### Phase 5: Implement
- action: EXECUTE_TASK
- rules:
    - MUST follow all steps in task.steps
    - MUST follow existing code patterns
    - MUST NOT skip any step

### Phase 6: Verify
- action: VERIFICATION_GATE
- levels:
    - L1_BASELINE: ["lint", "build"]
    - L2_TYPECHECK: ["tsc --noEmit"]
    - L3_BROWSER: required_if "task involves UI changes"
    - L4_ADVERSARIAL: optional
    - L5_REGRESSION: optional
- failure_action: FIX_AND_RETRY

### Phase 7: Record
- action: APPEND_LOG
- target: "session-log.md"
- format: standardized template

### Phase 8: Commit
- action: ATOMIC_COMMIT
- includes: [code_changes, session_log, task_manifest]
- message_format: "[Task {id}] {title} - completed"
- pre_conditions: ALL_VERIFICATION_PASSED

## 3. Rules（行为规则集）
### Task Rules
- DO_IMPLEMENT_ALL_STEPS
- DONT_SKIP_TESTING
- DONT_REMOVE_TASKS
- MUST_FOLLOW_PATTERNS

### Communication Rules
- REPORT_BLOCKING_STANDARDIZED
- LOG_EVERYTHING
- HONEST_REPORTING

### Safety Rules
- NO_COMMIT_WHEN_BLOCKED
- NO_FALSE_COMPLETION
- ASK_WHEN_UNSURE

## 4. Blocking Conditions
### ENVIRONMENT_MISSING
  triggers: [".env not found", "db not configured", "deps not installed"]
  action: STOP_AND_REPORT

### EXTERNAL_DEP_DOWN
  triggers: ["API 503", "service timeout"]
  action: MARK_BLOCKED_CONTINUE_NEXT

### TEST_IMPOSSIBLE
  triggers: ["requires real account", "requires hardware"]
  action: STOP_AND_REPORT

## 5. Permissions
tools:
  Bash:
    allowed: ["npm *", "npx *", "git *", "cat *", "ls *"]
    dangerous: ["rm -rf *", "sudo *"]
    requires_confirmation: true_for_dangerous
  Write/Edit:
    scope: "project_directory_only"
    protected: [".env*", "*.key", "credentials*"]
  WebFetch:
    rate_limit: "10 req/min"
```

#### 6.1.3 引擎接口

```typescript
interface ConstitutionRule {
  id: string;
  type: 'DO' | 'DONT' | 'MUST' | 'ESCALATE' | 'PERMIT';
  scope: WorkflowPhase;
  condition?: string;
  message: string;
  antiCheat?: string;
  sourceLine: number;
}

interface ConstitutionDocument {
  version: string;
  metadata: { project: string; enforcement: string };
  workflow: WorkflowPhase[];
  rules: ConstitutionRule[];
  blockingConditions: BlockingCondition[];
  permissions: PermissionMap;
}

class ConstitutionEngine {
  parse(markdown: string): ConstitutionDocument;
  getRulesForPhase(phase: WorkflowPhase): ConstitutionRule[];
  checkViolation(action: AgentAction): RuleViolation | null;
  getBlockingCondition(type: string): BlockingCondition;
  generatePhaseInstructions(phase: WorkflowPhase): string;
  generateSystemPrompt(): string;  // Prompt Cache 稳定前缀
}
```

### 6.2 State Manager（状态管理器）

#### 6.2.1 职责

管理任务状态的读写，保证一致性和并发安全。所有状态以文件形式持久化（File-First 原则）。

#### 6.2.2 数据结构

```typescript
interface TaskManifest {
  meta: {
    project: string;
    version: string;
    lastUpdated: ISO8601;
    totalTasks: number;
    completedTasks: number;
    blockedTasks: number;
  };
  tasks: Task[];
}

interface Task {
  id: number;
  title: string;
  description: string;
  steps: string[];                // BDD 格式的执行步骤
  status: 'pending' | 'in_progress' | 'needs_input' | 'blocked' | 'completed' | 'failed' | 'skipped';
  passes: boolean;
  blocked: boolean;
  blockReason?: string;
  dependsOn: number[];
  category: string;
  priority: 'P0' | 'P1' | 'P2' | 'P3';
  tags: string[];
  createdAt?: ISO8601;
  startedAt?: ISO8601;
  completedAt?: ISO8601;
  assignee?: string;
  attempts: number;
  lastError?: string;
}
```

#### 6.2.3 核心操作

```typescript
class StateManager {
  // 读取（无锁）
  readManifest(): TaskManifest;
  getTask(id: number): Task | undefined;
  getNextTask(): Task | null;
  getStats(): TaskStats;

  // 写入（需加文件锁）
  startTask(id: number): void;
  completeTask(id: number): void;
  blockTask(id: number, reason: string): void;
  failTask(id: number, error: string): void;

  // 查询
  areDependenciesMet(taskId: number): boolean;
  getTopologicallySortedTasks(): Task[];
}
```

#### 6.2.4 任务选择算法

```typescript
function selectNextTask(manifest: TaskManifest): Task | null {
  const candidates = manifest.tasks.filter(t =>
    t.status === 'pending' &&
    !t.blocked &&
    t.passes === false &&
    areDependenciesMet(t.id)
  );

  return candidates.sort((a, b) => {
    // P0 > P1 > P2 > P3
    const pOrder = { P0: 0, P1: 1, P2: 2, P3: 3 };
    const pDiff = pOrder[a.priority] - pOrder[b.priority];
    if (pDiff !== 0) return pDiff;
    // 依赖下游最多的先做
    return countDependents(b.id) - countDependents(a.id) || a.id - b.id;
  })[0] ?? null;
}
```

### 6.3 Workflow Engine（工作流引擎）

#### 6.3.1 职责

执行 PDCA 循环，驱动 Agent 完成一个完整的任务周期。这是 Agent Core 的核心控制流。

#### 6.3.2 PDCA 状态机

```
              ┌─────────────────┐
              │   INITIALIZE    │
              │  (环境健康检查)  │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
        ┌────→│  SELECT_TASK    │◄────┐
        │     │  (选择下一个任务) │     │
        │     └────────┬────────┘     │
        │              │              │
        │              ▼              │
        │     ┌─────────────────┐     │
        │     │    ANALYZE      │     │
        │     │  (深入理解任务)  │     │
        │     └────────┬────────┘     │
        │              │              │
        │              ▼              │
        │     ┌─────────────────┐     │
        │     │     PLAN        │     │
        │     │  (制定实现方案)  │     │
        │     └────────┬────────┘     │
        │              │              │
        │              ▼              │
        │     ┌─────────────────┐     │
        │     │   IMPLEMENT     │     │
        │     │  (执行实现)      │     │
        │     └────────┬────────┘     │
        │              │              │
        │              ▼              │
        │     ┌─────────────────┐     │
        │     │    VERIFY       │     │
        │     │ (验证门控测试)   │     │
        │     └────────┬────────┘     │
        │              │              │
        │        ┌─────┴─────┐       │
        │        │ PASS       │ FAIL  │
        │        ▼           ▼       │
        │  ┌──────────┐ ┌─────────┐  │
        │  │ RECORD   │ │ RETRY   │  │
        │  │ → COMMIT │ │ (≤3次)  │  │
        │  └────┬─────┘ └────┬────┘  │
        │       │            │       │
        └───────┘            └───────┘
                    │
               3次失败后
                    │
                    ▼
              ┌──────────┐
              │  FAILED  │
              │(需人工介入)│
              └──────────┘
```

#### 6.3.3 主循环伪代码

```typescript
class WorkflowEngine {
  async runCycle(): Promise<WorkflowResult> {
    const MAX_RETRIES = 3;

    // Phase 1: 环境初始化
    await this.executeInitialize();

    // Phase 2: 选择任务
    const task = this.stateManager.getNextTask();
    if (!task) return { status: 'NO_MORE_TASKS' };
    this.hookBus.emit('task:selected', { taskId: task.id });
    this.stateManager.startTask(task.id);

    // Phase 3: 深度分析任务
    const analysis = await this.analyzeTask(task);

    // Phase 4: 制定实现方案
    const plan = await this.createPlan(task, analysis);

    // Phase 5-8: Implement → Verify → Record → Commit（带重试）
    for (let retry = 0; retry < MAX_RETRIES; retry++) {
      try {
        // Implement
        const changes = await this.implementTask(task, plan);

        // Verify
        const result = await this.verifier.verify(task, changes);

        if (result.verdict === 'PASS') {
          // Record
          await this.logger.record(task, changes, result);
          // Atomic Commit
          const hash = await this.atomicCommit(task);
          this.stateManager.completeTask(task.id);
          return { status: 'SUCCESS', taskId: task.id, commitHash: hash, retries: retry };
        } else if (result.verdict === 'BLOCKED') {
          this.stateManager.blockTask(task.id, result.reason);
          return { status: 'BLOCKED', taskId: task.id };
        }
        // FAIL → 继续重试
      } catch (error) {
        if (retry >= MAX_RETRIES - 1) {
          this.stateManager.failTask(task.id, error.message);
          return { status: 'FAILED', taskId: task.id, error };
        }
        await this.handleRetry(error, retry);  // 3-Strike Protocol
      }
    }
  }
}
```

#### 6.3.4 相比原始方案的改进

| 原始方案 | Agent Core 改进 | 理由 |
|---------|----------------|------|
| Step 1: Initialize | 保留 + 增加环境健康检查 | 确保运行环境真正就绪 |
| Step 2: Select Task | 保留 + DAG 依赖解析 | 支持复杂依赖关系 |
| — | **新增 ANALYZE 阶段** | 先充分理解再动手 |
| — | **新增 PLAN 阶段** | 制定方案避免盲目开工 |
| Step 3: Implement | 保留 + 子步骤追踪 | 细粒度进度跟踪 |
| Step 4: Test | 升级为 5 级验证门控 | L1→L5 渐进式验证 |
| Step 5: Update Progress | 保留 + 结构化模板 | 便于解析和回溯 |
| Step 6: Commit | 保留 + 原子性保证 | 预提交检查清单 |
| — | **新增 3-Strike 重试协议** | 系统化错误恢复 |

### 6.4 Context Engine（上下文引擎）

#### 6.4.1 职责

为每一轮 LLM 调用组装最优的上下文窗口内容。在有限的 token 预算内，提供最有价值的信息。

#### 6.4.2 上下文注入源

| 注入源 | 类型 | 预算占比 | 更新频率 |
|--------|------|---------|---------|
| Constitution（静态规则） | Static Zone | ~5% | 很少变化 |
| Tool Schemas（工具定义） | Static Zone | ~5% | 工具集变化时 |
| Project README / Architecture | Semi-Static | ~5% | 项目级 |
| Memory（长期记忆） | Semi-Static | ~5% | 跨会话 |
| Session Log Summary（进度日志） | Semi-Static | ~3% | 每次任务后 |
| Current Task Spec（当前任务） | Dynamic Zone | ~5% | 每个任务 |
| Related Source Files（相关代码） | Dynamic Zone | ~30% | 按需注入 |
| Conversation History（对话历史） | Dynamic Zone | ~25% | 实时 |
| Tool Results（工具输出） | Dynamic Zone | ~10% | 实时 |
| Error Outputs（错误日志） | Dynamic Zone | ~5% | 按需 |
| Safety Margin（安全余量） | — | ~2% | — |

#### 6.4.3 源代码智能注入

不是加载整个代码库，而是**智能选择最相关的 3-5 个源文件**：

```typescript
async function selectRelevantFiles(task: Task, projectContext: ProjectContext): Promise<FileInfo[]> {
  // 1. 基于 task.description 中的关键词搜索
  const keywordMatches = await grepSearch(task.description);

  // 2. 基于 task.dependsOn 关联的前置任务涉及的文件
  const dependencyFiles = getFilesFromPreviousTasks(task.dependsOn);

  // 3. 基于项目架构推断的关键文件
  const archFiles = inferArchitecturalFiles(task.category);

  // 4. 合并、去重、按相关性排序
  return mergeAndRank(keywordMatches, dependencyFiles, archFiles)
    .slice(0, 5);  // 最多注入 5 个文件
}
```

### 6.5 Tool Pipeline（工具运行时管道）

#### 6.5.1 职责

管理工具的注册、调度、执行和结果收集。Tool Pipeline 是 Agent 与外部世界交互的唯一通道。

#### 6.5.2 统一工具接口

```typescript
interface Tool<TInput = any, TOutput = any> {
  name: string;
  description: string;
  inputSchema: z.ZodSchema<TInput>;
  outputSchema?: z.ZodSchema<TOutput>;
  call(input: TInput, context: ToolContext): Promise<TOutput>;
  isReadOnly?(input: TInput): boolean;
  checkPermissions?(input: TInput, context: ToolContext): Promise<PermissionDecision>;
}
```

#### 6.5.3 内置工具清单

| 类别 | 工具 | 功能 | 只读 |
|------|------|------|------|
| **文件** | FileRead | 读取文件（多格式支持） | 是 |
| | FileWrite | 创建/覆写文件 | 否 |
| | FileEdit | 精确字符串替换 | 否 |
| | Glob | 文件模式搜索 | 是 |
| **Shell** | Bash | 命令执行 | 取决于命令 |
| **搜索** | Grep | 内容正则搜索 | 是 |
| | WebSearch | 网络搜索 | 是 |
| | WebFetch | URL 内容获取 | 是 |
| **交互** | AskUser | 向用户提问 | 是 |
| **Agent** | SubAgent | 委派子任务 | 是 |
| **MCP** | * | MCP 服务器动态工具 | 取决于定义 |

#### 6.5.4 FileEdit 的关键设计：精确字符串替换

选择精确字符串替换而非行号编辑，原因有三：
1. LLM 生成的行号经常出错
2. 匹配唯一性校验防止误改（隐式原子性）
3. 读后写检查防止覆盖冲突（乐观锁）

### 6.6 Verification System（验证系统）

#### 6.6.1 五级验证门控

| 级别 | 名称 | 内容 | 触发条件 | 必须? |
|------|------|------|---------|------|
| L1 | 基线验证 | lint + build | 所有任务 | 是 |
| L2 | 类型检查 | tsc --noEmit | TypeScript 项目 | 推荐 |
| L3 | 浏览器测试 | Playwright 截图对比 | 涉及 UI 变更 | 是（此时） |
| L4 | 对抗性探针 | 边界值、并发、错误路径 | 核心功能 | 可选 |
| L5 | 回归验证 | 确认旧功能未被破坏 | 大型变更 | 可选 |

#### 6.6.2 验证结论

```typescript
type VerificationVerdict = 'PASS' | 'FAIL' | 'PARTIAL' | 'BLOCKED';

interface VerificationResult {
  verdict: VerificationVerdict;
  level: number;
  tests: TestCaseResult[];
  evidence: string[];    // 命令输出作为证据
  duration: number;      // 验证耗时
}
```

**关键原则：验证者的工作是打破信心，而不是强化信心。** PARTIAL 仅用于环境限制（如需要真实账号），不用于 Agent 的不确定性。

### 6.7 Prompt Assembly（提示词组装架构）

#### 6.7.1 组装流程

```
┌─────────────────────────────────────────────────────────┐
│                  Prompt Assembly Pipeline                 │
│                                                          │
│  1. 加载 Constitution System Prompt（缓存友好）          │
│     ↓                                                    │
│  2. 注入当前阶段的 Phase Instructions                    │
│     ↓                                                    │
│  3. 注入 Task Spec（当前任务规范）                       │
│     ↓                                                    │
│  4. 注入 Context Engine 组装的上下文                     │
│     ↓                                                    │
│  5. 注入 Conversation History（对话历史）                │
│     ↓                                                    │
│  6. 注入 Tool Call Results（工具结果）                   │
│     ↓                                                    │
│  7. Token 预算检查 → 如超出则触发 Compact                │
│     ↓                                                    │
│  8. 输出最终 Prompt（分三层：Static / Semi / Dynamic）   │
└─────────────────────────────────────────────────────────┘
```

#### 6.7.2 System Prompt 模板

```
你是 {constitution.name}，角色是 {constitution.role}。

## 工作流
你当前处于 {phase} 阶段。
{phase_instructions}

## 规则
{applicable_rules}

## 当前任务
### Task {task.id}: {task.title}
{task.description}

### 执行步骤
{task.steps.map((s, i) => `${i+1}. ${s}`).join('\n')}

### 验收标准
完成后必须通过以下验证:
{verification_levels}

## 项目上下文
{project_context}

## 进度信息
{session_log_summary}
```

### 6.8 Permission System（权限系统）

#### 6.8.1 三层权限模型

```
Layer 1: 输入验证
  - 路径规范化、Schema 校验、注入防护、敏感信息过滤

Layer 2: 规则引擎
  - Allow/Deny/Ask 规则匹配
  - 基于 Constitution 的权限映射
  - AI Classifier 自动审批（auto 模式）

Layer 3: 沙箱隔离
  - 文件系统访问控制（允许/拒绝路径列表）
  - 网络过滤（白名单域名）
  - 进程隔离（tmux / namespace）
```

#### 6.8.2 规则示例

```jsonc
[
  { "tool": "Read", "path": "./**", "behavior": "allow" },
  { "tool": "*", "path": "~/.ssh/**", "behavior": "deny" },
  { "tool": "Bash", "command": "(rm|sudo).*-rf", "behavior": "ask" },
  { "tool": "Write", "path": "**/.env*", "behavior": "ask" }
]
```

### 6.9 Hook Bus（事件总线）

#### 6.9.1 设计

Hook Bus 是 OpenBoss 的事件收集和分发中枢。所有 Agent 行为（工具调用、状态变更、工作流推进）都通过 Hook Bus 产生事件。事件同时通过两个通道输出：

| 通道 | 格式 | 用途 | 可靠性 |
|------|------|------|--------|
| HTTP POST | JSON | 实时事件上报到后端 | 实时性好 |
| JSONL File | JSON Lines | 本地持久化日志 | 可靠性好 |

#### 6.9.2 Hook 类型

| Hook | 触发时机 | 数据内容 |
|------|---------|---------|
| PreToolUse | 工具调用前 | 工具名、输入参数 |
| PostToolUse | 工具调用后 | 工具名、输入、输出、耗时 |
| Notification | Agent 通知 | 通知内容、类型 |
| Stop | Agent 停止 | 停止原因、最终状态 |

### 6.10 Lifecycle Manager（生命周期管理器）

#### 6.10.1 Agent 生命周期

```
Created → Configured → Starting → Working → NeedsInput → Stopping → Terminated
                           ↑                                        │
                           └────────────────────────────────────────┘
                                        (重启)
```

#### 6.10.2 Ephemeral Agent 模式

Agent 是**无状态的、一次性的、幂等的**：
- 每次启动都是全新的（无历史上下文）
- 通过文件系统恢复状态（读 task-manifest.json + session-log.md）
- 执行完一个任务后退出（不驻留）
- 外部调度器决定是否启动下一个 Agent

这使得 Agent 天然支持：重试、并行、替换后端模型。

---

## 7. Scheduler 编排引擎（Phase 2）

> Phase 2 在 Agent Core 稳定后启动，实现多 Agent 编排能力。

### 7.1 任务调度器

任务调度器基于 DAG（有向无环图）管理任务依赖和执行顺序：

```typescript
class TaskScheduler {
  // 从 PRD/Issue 自动生成任务队列
  async decomposeRequirements(requirementDoc: string): Promise<Task[]>;

  // 基于 DAG 拓扑排序调度任务
  schedule(manifest: TaskManifest): Task[];

  // Feedback Loop 自动执行
  async runFeedbackLoop(): Promise<void>;
}
```

### 7.2 多 Agent 协作（Swarm）

```
┌─────────────────────────────────────────────┐
│            Swarm 多 Agent 架构               │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  Boss Agent（主控 Agent）              │   │
│  │  - 接收用户指令                        │   │
│  │  - 分解任务                            │   │
│  │  - 分配给子 Agent                      │   │
│  │  - 收集结果并汇总                      │   │
│  └──────────┬───────────────────────────┘   │
│             │                               │
│    ┌────────┼────────┬────────┐            │
│    ▼        ▼        ▼        ▼            │
│  ┌──────┐┌──────┐┌──────┐┌──────┐        │
│  │Coder ││Tester││Writer││Design│        │
│  │      ││      ││      ││er    │        │
│  └──┬───┘└──┬───┘└──┬───┘└──┬───┘        │
│     │       │       │       │              │
│     ▼       ▼       ▼       ▼              │
│  ┌─────────────────────────────────────┐  │
│  │     Hermes Bus（信使总线）            │  │
│  │  消息路由 / 协议转换 / 冲突调解       │  │
│  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

### 7.3 并发控制与隔离

| 隔离策略 | 层级 | 实现方式 |
|---------|------|---------|
| **上下文隔离** | Agent 间 | 每个 Agent 独立对话上下文 |
| **文件系统隔离** | 工作目录 | 可配置独立工作目录 |
| **Git 分支隔离** | 代码修改 | 每个任务在独立分支执行 |
| **进程隔离** | 运行环境 | 独立 tmux 会话 |
| **资源锁定** | 文件/目录 | 文件锁 + 乐观并发控制 |

### 7.4 tmux 会话管理

每个 Agent 运行在独立的 tmux 会话中：

```typescript
class TmuxManager {
  // 创建会话
  createSession(agentId: string, taskId: number): TmuxSession;

  // 发送命令到会话
  sendCommand(sessionId: string, command: string): void;

  // 捕获会话输出
  captureOutput(sessionId: string): string;

  // 会话状态查询
  getSessionStatus(sessionId: string): SessionStatus;

  // 清理过期会话
  cleanupStaleSessions(): void;
}
```

---

## 8. 一人公司场景设计（Phase 3）

> Phase 3 是终极愿景，在 Agent Core + Scheduler 稳定后逐步实现。

### 8.1 产品研发全链路自动化

```
PRD 文档
    │
    ▼ Planner Agent
任务分解（task-manifest.json）
    │
    ├─→ Coder Agent（功能实现）
    ├─→ Designer Agent（UI/UX 实现）
    ├─→ Tester Agent（自动化测试）
    │
    ▼ Reviewer Agent
代码审查
    │
    ▼
自动化部署
    │
    ▼
文档更新（Writer Agent）
```

### 8.2 市场营销 Agent

| 能力 | 描述 | 输出 |
|------|------|------|
| 竞品分析 | 自动搜索和对比竞品功能 | 竞品对比报告 |
| 内容生成 | 根据产品特性生成营销文案 | 博客文章、社交媒体帖子 |
| SEO 优化 | 分析关键词、生成 meta 信息 | SEO 报告 |
| 用户调研 | 分析用户反馈和评价 | 用户洞察报告 |

### 8.3 运营客服 Agent

| 能力 | 描述 | 输出 |
|------|------|------|
| 工单处理 | 自动分类和回复用户工单 | 工单回复草稿 |
| FAQ 维护 | 基于历史工单自动更新 FAQ | FAQ 文档 |
| 用户引导 | 引导新用户上手产品 | 引导教程 |
| 数据分析 | 分析运营数据（DAU/留存/转化） | 运营周报 |

### 8.4 财务法务 Agent

| 能力 | 描述 | 输出 |
|------|------|------|
| 发票管理 | 自动处理和归档发票 | 财务报表 |
| 合同审查 | AI 辅助审查合同条款 | 风险提示 |
| 税务提醒 | 自动计算和提醒税务事项 | 税务日历 |
| 预算跟踪 | 跟踪项目成本和预算 | 预算报告 |

### 8.5 知识管理 Agent

| 能力 | 描述 | 输出 |
|------|------|------|
| 文档管理 | 自动组织和索引项目文档 | 知识库 |
| 会议纪要 | 从会议记录中提取决策和行动项 | 决策记录 |
| 技术博客 | 将项目经验整理为技术文章 | 博客草稿 |
| 决策日志 | ADR（架构决策记录）维护 | ADR 文档 |

---

## 9. 数据模型与文件协议

### 9.1 文件系统布局

```
.openboss/
├── constitution.md          # Agent 行为宪法（Constitution Spec）
├── task-manifest.json       # 任务状态源（Task Spec）
├── session-log.md           # 会话日志（追加式）
├── config.json              # 项目配置
├── memory/
│   ├── MEMORY.md            # 核心记忆文件
│   ├── YYYY-MM-DD.md        # 按日期的工作日志
│   ├── decisions/           # ADR 架构决策记录
│   └── lessons/             # 经验教训库
├── artifacts/               # 产出物归档
│   ├── plans/               # 实现方案存档
│   ├── screenshots/         # 截图对比
│   └── reports/             # 验证报告
├── logs/
│   ├── {session-id}.jsonl   # 事件日志（OpenClaw 格式）
│   └── audit.log            # 审计日志
└── hooks/
    ├── pre-tool-use.sh      # PreToolUse Hook 脚本
    ├── post-tool-use.sh     # PostToolUse Hook 脚本
    ├── notification.sh      # Notification Hook 脚本
    └── stop.sh              # Stop Hook 脚本
```

### 9.2 constitution.md 协议

见第 6.1.2 节的完整结构定义。

### 9.3 task-manifest.json 协议

见第 6.2.2 节的完整数据结构定义。

### 9.4 session-log.md 协议

```markdown
---
session: {session_id}
date: YYYY-MM-DD
agent: {agent_id}
tasks_completed: N
tasks_failed: N
---

## Task {id}: {title}
- **Status**: completed | failed | blocked
- **Duration**: {start_time} → {end_time} ({elapsed})
- **Retries**: {retry_count}
- **Changes**: {file_list}

### What was done
{具体完成的工作描述}

### Testing
- **Command**: {test_command}
- **Output**: {test_output_summary}
- **Verdict**: PASS | FAIL

### Notes
{给未来 Agent 的备注和经验教训}
```

### 9.5 memory/ 协议

```
memory/MEMORY.md           # 格式: Markdown，按主题分 section
memory/YYYY-MM-DD.md       # 格式: 日期标题 + 当日工作总结 + 关键发现
memory/decisions/arch-NNN.md  # ADR 格式: Context / Decision / Consequences
memory/lessons/*.md        # 格式: 问题 / 根因 / 解决方案 / 预防措施
```

---

## 10. Agent 思维范式（Thinking Protocol）

### 10.1 单轮思考框架

Agent 在每次 LLM 调用前应遵循以下思考框架：

```
1. 我现在处于工作流的哪个阶段？
   → 检查 Constitution 中的 Workflow Phase

2. 当前任务要求我做什么？
   → 读取 task-manifest.json 中的 steps

3. 我需要什么信息才能开始？
   → Context Engine 组装相关上下文

4. 有哪些约束需要遵守？
   → 查询 Constitution Rules

5. 上一个任务留下了什么信息？
   → 读取 session-log.md 的最近记录

6. 完成后如何验证？
   → 查询 Verification Levels

7. 如果失败了怎么办？
   → 遵循 3-Strike Error Protocol
```

### 10.2 决策树

```
收到任务
  │
  ├─ 环境是否就绪？
  │   ├─ 否 → 初始化环境 → BLOCKED if 无法解决
  │   └─ 是 ↓
  │
  ├─ 依赖是否满足？
  │   ├─ 否 → 等待依赖完成
  │   └─ 是 ↓
  │
  ├─ 任务是否理解清楚？
  │   ├─ 否 → 分析需求 → 向用户确认
  │   └─ 是 ↓
  │
  ├─ 是否需要规划？
  │   ├─ 是 → 制定实现方案
  │   └─ 否 → 直接实现
  │
  ├─ 实现完成？
  │   ├─ 否 → 继续 + 记录进度
  │   └─ 是 ↓
  │
  ├─ 验证通过？
  │   ├─ PASS → Record → Commit → 下一个任务
  │   ├─ FAIL → 修复 → 重新验证（≤3次）
  │   └─ BLOCKED → 记录原因 → STOP
  │
  └─ 3次都失败？
      └─ 标记 FAILED → git reset → 通知 Boss
```

### 10.3 3-Strike Error Protocol

当任务执行失败时，Agent 遵循三级错误恢复协议：

| Strike | 行动 | 策略 |
|--------|------|------|
| **Strike 1** | 分析错误 | 阅读错误日志，定位根因，针对性修复 |
| **Strike 2** | 换一个角度 | 如果同一修复方案再次失败，尝试不同的方法 |
| **Strike 3** | 最小化修复 | 尝试最小可行修复，即使不完美也比完全失败好 |
| **Strike Out** | 放弃并报告 | git reset，标记任务为 failed，输出结构化报告 |

---

## 11. 技术选型

### 11.1 Agent Core（Phase 1）

| 技术维度 | 推荐方案 | 理由 |
|---------|---------|------|
| **运行时** | Node.js / TypeScript | 与 tmux/CLI 集成最方便，生态丰富 |
| **LLM SDK** | 自建 Adapter（支持 Claude/GPT/GLM） | 不绑定特定厂商 |
| **文件解析** | gray-matter (frontmatter) + zod (schema) | Constitution 和 Task 的解析验证 |
| **进程管理** | node-pty + tmux | 完整 PTY 支持，适合 CLI 集成 |
| **文件锁** | proper-lockfile | 跨平台文件锁 |
| **模板引擎** | Handlebars / Nunjucks | Prompt 模板和日志模板 |
| **测试** | Vitest | 快速、TypeScript 原生支持 |

### 11.2 Scheduler + UI（Phase 2）

| 技术维度 | 推荐方案 | 理由 |
|---------|---------|------|
| **后端框架** | Fastify | 高性能，与 Node.js 生态无缝 |
| **前端框架** | React + Vite | 生态成熟，组件库丰富 |
| **UI 组件库** | Shadcn/UI | 深色主题支持好，高度可定制 |
| **实时通信** | Socket.IO | 自动重连、房间机制 |
| **数据库** | SQLite (v1) → PostgreSQL (v2) | v1 零配置，v2 多用户 |
| **状态管理** | Zustand | 轻量简洁 |

---

## 12. 实施路线图

### Phase 1: Agent Core 雏形（第 1-8 周）

> **目标：实现一个能自主完成单个编码任务的 Agent，具备完整的 PDCA 循环。**

| 周 | 里程碑 | 交付物 |
|----|--------|--------|
| 1-2 | **基础框架** | 项目脚手架、Constitution 解析器、State Manager |
| 3-4 | **核心循环** | Workflow Engine（ANALYZE→PLAN→IMPLEMENT→VERIFY→RECORD→COMMIT） |
| 5-6 | **验证与安全** | Verification System（L1-L3）、Permission System、Tool Pipeline |
| 7-8 | **打磨与测试** | Context Engine、Prompt Assembly、Hook Bus、端到端测试 |

**Phase 1 验收标准：**
- 能从 task-manifest.json 读取任务并自动执行
- 每个任务遵循完整的 PDCA 循环
- 所有修改通过 L1 验证（lint + build）
- 涉及 UI 的修改通过 L3 验证（浏览器截图）
- 验证失败时遵循 3-Strike Protocol
- 每个任务完成后执行 Atomic Commit
- 在 5 个以上的真实任务中验证可靠性

### Phase 2: Scheduler 编排（第 9-16 周）

> **目标：实现多 Agent 编排，支持从 PRD 自动分解任务并调度执行。**

| 周 | 里程碑 | 交付物 |
|----|--------|--------|
| 9-10 | **Scheduler 核心** | Task Scheduler（PRD→任务分解）、Feedback Loop |
| 11-12 | **多 Agent** | Swarm 架构、Hermes Bus、tmux 管理 |
| 13-14 | **并发控制** | 资源锁定、Git 分支隔离、冲突检测 |
| 15-16 | **可视化 UI** | Web 前端（任务看板、实时日志、Agent 状态仪表盘） |

### Phase 3: 一人公司场景（第 17-30 周）

> **目标：扩展 Agent 类型，覆盖非编码场景，实现一人公司全栈自动化。**

| 周 | 里程碑 | 交付物 |
|----|--------|--------|
| 17-20 | **场景 Agent** | Designer、Tester、Writer、Marketer Agent |
| 21-24 | **知识管理** | Memory 系统增强、决策日志、经验库 |
| 25-27 | **运维自动化** | 部署 Agent、监控 Agent、客服 Agent |
| 28-30 | **开放生态** | OpenClaw 协议完善、插件系统、社区文档 |

---

## 13. 风险与应对

### 13.1 技术风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| LLM API 不稳定或限流 | 高 | 高 | Adapter Pattern + 降级到本地模型 |
| Context Window 不够用 | 中 | 高 | Context Engine 的压缩和预算控制 |
| Agent 产生不可控行为 | 中 | 严重 | Constitution 强制约束 + Permission System |
| 文件锁竞争导致死锁 | 低 | 中 | 超时自动释放 + 锁排序 + 死锁检测 |
| tmux 会话泄漏 | 中 | 低 | 定期清理 stale session + Lifecycle Manager |

### 13.2 架构风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| 过度设计导致 Phase 1 无法交付 | 中 | 高 | 严格遵循渐进式路线，Phase 1 只做核心 |
| 四份已有资产的设计冲突 | 低 | 中 | 本章已进行架构级整合，消除冲突 |
| LLM 厂商绑定 | 中 | 中 | LLM Adapter 抽象层，支持多厂商切换 |

### 13.3 用户体验风险

| 风险 | 概率 | 影响 | 应对策略 |
|------|------|------|---------|
| 配置过于复杂 | 中 | 中 | 提供合理默认值 + 交互式初始化向导 |
| 错误信息不友好 | 高 | 中 | 结构化错误报告 + 修复建议 |
| 学习曲线陡峭 | 中 | 中 | 详细的文档 + 示例项目 + 视频教程 |

---

## 14. 附录 A：实战验证分析（Spring FES Video 项目）

> 本章基于用户提供的 7 个实战项目文件，深度分析一个已被 31 个任务验证过的 Agent 运行系统。这些文件是 OpenBoss Agent Core 的**活体标本**——不是理论设计，而是经过真实环境锤炼的生产级模式。

### 14.1 项目概况

| 维度 | 数据 |
|------|------|
| 项目名称 | Spring FES Video（故事转视频生成平台） |
| 技术栈 | Next.js 14 + TypeScript + Tailwind CSS + Supabase |
| 外部 AI 服务 | 智谱 AI GLM-4.7（分镜生成）、火山引擎 Seedream 4.5（图片）、Seedance 1.5 Pro（视频） |
| Agent 工具 | Claude Code + Playwright MCP（唯一安装的 MCP） |
| 任务总数 | 31 个任务 |
| 执行时间 | 约 10 小时 |
| 完成率 | 100%（全部 31 个任务 passes: true） |
| AI 生成率 | 100% 代码和 prompt 均由 AI 生成 |
| 人工介入 | 仅 2 个 git commit（markdown 文件修改，内容仍为 AI 生成） |

### 14.2 实战文件的角色定位

```
┌──────────────────────┬─────────────────────────┬────────────────────────────┐
│ 文件                 │ OpenBoss 中的角色        │ 实战验证状态               │
├──────────────────────┼─────────────────────────┼────────────────────────────┤
│ CLAUDE.md           │ Constitution（行为宪法） │ 31 任务全通过              │
│ task.json           │ Task Manifest（状态源）  │ 31 任务全通过              │
│ progress.txt        │ Session Log（会话日志）  │ 31 任务全通过              │
│ init.sh             │ Lifecycle Init           │ 原型可用                    │
│ run-automation.sh   │ Automation Loop（调度器）│ 原型可用                    │
│ architecture.md     │ Domain KB（领域知识库） │ 31 任务全通过              │
│ README.md           │ Project Context          │ 31 任务全通过              │
└──────────────────────┴─────────────────────────┴────────────────────────────┘
```

### 14.3 实战 vs PRD 设计的对比分析

#### 14.3.1 task.json：简单即是正义

**实战发现**：实际的 task.json 结构比 PRD 设计的简单得多。没有 `status`、`dependsOn`、`priority`、`category`、`attempts` 等字段。只有 `id`、`title`、`description`、`steps[]`、`passes`（boolean）五个字段。

```json
{
  "project": "Spring FES Video",
  "description": "故事转视频生成平台",
  "tasks": [
    {
      "id": 1,
      "title": "项目基础配置",
      "description": "配置项目的基础设置和依赖",
      "steps": [
        "安装 Supabase 客户端: @supabase/supabase-js, @supabase/ssr",
        "安装 UI 组件库: clsx, tailwind-merge",
        "创建 .env.local 模板文件（包含所有必需的环境变量）",
        "创建 lib/utils.ts 工具函数文件"
      ],
      "passes": true
    }
  ]
}
```

**关键洞察**：

| 设计维度 | PRD 设计 | 实战做法 | 结论 |
|---------|---------|---------|------|
| 任务状态 | 7 种状态枚举 | 仅 `passes: boolean` | 简单布尔值足够 |
| 依赖管理 | `dependsOn[]` + DAG | 无显式依赖，靠 ID 顺序 | 小项目 ID 顺序足够 |
| 优先级 | P0-P3 四级 | 无（ID 顺序即优先级） | 小项目不需要 |
| 重试次数 | `attempts` 字段 | Agent 自己重试 | 不需要显式跟踪 |
| 时间戳 | 多个时间字段 | 无（靠 git 历史） | git 历史足够 |
| 分配人 | `assignee` 字段 | 无（单人 Agent） | 单 Agent 不需要 |

**OpenBoss 采取的策略**：OpenBoss Agent Core 保留完整的 Task 数据结构（支持 Phase 2 多 Agent 编排场景），但在 Phase 1 的实际实现中，**最小可用版本**只需 `id`、`title`、`description`、`steps[]`、`passes` 五个字段。其他字段作为可选扩展，在需要时才启用。

#### 14.3.2 CLAUDE.md：宪法就在身边

**实战发现**：CLAUDE.md 就是一个生产级的 Constitution 文件。它不是一个抽象的设计文档，而是 Claude Code 在每次会话开始时**真正读取和遵循的指令文件**。

**实战 Constitution 的核心结构**：

```markdown
# 项目指令

## Project Context（1 句话项目描述）

## MANDATORY: Agent Workflow（强制工作流 - 6 步）
### Step 1: Initialize Environment（./init.sh）
### Step 2: Select Next Task（读 task.json，选 passes: false）
### Step 3: Implement the Task（按 steps 实现）
### Step 4: Test Thoroughly（强制测试要求）
### Step 5: Update Progress（写 progress.txt）
### Step 6: Commit Changes（所有更改在同一 commit）

## 阻塞处理（Blocking Issues）
### 需要停止任务的情况
### 阻塞时的正确操作（DO / DON'T）
### 阻塞信息格式（标准化模板）

## Project Structure（项目目录）
## Commands（常用命令）
## Coding Conventions（编码规范）
## Key Rules（核心规则 7 条）
```

**与 PRD Constitution 对比**：

| PRD 设计要素 | 实战对应 | 匹配度 |
|------------|---------|--------|
| Identity（身份定义） | Project Context + Coding Conventions | 完全匹配 |
| Workflow（6 步工作流） | MANDATORY: Agent Workflow | 完全匹配 |
| Rules（行为规则集） | Key Rules（7 条）+ 阻塞处理 | 完全匹配 |
| Blocking Conditions（阻塞条件） | 阻塞处理章节 | 完全匹配 |
| Permissions（权限映射） | 无（使用了 --dangerously-skip-permissions）| Phase 2 才需要 |
| frontmatter（版本管理） | 无 | 实战中不需要 |

**关键发现——测试分级策略**：

CLAUDE.md 定义了务实的测试分级策略：
- **大幅度修改**（新建页面、重写组件、修改核心交互）→ **必须浏览器测试**（MCP Playwright）
- **小幅度修改**（修复 bug、调整样式、添加辅助函数）→ 可以只用 lint/build
- **所有修改** → 必须通过 `npm run lint` + `npm run build`

这比 PRD 设计的 L1-L5 五级验证更务实。OpenBoss 应该在 Phase 1 中采用这种分级策略，Phase 2 再扩展为完整的五级体系。

#### 14.3.3 progress.txt：追加日志的真实面貌

**实战发现**：progress.txt 是一个**纯追加的日志文件**，新条目添加在文件顶部（最新在前）。每个条目包含四个标准化部分：

```markdown
## 2026-02-10 - Task 31: 最终测试和优化

### What was done:
- 运行 npm run lint 检查代码规范 - 通过
- 运行 npm run build 确保构建成功 - 通过
- 测试完整用户流程：
  - ✅ 首页显示正确
  - ✅ 项目列表页显示正确
  ...

### Testing:
- ✅ npm run lint 通过
- ✅ npm run build 成功
- ✅ 所有页面在浏览器中正常显示

### Notes:
- 所有 31 个任务已完成
- 需要配置真实的 API 密钥才能测试 AI 生成功能
```

**与 PRD session-log.md 对比**：

| PRD 设计 | 实战做法 | 结论 |
|---------|---------|------|
| frontmatter（session_id, agent_id） | 无 | 简单场景不需要 |
| 结构化日期（YYYY-MM-DD） | 有（完全一致） | 实战验证 |
| What was done / Testing / Notes | 有（完全一致） | 实战验证 |
| Bug Fix 也记入日志 | 是（无 task_id，以日期 + Bug 描述为标题） | 实战模式 |
| 新条目在顶部 | 是（最新在前） | 比 PRD 设计的底部追加更好 |

#### 14.3.4 run-automation.sh：外部循环的精确实现

**实战发现**：run-automation.sh 是 Ephemeral Agent Pattern 的**教科书级实现**。它完美展示了"Agent 是无状态的 worker，循环逻辑在外部"这一核心理念。

```bash
# 外部循环的核心逻辑
for run in 1..N:
  1. 检查 task.json 中是否还有 passes: false
  2. 用 grep -c '"passes": false' task.json 计数
  3. 如果为 0 → 全部完成，退出
  4. 启动 claude -p --dangerously-skip-permissions
  5. 注入标准 prompt（"请按 CLAUDE.md 工作流执行下一个任务"）
 6. 等待 Claude Code 完成
  7. 检查 task.json 中 passes: false 的数量变化
  8. 记录日志
  9. 等待 2 秒
  10. 继续下一轮
```

**关键技术细节**：

| 细节 | 实战做法 | OpenBoss 采取 |
|------|---------|-------------|
| Claude Code 启动方式 | `claude -p`（非交互模式） | Phase 1 保持 CLI 模式 |
| 权限模式 | `--dangerously-skip-permissions` | Phase 1 用此模式快速验证，Phase 2 加 Permission System |
| 允许的工具 | `--allowed-tools "Bash Edit Read Write Glob Grep Task WebSearch WebFetch mcp__playwright__*"` | Phase 1 预配置允许的工具集 |
| Prompt 注入方式 | 临时文件 + stdin 重定向 | OpenBoss Prompt Assembly 生成的 prompt |
| 任务完成检测 | `grep -c '"passes": false' task.json` | State Manager.getNextTask() |
| 循环间延迟 | 2 秒 | 可配置 |
| 日志记录 | 每轮单独 log + 汇总 log | Hook Bus + JSONL 日志 |

#### 14.3.5 init.sh：最小化的环境初始化

**实战发现**：init.sh 非常简单——安装依赖、启动 dev server、等待就绪。整个脚本不到 40 行。这验证了"Phase 1 保持简单"的策略是正确的。

```bash
set -e
cd hello-nextjs && npm install && cd ..
cd hello-nextjs
npm run dev &
SERVER_PID=$!
cd ..
sleep 3
```

#### 14.3.6 architecture.md：领域知识的标准格式

**实战发现**：architecture.md 是一个精心编写的领域知识文档，包含：
- Mermaid 系统架构图
- Mermaid 核心业务流程图
- Mermaid 数据模型 ER 图
- 页面结构图
- 完整的 API 设计表格
- 外部 API 集成文档（含请求示例）
- 环境变量说明

这是 Agent 在 IMPLEMENT 阶段**最重要的上下文来源之一**。OpenBoss 的 Context Engine 应该自动检测并注入 architecture.md 的相关章节。

### 14.4 实战验证的关键结论

#### 结论 1：最小可行 Constitution 就够用

CLAUDE.md 用约 200 行 Markdown 就实现了完整的 Agent 行为控制。PRD 设计的 Constitution 结构（含 frontmatter、结构化规则、权限映射等）虽然更完善，但 Phase 1 的最小实现应该贴近实战的简洁性。

**Phase 1 Constitution 最小模板**：

```markdown
# {Project Name} - Project Instructions

## Project Context
{一句话项目描述}

## MANDATORY: Agent Workflow
### Step 1: Initialize Environment → ./init.sh
### Step 2: Select Next Task → 读 task.json
### Step 3: Implement the Task → 按 steps 实现
### Step 4: Test Thoroughly → 分级测试策略
### Step 5: Update Progress → 写 progress.txt
### Step 6: Commit Changes → 单一原子提交

## 阻塞处理
{DO / DON'T + 标准化格式}

## Key Rules
{5-10 条核心规则}
```

#### 结论 2：task.json 五字段足够

Phase 1 只需要 `{id, title, description, steps[], passes}` 五个字段。其他字段（依赖、优先级、状态等）在 Phase 2 多 Agent 编排时才需要启用。

#### 结论 3：外部循环比内部循环更可靠

run-automation.sh 证明将 PDCA 循环放在 Agent 外部（bash 脚本）比放在 Agent 内部更可靠。OpenBoss 应该在 Phase 1 就实现外部循环调度器，而不是期望 Agent 自己管理循环。

#### 结论 4：分级测试比多级验证更务实

实战中不需要 L1-L5 五级验证体系。"大改用浏览器、小改用 lint/build、所有改必过 build"这个简单规则就够了。OpenBoss 的 Verification System 在 Phase 1 应该采用这个务实策略。

#### 结论 5：Bug Fix 不应该混入 task.json

实战中 Bug Fix 是在 progress.txt 中记录的，不在 task.json 中。task.json 只包含**计划内的任务**，Bug Fix 是**计划外的修正**。OpenBoss 应该支持这种双轨模式：task.json 管理计划任务，progress.txt 兼顾计划任务记录和 Bug Fix 记录。

#### 结论 6：Playwright MCP 是唯一必需的外部工具

实战中只安装了 Playwright MCP，其他所有能力（文件操作、搜索、命令执行）都是 Claude Code 内置的。OpenBoss Phase 1 的工具集应该以 Claude Code 内置工具为基础，Playwright MCP 为唯一外部依赖。

### 14.5 从实战中提炼的 Phase 1 最小实现清单

基于实战分析，OpenBoss Phase 1 的**最小可行实现**需要以下组件：

| 组件 | 对应实战文件 | 最小实现 |
|------|------------|---------|
| Constitution Parser | CLAUDE.md | 读取 Markdown 文件，提取 Workflow Steps + Rules + Blocking Conditions |
| State Manager | task.json | 读写 JSON，查询下一个 `passes: false` 的任务 |
| Progress Logger | progress.txt | 追加日志条目到文件顶部 |
| Init Runner | init.sh | 执行初始化脚本，检查环境就绪 |
| Automation Loop | run-automation.sh | 外部循环：读任务 → 启动 Agent → 检查结果 → 重复 |
| Context Injector | architecture.md | 检测并注入领域知识文件的相关章节 |
| Verification Gate | CLAUDE.md Step 4 | 分级测试：大改→浏览器，小改→lint/build |
| Commit Protocol | CLAUDE.md Step 6 | 单一原子提交：代码 + progress.txt + task.json |

---

## 15. 附录 B：与现有资产的关系映射

### 15.1 概念映射表

| OpenBoss 概念 | AI-Coding-Agent-PRD | AgentCommander PRD | OpenBoss Agent Core PRD | harness.md |
|--------------|--------------------|--------------------|------------------------|------------|
| Constitution Engine | System Prompt + Permission Rules | Agent 定义 (role_id, system_prompt) | Constitution Engine | — |
| State Manager | — | 任务管理模块 (task.json) | State Manager | task.json |
| Workflow Engine | Agentic Loop | Feedback Loop 自动执行 | Workflow Engine (PDCA) | run-automation.sh |
| Context Engine | 上下文管理系统 | 上下文管理 + process.txt 注入 | Context Engine | — |
| Tool Pipeline | 工具架构 (统一接口) | — | Tool Pipeline | — |
| Verification System | Plan Mode (只读验证) | 自测试协议 (三层) | Verification System | TDD 约束 |
| Permission System | 权限与安全系统 (四层) | Hook 注入 + 权限 | Permission System | — |
| Hook Bus | — | JSONL + HTTP POST 双通道 | Hook Bus | — |
| Prompt Assembly | 上下文组装策略 | — | Prompt Assembly | — |
| Scheduler | — | Task Scheduler (DAG) | — | — |
| Hermes Agent | 多Agent协作 (Swarm, Mailbox) | Agent 通信协议 | — | — |
| Spec-Agentic | Plan Mode (思考/行动分离) | task.json BDD 格式 | Constitution + Task Manifest | BDD 约束 |
| Harness Engineering | — | — | Constitution Rules + Anti-Cheat | BDD + TDD |
| OpenClaw | — | Claude Code Hooks 集成 | Hook Bus (事件协议) | — |

### 15.2 文件映射表

| OpenBoss 文件 | 来源 | 说明 |
|--------------|------|------|
| `constitution.md` | `CLAUDE.md` | 进化版：增加版本管理、结构化规则、权限映射 |
| `task-manifest.json` | `task.json` | 进化版：增加 steps、DAG 依赖、BDD 格式 |
| `session-log.md` | `progress.txt` | 进化版：结构化模板、标准化格式 |
| `memory/` | `MEMORY.md` | 进化版：按日期归档、决策记录、经验教训库 |
| `logs/*.jsonl` | AgentCommander 日志系统 | OpenClaw 标准事件格式 |

### 15.3 设计模式溯源

| OpenBoss 设计模式 | 来源 | 验证状态 |
|------------------|------|---------|
| File-Driven State Machine | planning-with-files + 已有项目 | 生产验证（31任务） |
| Constitution-Based Behavior Control | behavior-institutionalization + CLAUDE.md | 生产验证 |
| Verification-Gated Delivery | verification-agent + progress.txt | 生产验证 |
| Atomic Commit Protocol | CLAUDE.md Step 6 + Git 最佳实践 | 生产验证 |
| Blocking/Escalation Protocol | CLAUDE.md Blocking Issues | 生产验证 |
| Ephemeral Agent Pattern | run-automation.sh | 原型验证 |
| Prompt Cache Economics | prompt-cache-economics 技能 | 理论完备 |
| Context Hygiene System | context-hygiene-system 技能 | 理论完备 |
| BDD/TDD Dual Constraint | harness.md | 概念验证 |
| Spec-Agentic 范式 | 综合：Constitution + Task Spec + Output Spec | 设计完备 |
| OpenClaw Protocol | Claude Code Hooks + AgentCommander 通信 | 设计完备 |
| Hermes Agent | Swarm Mailbox + Agent 通信协议 | 设计完备 |

---
*AI生成*
