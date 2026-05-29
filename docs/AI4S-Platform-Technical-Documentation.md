# AI4S 化学平台 — 技术交付文档

**版本：** v1.0  
**日期：** 2026-05-27  
**文档密级：** 内部技术交付  

---

## 目录

1. [任务目标、定位与价值](#一任务目标定位与价值)
2. [已完成的核心能力](#二已完成的核心能力)
3. [系统架构说明](#三系统架构说明)
4. [核心模块技术原理](#四核心模块技术原理)
5. [当前能力边界与局限性](#五当前能力边界与局限性)
6. [验证结论与实际效果](#六验证结论与实际效果)
7. [下一步演进方向](#七下一步演进方向)

---

## 一、任务目标、定位与价值

### 1.1 平台定位

AI4S（AI for Science）化学平台是一个**面向化学专业学生与科研人员的 AI 驱动化学信息学基础设施平台**。平台以"降低化学信息学工具使用门槛、提升科研工作效率"为目标，将数据摄取、分子性质预测、文献智能检索、化学计算工具箱等功能整合于统一界面。

### 1.2 核心价值

传统化学研究中，科研人员面临三大痛点：

| 痛点 | 传统方案 | AI4S 平台方案 |
|------|---------|-------------|
| **化学数据库检索效率低** | 手动查阅 PubChem、PDB 等多个数据库 | 统一分子数据库，支持中文名/CAS/SMILES 多模式检索，一次搜索聚合多源数据 |
| **分子性质计算分散** | 使用 RDKit 命令行、Gaussian 等工具单独计算 | 集成 RDKit 性质预测，一键输出 MW、LogP、TPSA、Lipinski Rule of Five |
| **文献调研耗时** | 在 Google Scholar、Web of Science 之间反复切换 | 集成 Semantic Scholar API，关键词搜索 + 热点方向导航 + 论文 BibTeX 导出 |

### 1.3 技术价值

- **统一数据摄取管道**：Connector → Pipeline (validate → clean → quality) → Snapshot → Catalog，实现从原始数据到可查询数据集的端到端自动化
- **分子性质预测引擎**：基于 RDKit 描述符计算，覆盖分子量、LogP、氢键供体/受体、TPSA、可旋转键、环计数等关键理化参数
- **文献智能检索**：Semantic Scholar API 集成 + 本地搜索历史 + 热点研究方向推荐
- **化学计算工具箱**：6 大实用计算器，覆盖实验配制、pH 计算、单位换算、缓冲溶液等日常需求
- **HPC 超算融合框架**：支持 Slurm/Kubernetes 连接器，作业调度与资源监控
- **RLHF 对齐训练框架**：Feedback Collector → Reward Trainer → PPO/DPO Trainer 完整 RLHF 管线
- **Agent Runtime**：Task Queue → Router → Dispatcher → Tool Executor → Memory Store，支持工具注册与向量记忆

---

## 二、已完成的核心能力

### 2.1 分子数据库模块

**API 端点：** `/api/v1/data/*`（21 个端点）

| 能力 | 说明 | 技术实现 |
|------|------|---------|
| 多模式分子检索 | 支持中文名、英文名、CAS 号、SMILES 表达式检索 | 本地分子库 + `lookupMolecule()` 查找算法 |
| PubChem 数据摄取 | 自动从 PubChem 摄取分子数据，验证与清洗 | PubChem API + Pipeline 验证管道 |
| 分子详情展示 | 分子式、分子量、LogP、HBD/HBA、TPSA、SMILES | RDKit RDKitDescriptors 计算 |
| 热门分子推荐 | 8 个常用药物/分子的快捷入口 | 前端 `POPULAR_MOLECULES` 预设 |
| 搜索历史 | 本地 localStorage 存储，支持回搜与清空 | React state + localStorage |

**支持的检索格式：**
- 中文名：阿司匹林、咖啡因、葡萄糖
- 英文名：aspirin, caffeine, glucose
- CAS 号：50-78-2, 58-08-2
- 分子式：C9H8O4, C6H12O6
- SMILES：`CC(=O)Oc1ccccc1C(=O)O`

### 2.2 文献调研模块

**API 端点：** `/api/v1/agent/literature/search`

| 能力 | 说明 | 技术实现 |
|------|------|---------|
| 关键词搜索 | 支持中英文关键词，搜索化学领域学术论文 | Semantic Scholar Academic Graph API |
| 论文列表展示 | 标题、作者、期刊、年份、引用数 | React 组件 + TypeScript 类型 |
| 摘要展开 | 点击查看/收起论文摘要 | 条件渲染 |
| BibTeX 导出 | 一键生成并下载 BibTeX 引用 | `Blob` + `URL.createObjectURL` |
| 搜索历史 | 最近搜索关键词，支持点击回搜和逐条删除 | localStorage |
| 热点研究方向 | 6 大前沿领域，点击一键搜索 | 预设关键词按钮 |
| 化学前沿动态 | Semantic Scholar 实时高引用论文展示（API 失败时回落 Demo 数据） | Fetch API + 静态回落 |
| 搜索统计 | 总搜索次数、最常搜索关键词 Top 5 | localStorage 持久化 |

**6 大热点研究方向：**
1. Perovskite Solar Cells（钙钛矿太阳能电池）
2. Metal-Organic Frameworks（金属有机框架/MOF）
3. AI Drug Discovery（AI 辅助药物发现）
4. Green Chemistry（绿色化学）
5. 2D Materials（二维材料，如石墨烯）
6. CRISPR Chemistry（基因编辑化学）

### 2.3 性质预测模块

**API 端点：** `/api/v1/data/predict`

| 能力 | 说明 | 技术实现 |
|------|------|---------|
| 分子性质预测 | 输入 SMILES 或名称，输出 10 项理化性质 | RDKit `CalcMolDescriptors` |
| 分子量 (MW) | 精确到 0.01 g/mol | `rdkit.Chem.Descriptors.MolWt` |
| 脂水分配系数 (LogP) | Wildman-Crippen 方法 | `rdkit.Chem.Crippen.MolLogP` |
| 氢键供体/受体 (HBD/HBA) | Lipinski 定义 | `rdkit.Chem.Lipinski` |
| 拓扑极性表面积 (TPSA) | 单位 Å² | `rdkit.Chem.Descriptors.TPSA` |
| 可旋转键 | 反映分子柔性 | `rdkit.Chem.Lipinski.NumRotatableBonds` |
| 环计数 | 脂肪环 + 芳香环 | `rdkit.Chem.Descriptors` |
| Lipinski Rule of Five | 类药五规则自动评估 | 四指标可视化判断 |
| 预测历史 | 最近预测分子记录，可重新预测 | localStorage |

**性质的化学解释（前端展示）：**
- LogP < 0：亲水性强，易溶于水
- LogP 1-3：亲水亲脂适中
- LogP > 5：亲脂性强，难溶于水
- TPSA < 60 Å²：极性较低，容易穿透细胞膜
- TPSA 60-140 Å²：极性适中，通常具有良好的口服生物利用度
- TPSA > 140 Å²：极性较高，口服吸收可能受限

### 2.4 化学计算工具箱

纯前端实现，6 个独立卡片工具：

| 工具 | 核心功能 | 关键技术 |
|------|---------|---------|
| **摩尔质量计算器** | 化学式解析（支持括号如 `Ca(OH)2`），各元素质量贡献，SVG 饼图 | 正则表达式化学式解析器 + 原子量数据库（86 元素） |
| **溶液配制计算器** | 已知浓度配制模式、稀释计算模式（C₁V₁=C₂V₂），公式实时显示 | React useMemo 实时计算 |
| **pH 计算器** | 支持强酸/强碱/弱酸/弱碱四种模式，pH 色卡石蕊试纸可视化 | pH = -log₁₀[H⁺] + 弱酸近似公式 |
| **单位换算器** | 能量/压强/温度/波长 4 大类，双向换算 | Base unit 中间转换标准 |
| **元素周期表查询** | 18×6 网格布局 + 搜索，元素详情（Z、原子量、电子构型、电负性、氧化态） | 86 元素数据集 + 颜色编码（9 大类） |
| **缓冲溶液计算器** | Henderson-Hasselbalch 方程，7 套常用缓冲体系预设 | pH = pKa + log([A⁻]/[HA]) |

### 2.5 统一后端

**技术栈：** FastAPI + PostgreSQL + Redis + Weaviate + Prometheus

| 组件 | 技术选型 | 用途 |
|------|---------|------|
| Web 框架 | FastAPI 0.115+ | 异步 REST API，OpenAPI 自动文档 |
| 关系数据库 | PostgreSQL 16 | 元数据、Catalog、Lineage、Feedback 持久化 |
| 缓存/队列 | Redis 7 | Agent Runtime 任务队列、通用缓存 |
| 向量数据库 | Weaviate 1.24 | Agent 记忆存储与语义检索 |
| 监控 | Prometheus + Grafana | 指标采集、仪表盘可视化 |

### 2.6 一键启动

项目根目录 `start.bat` 支持 Windows 环境一键启动全部服务：

```batch
start.bat
```

自动执行：Docker Compose 启动 PostgreSQL/Redis/Weaviate → 安装 Python 依赖 → 启动 FastAPI 后端 → 启动 Vite 前端开发服务器。

---

## 三、系统架构说明

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI4S 化学平台架构                            │
├───────────────┬─────────────────────────────────────────────────┤
│   Frontend    │  React 18 + TypeScript + Tailwind CSS            │
│   Port 5173   │  Vite 5 构建，lucide-react 图标库                 │
├───────────────┼─────────────────────────────────────────────────┤
│   Backend     │  FastAPI (Python 3.11+) + Uvicorn                │
│   Port 8000   │  OpenTelemetry 链路追踪 + Prometheus Metrics     │
├───────┬───────┼──────────────┬──────────────────────────────────┤
│  data │ agent │    rlhf      │          hpc_fusion               │
│ _infra│_runtime│              │                                   │
│       │       │              │                                   │
│ 摄取管│ 任务   │ RLHF 对齐    │ HPC 超算调度                       │
│ 道 +  │ 调度   │ 训练框架     │ + 监控                            │
│ 分子  │ 工具   │              │                                   │
│ 预测  │ 记忆   │              │                                   │
├───────┴───────┴──────────────┴──────────────────────────────────┤
│   Data Layer                                                      │
│   PostgreSQL 16 ── Redis 7 ── Weaviate 1.24                       │
├─────────────────────────────────────────────────────────────────┤
│   Monitor                                                        │
│   Prometheus ── Grafana (仪表盘)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈详情

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **前端框架** | React | 18.x | 函数组件 + Hooks |
| **前端语言** | TypeScript | 5.x | 类型安全 |
| **前端样式** | Tailwind CSS | 3.4 | Utility-first CSS，自定义 brand 色系 |
| **构建工具** | Vite | 5.4 | 极速 HMR，ESBuild 预构建 |
| **图标库** | lucide-react | 0.x | 轻量 SVG 图标 |
| **路由** | react-router-dom | 6.x | SPA 客户端路由 |
| **后端框架** | FastAPI | 0.115+ | 异步 Python Web 框架 |
| **ASGI 服务器** | Uvicorn | 0.30+ | 高性能 ASGI |
| **ORM** | SQLAlchemy 2.0 | 2.x | 异步引擎 + Alembic 迁移 |
| **关系数据库** | PostgreSQL | 16 | 元数据持久化 |
| **缓存** | Redis | 7 | 任务队列 + 缓存 |
| **向量数据库** | Weaviate | 1.24 | 语义向量存储 |
| **监控** | Prometheus | 2.x | Metrics 采集 |
| **可视化** | Grafana | 10.x | 仪表盘 |
| **化学信息学** | RDKit | 2024.x | 分子描述符计算 |
| **容器化** | Docker Compose | v2 | 基础设施编排 |

### 3.3 前端路由结构

| 路由 | 页面 | 组件 | 说明 |
|------|------|------|------|
| `/` | 重定向至 `/database` | `<Navigate>` | 默认进入数据库 |
| `/database` | 分子数据库 | `<MolecularDatabase>` | 分子检索 + 详情 |
| `/literature` | 文献调研 | `<LiteratureResearch>` | 论文搜索 + 热点 |
| `/prediction` | 性质预测 | `<PropertyPrediction>` | RDKit 分子预测 |
| `/experiments` | 化学计算工具箱 | `<ChemistryToolbox>` | 6 大计算器 |

### 3.4 后端 API 结构

| 模块 | 路由前缀 | 端点数 | 核心功能 |
|------|---------|--------|---------|
| data_infra | `/api/v1/data` | 21 | 数据摄取、Catalog、分子预测、PDF 提取 |
| agent_runtime | `/api/v1/agent` | 16 | 任务队列、工具注册、文献搜索、向量记忆 |
| rlhf | `/api/v1/rlhf` | 11 | 反馈收集、奖励训练、PPO/DPO 策略训练 |
| hpc_fusion | `/api/v1/hpc` | 18 | 作业调度、集群监控、异常检测、容量预测 |

---

## 四、核心模块技术原理

### 4.1 data_infra — 数据基础设施

**设计理念：** 将异构化学数据从原始来源经过标准化管道处理，转化为可搜索、可溯源、可版本化的数据资产。

```
Connector → Pipeline → Snapshot → Catalog
  │           │  │          │          │
  PubChem    validate  clean  quality   Lineage
  REST API    rules   transforms  checks  Graph (Mermaid)
  CSV/JSON
```

**核心流程：**

1. **Connector（连接器）**：抽象数据源接入层
   - `PubChemConnector`：对接 PubChem REST API，按 CID/SMILES 摄取分子数据
   - `GenericConnector`：支持 CSV/JSON 文件导入与 Schema 注册
   - 连接器注册与管理：`POST /data/connectors`、`GET /data/connectors`

2. **Pipeline（管道）**：三阶段数据处理
   - **Validate**：Schema 校验、数据类型检查、必填字段验证
   - **Clean**：标准化转换（单位统一、格式规范化）、去重、缺失值处理
   - **Quality**：质量评分（completeness, accuracy, consistency），生成 PASS RATE
   - 输出：`IngestionReport`（rows_read, rows_written, pass_rate, validation_errors）

3. **Snapshot（快照）**：数据集版本化管理
   - 每次摄取生成一个 Snapshot（snapshot_id, dataset, row_count, parent_snapshot_id）
   - 支持 Diff 对比：两个 Snapshot 之间的差异分析

4. **Catalog（目录）**：可搜索的数据资产清单
   - 元数据：name, description, owner, columns, format, tags, quality_score
   - 搜索过滤：`GET /data/catalog?search=&format=&min_quality=`

5. **Lineage（数据溯源）**：上下游依赖关系图
   - 支持 Mermaid 格式导出（可在 Markdown 中直接渲染为流程图）

### 4.2 agent_runtime — 智能代理运行时

**设计理念：** 构建 AI Agent 的执行环境，支持任务调度、工具调用、记忆管理和外部 API 集成。

```
TaskQueue → Router → Dispatcher → ToolExecutor
                     │                 │
                   Agent Pool      MemoryStore (Weaviate)
```

**核心流程：**

1. **TaskQueue（任务队列）**：基于 Redis 的异步任务管理
   - 提交任务：`POST /agent/tasks` → 返回 task_id
   - 轮询状态：`GET /agent/tasks/{id}` → status (pending/active/completed/dead)
   - 队列统计：`GET /agent/queue/stats` → pending, active, dead 计数

2. **Agent Pool（代理池）**：Agent 注册与生命周期管理
   - 注册 Agent：`POST /agent/agents`（capability 声明）
   - 查询在线 Agent：`GET /agent/agents`
   - 总量统计 + 能力矩阵：total, online, busy, total_capacity, capability_matrix

3. **Tool Registry（工具注册表）**：
   - 注册工具：`POST /agent/tools`（name, description, parameters JSON Schema）
   - 执行工具：`POST /agent/tools/execute`
   - 工具链：`POST /agent/tools/chain`（多工具顺序执行）
   - ToolSchema：OpenAI Function Calling 格式兼容

4. **MemoryStore（记忆存储）**：
   - 存储记忆：`POST /agent/memory`（content, importance, tags）
   - 召回记忆：`POST /agent/memory/recall`（语义相似度搜索）
   - 统计：`GET /agent/memory/stats`（total, avg_importance, sources, tags）
   - 双层存储架构：PostgreSQL（结构化索引）+ Weaviate（向量语义检索）

5. **文献搜索集成**：
   - 端点：`POST /agent/literature/search`
   - 后端代理 Semantic Scholar API 请求（避免 CORS 问题）

### 4.3 rlhf — 人类反馈强化学习

**设计理念：** 构建从反馈收集到策略训练的完整 RLHF 管线，使 AI 模型能够对齐化学领域专家偏好。

```
FeedbackCollector → RewardTrainer → PolicyTrainer (PPO/DPO)
       │                  │                  │
   Annotator          RewardScorer      RLHFPipeline
   Consensus          RewardModel       Iterate/Evaluate
```

**核心流程：**

1. **FeedbackCollector（反馈收集）**：
   - 生成比较对：`POST /rlhf/feedback/items`（prompt + 2 responses）
   - 分配标注任务：`POST /rlhf/feedback/assign`
   - 提交标注：`POST /rlhf/feedback/annotate`（choice: chosen/rejected, confidence）
   - 共识聚合：`GET /rlhf/feedback/consensus`（_agreement, _num_annotators）
   - 标注者质量：`GET /rlhf/feedback/annotator-quality`（accuracy, avg_confidence）

2. **RewardTrainer（奖励训练）**：
   - 奖励评分：`POST /rlhf/reward/score` → RewardScore（prompt + score）
   - 基于 Bradley-Terry 偏好模型训练奖励函数

3. **PolicyTrainer（策略训练）**：
   - PPO（Proximal Policy Optimization）训练：`POST /rlhf/policy/train?algorithm=ppo`
   - DPO（Direct Preference Optimization）训练：`POST /rlhf/policy/train?algorithm=dpo`
   - 输出：`PolicyTrainResult`（epochs, final_loss, n_prompts）

4. **RLHFPipeline（完整管线）**：
   - 迭代训练：`POST /rlhf/pipeline/iterate`（自动 collect → train → evaluate）
   - 评估：`POST /rlhf/pipeline/evaluate`（avg_reward）

### 4.4 hpc_fusion — 高性能计算融合

**设计理念：** 对化学计算中常见的 DFT、MD 等大规模计算任务进行作业调度与集群资源管理，抽象底层 Slurm/K8s 差异。

```
JobPrioritizer → SchedulingEngine → Connector (Slurm / K8s)
       │                                   │
  Preemption/Backfill              MetricsCollector
                                   AnomalyDetector
```

**核心流程：**

1. **JobPrioritizer（作业优先级）**：
   - 提交作业：`POST /hpc/jobs`（name, partition, nodes, gpus_per_node）
   - 支持抢占策略（Preemption）和回填调度（Backfill）

2. **SchedulingEngine（调度引擎）**：
   - 调度器状态：`GET /hpc/scheduler/status`（policy, pending, running, queues）
   - 手动触发调度周期：`POST /hpc/scheduler/cycle`

3. **连接器抽象层**：
   - `SlurmConnector`：通过 SSH + `squeue`/`sbatch` 命令管理 Slurm 集群
   - `K8sConnector`：通过 Kubernetes API 管理容器化作业

4. **MetricsCollector（指标采集）**：
   - 集群快照：`GET /hpc/metrics/cluster`（nodes, avg_gpu_util, avg_cpu_util）
   - 容量余量：`GET /hpc/metrics/headroom`（remaining_capacity_pct, estimated_free_gpus）
   - 单节点历史：`GET /hpc/nodes`

5. **异常检测与告警**：
   - 异常检测：`GET /hpc/analysis/anomalies`（node, metric, severity, message）
   - 健康报告：`GET /hpc/analysis/health`
   - 告警管理：创建/查询/解决（CRUD）

---

## 五、当前能力边界与局限性

### 5.1 分子性质预测

| 维度 | 当前能力 | 局限性 |
|------|---------|--------|
| 计算精度 | RDKit 经验描述符（MW, LogP, TPSA 等） | 不支持量子化学精度计算（DFT、CCSD(T)），无法预测反应能垒、过渡态 |
| 分子类型 | 有机小分子（药物分子为主） | 暂不支持金属配合物、聚合物、蛋白质等大分子 |
| 3D 构象 | 无 | 不支持 3D 结构优化与可视化 |

### 5.2 文献搜索

| 维度 | 当前能力 | 局限性 |
|------|---------|--------|
| 数据源 | Semantic Scholar Academic Graph | 单数据源，未集成 Google Scholar、PubMed、arXiv |
| 检索深度 | 标题 + 摘要匹配 | 不支持全文检索、语义理解式搜索 |
| 自动化程度 | 关键词搜索 + 结果展示 | 不支持论文自动摘要、中文翻译、知识图谱构建 |

### 5.3 HPC 超算模块

| 维度 | 当前能力 | 局限性 |
|------|---------|--------|
| 部署状态 | 框架级实现，代码完备 | 未对接真实超算集群（需要实际 Slurm/K8s 环境） |
| 调度策略 | FIFO + 抢占 + 回填 | 暂无高级调度策略（如 Gang Scheduling、公平共享） |

### 5.4 RLHF 模块

| 维度 | 当前能力 | 局限性 |
|------|---------|--------|
| 硬件要求 | 代码支持 GPU 训练 | 完整 RLHF 训练需要至少 1 张 A100/H100 GPU |
| 数据需求 | 框架完成 | 真实化学领域偏好数据需要人工标注积累 |

### 5.5 整体系统

| 维度 | 当前能力 | 局限性 |
|------|---------|--------|
| 用户系统 | 无 | 无用户认证、权限管理、多租户隔离 |
| 部署方式 | Docker Compose 一键启动 | 暂不支持 Kubernetes 生产集群部署 |
| 数据安全 | 本地存储 | 无数据加密、审计日志、备份策略 |

---

## 六、验证结论与实际效果

### 6.1 分子性质预测验证

| 测试分子 | 预测 MW (g/mol) | 标准值 (g/mol) | 偏差 | 结果 |
|---------|----------------|---------------|------|------|
| 咖啡因 (Caffeine) | 194.19 | 194.19 | 0.00 | ✅ PASS |
| 阿司匹林 (Aspirin) | 180.16 | 180.16 | 0.00 | ✅ PASS |
| 布洛芬 (Ibuprofen) | 206.28 | 206.28 | 0.00 | ✅ PASS |
| 葡萄糖 (Glucose) | 180.16 | 180.16 | 0.00 | ✅ PASS |

**结论：** RDKit 描述符计算的分子量与国际标准值完全一致（偏差 < 0.01 g/mol）。

### 6.2 数据摄取验证

| 测试项 | 指标 | 结果 |
|--------|------|------|
| PubChem 数据摄取 | PASS RATE | **100%** |
| Schema 验证 | 字段完整性 | 全部通过 |
| 数据清洗 | 格式标准化 | 正常执行 |

### 6.3 化学计算工具箱验证

**30 项全量测试，全部通过（2026-05-27 Playwright 自动化测试）：**

| 工具 | 测试用例 | 预期结果 | 实际结果 |
|------|---------|---------|---------|
| 摩尔质量计算器 | H₂SO₄ | 98.08 g/mol | ✅ 98.08 |
| 摩尔质量计算器 | C₆H₁₂O₆ | 180.16 g/mol | ✅ 180.16 |
| 摩尔质量计算器 | Ca(OH)₂ | 74.09 g/mol | ✅ 74.09 |
| 摩尔质量计算器 | 无效化学式 | 错误提示 | ✅ "无法解析化学式" |
| 溶液配制 | 0.1M × 500mL × MW58.44 | 2.922 g | ✅ 2.922 |
| 溶液稀释 | C1=1, V1=100, C2=0.05 | V2=2000, +1900mL | ✅ |
| pH 计算 | 强酸 0.1M | pH=1.00 | ✅ 1.00 |
| pH 计算 | 强碱 0.1M | pH=13.00 | ✅ 13.00 |
| pH 计算 | 弱酸 Ka=1.8×10⁻⁵ | pH≈2.87 | ✅ 2.87 |
| 单位换算 | 1 eV | 96.485 kJ/mol | ✅ 96.485 |
| 单位换算 | 0°C | 273.15 K | ✅ 273.15 |
| 元素周期表 | 搜索 Fe | Z=26, 电子构型 | ✅ |
| 缓冲溶液 | 醋酸缓冲 pKa=4.76 | pH=4.76 | ✅ 4.76 |
| 缓冲溶液 | [A⁻]/[HA]=0.1 | pH=3.76 | ✅ 3.76 |

**平台改进验证（2026-05-27，19 项测试全部通过）：**

| 模块 | 新增功能 | 验证结果 |
|------|---------|---------|
| 文献调研 | 搜索历史 + 逐条删除 | ✅ |
| 文献调研 | 6 大热点研究方向可点击搜索 | ✅ |
| 文献调研 | Semantic Scholar 新闻卡片 | ✅ |
| 文献调研 | 搜索统计（总数 + Top 关键词） | ✅ |
| 分子数据库 | 热门分子推荐卡片（8 个） | ✅ |
| 性质预测 | 预测历史记录 + 重新预测 | ✅ |

### 6.4 系统可用性

- **一键启动**：Windows 环境下执行 `start.bat`，5 分钟内完成全部服务启动
- **无需专业运维**：所有基础设施通过 Docker Compose 编排，自动处理依赖关系
- **跨平台支持**：前端纯 Web 技术，后端 Python 跨平台，可通过 Docker 在任何 OS 运行

---

## 七、下一步演进方向

### 第一阶段（近期，1-2 个月）

| 序号 | 演进方向 | 优先级 | 预计工作量 |
|------|---------|--------|-----------|
| 1 | **3D 分子可视化**：集成 RDKit `MolDraw2D` → 3D 构象生成与 WebGL 渲染 | 🔴 高 | 3 周 |
| 2 | **分子相似性搜索**：基于 Morgan Fingerprint 的 Tanimoto 相似度，支持子结构检索 | 🔴 高 | 3 周 |
| 3 | **文献自动摘要**：集成 LLM（GPT-4o 或 Claude）对搜索论文进行中文摘要生成 | 🟡 中 | 2 周 |

### 第二阶段（中期，3-6 个月）

| 序号 | 演进方向 | 优先级 | 预计工作量 |
|------|---------|--------|-----------|
| 4 | **DFT 计算接口**：对接 Gaussian 16 / ORCA 计算服务，支持量子化学精度 | 🟡 中 | 6 周 |
| 5 | **用户系统**：OAuth 2.0 登录（Google/GitHub/ORCID），JWT 认证 + 权限管理 | 🟡 中 | 4 周 |
| 6 | **自定义实验数据上传**：支持 CSV/Excel 格式实验数据导入，对接 RLHF 微调流程 | 🟡 中 | 4 周 |
| 7 | **中文翻译**：基于大模型将英文论文标题和摘要自动翻译为中文 | 🟢 低 | 2 周 |

### 第三阶段（远期，6-12 个月）

| 序号 | 演进方向 | 优先级 | 预计工作量 |
|------|---------|--------|-----------|
| 8 | **生产级 Kubernetes 部署**：Helm Chart + CI/CD (GitHub Actions) | 🟢 低 | 8 周 |
| 9 | **知识图谱构建**：从文献中自动抽取化学实体关系，构建可查询的化学知识网络 | 🟢 低 | 8 周 |
| 10 | **反应预测**：基于 Transformer 的逆合成分析与反应产率预测 | 🟢 低 | 12 周 |

---

## 附录

### A. 快速启动指南

```bash
# Windows 环境
start.bat

# 手动启动（Linux/macOS）
docker compose up -d                    # 启动 PostgreSQL + Redis + Weaviate
cd backend && pip install -e . && uvicorn main:app --port 8000 &
cd frontend && npm install && npm run dev -- --port 5173 &
```

### B. 环境变量参考

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `AI4S_DATABASE_URL` | `postgresql+asyncpg://ai4s:ai4s@localhost:5432/ai4s` | PostgreSQL 连接 |
| `AI4S_REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 |
| `AI4S_WEAVIATE_URL` | `http://localhost:8080` | Weaviate 连接 |
| `AI4S_AGENT_RUNTIME__MEMORY__BACKEND` | `weaviate` | 记忆存储后端 |

### C. 项目仓库

- **GitHub:** https://github.com/z2875596-crypto/ai4s-infra

---

> **文档编写：** AI4S 开发团队  
> **最后更新：** 2026-05-27  
> **版本：** v1.0
