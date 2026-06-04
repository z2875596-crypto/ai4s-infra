# 鸢见 YuanJian · AI4S-Infra

## 项目概览

**鸢见 (YuanJian)** — 面向化学与材料科学的 AI 科研平台，基于 ReAct 模式的多步推理 Agent，提供文献调研、分子数据库查询、性质预测、化学计算等一体化工具。

- **后端**: Python 3.10+ / FastAPI / Uvicorn
- **前端**: React 18 + TypeScript + Vite + Tailwind CSS
- **LLM**: DeepSeek API (Function Calling)
- **数据库**: SQLite (session), PostgreSQL (metadata), Redis (queue), Weaviate (vector)
- **容器化**: Docker / docker-compose

## 目录结构

```
ai4s-infra/
├── main.py                     # FastAPI 统一入口
├── pyproject.toml              # Python 依赖与项目配置
├── start.bat                   # Windows 一键启动脚本
├── docker-compose.yml          # 全部服务编排
├── config/
│   └── settings.yaml           # 全局配置
├── data/                       # 运行时数据 (SQLite 等)
├── docs/                       # 技术文档
├── docker/                     # Dockerfile + 监控配置
├── tests/                      # 各模块测试
│
├── ai4s/                       # 后端 Python 包
│   ├── __init__.py             # 版本 0.1.0
│   │
│   ├── agent/                  # ReAct 科研 Agent
│   │   ├── orchestrator.py     # 核心：ReAct 循环 + 5 个工具 + DeepSeek API
│   │   ├── router.py           # SSE 流式 API 端点 + docx 导出
│   │   └── memory.py           # SQLite 会话记忆
│   │
│   ├── agent_runtime/          # Agent 运行时引擎
│   │   ├── api.py              # 任务调度 API
│   │   ├── orchestration.py    # 编排引擎
│   │   ├── tools/              # 工具注册/执行/沙箱
│   │   │   ├── registry.py     # 工具注册中心
│   │   │   ├── executor.py     # 工具执行器
│   │   │   ├── literature_search.py  # Semantic Scholar + CrossRef 文献搜索
│   │   │   └── sandbox.py      # 沙箱隔离
│   │   ├── scheduler/          # 任务调度 (队列/分发/路由)
│   │   └── memory/             # 向量记忆 (存储/检索/摘要)
│   │
│   ├── data_infra/             # 数据基础架构
│   │   ├── api.py              # REST API (分子渲染/预测/PubChem/PDF/目录)
│   │   ├── prediction.py       # RDKit 分子性质预测
│   │   ├── ingestion/          # 数据接入 (connector/pipeline/pubchem/pdf)
│   │   ├── cleaning/           # 数据清洗 (validator/transformer/quality)
│   │   └── versioning/         # 数据版本管理 (catalog/lineage/snapshot)
│   │
│   ├── hpc_fusion/             # HPC 融合计算
│   │   ├── api.py              # 作业/调度/监控 API
│   │   ├── connector/          # Slurm / Kubernetes 连接器
│   │   ├── scheduler/          # 作业调度 (engine/placement/priority)
│   │   └── monitor/            # 监控告警 (collector/analyzer/alert)
│   │
│   ├── rlhf/                   # 基于人类反馈的强化学习
│   │   ├── api.py              # 反馈/奖励/策略 API
│   │   ├── feedback/           # 反馈收集与聚合
│   │   ├── reward/             # 奖励模型
│   │   └── policy/             # 策略优化 (PPO/DPO/trainer)
│   │
│   └── common/                 # 共享基础设施
│       ├── config.py           # YAML 配置加载
│       ├── logging.py          # 结构化日志
│       ├── metrics.py          # Prometheus 指标
│       └── exceptions.py       # 异常定义
│
└── frontend/                   # React 前端
    ├── index.html
    ├── vite.config.ts          # Vite 配置 (端口 3000, 代理 /api → :8000)
    ├── tailwind.config.js
    ├── public/
    └── src/
        ├── App.tsx             # 路由定义 (5 个页面)
        ├── main.tsx            # 入口
        ├── index.css           # Tailwind + 全局样式
        ├── api/
        │   └── client.ts       # 后端 API 客户端封装
        ├── components/
        │   ├── Layout.tsx      # 侧边栏导航布局
        │   ├── Logo.tsx
        │   ├── StatCard.tsx
        │   └── StatusBadge.tsx
        ├── pages/
        │   ├── AgentConsole.tsx      # /agent — AI 研究助手 (ReAct Agent)
        │   ├── MolecularDatabase.tsx  # /database — 分子数据库
        │   ├── LiteratureResearch.tsx # /literature — 文献调研
        │   ├── PropertyPrediction.tsx # /prediction — 性质预测
        │   └── ChemistryToolbox.tsx   # /experiments — 化学工具箱 (周期表等)
        └── types/
            └── index.ts        # TypeScript 类型定义
```

## 启动命令

### 后端

```bash
# 安装依赖
pip install -e .

# 启动开发服务器
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev   # 端口 3000, 自动代理 /api → localhost:8000
```

### Windows 一键启动

```bash
start.bat
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 (必填) | — |
| `DEEPSEEK_MODEL` | 模型名称 | deepseek-v4-flash |
| `DEEPSEEK_BASE_URL` | API 基础地址 | https://api.deepseek.com/v1 |

## 核心模块说明

### Agent Orchestrator

位于 `ai4s/agent/orchestrator.py`，基于 ReAct (Thought → Action → Observation) 模式的科研 Agent，通过 DeepSeek API 的 Function Calling 实现。工作流程：

1. 接收用户研究问题
2. LLM 思考 → 决定调用工具 → 观察结果 → 再次思考...
3. 收集足够信息后生成综合研究报告
4. SSE 流式推送每个步骤到前端

核心类 `AgentOrchestrator` (第 522 行) 提供 `run()` 异步生成器方法，逐条产出 `AgentEvent` (thought/action/observation/answer/error/done)。

### 五个科研工具

定义在 `ai4s/agent/orchestrator.py` 第 111-201 行的 `TOOL_DEFINITIONS` 中：

| 工具 | 函数 | 数据来源 |
|------|------|----------|
| `search_literature` | 文献搜索 | Semantic Scholar API (主) / CrossRef (备) |
| `search_pubchem` | 化合物查询 | PubChem REST API |
| `predict_properties` | 分子性质预测 | RDKit (MW/LogP/HBD/HBA/TPSA/Lipinski) |
| `calculate_molar_mass` | 摩尔质量计算 | 内置元素表 (本地解析) |
| `lookup_element` | 元素查询 | 内置元素周期表数据 |

### 前端页面与路由

定义在 `frontend/src/App.tsx`:

| 路由 | 页面组件 | 说明 |
|------|----------|------|
| `/` | → `/agent` 重定向 | — |
| `/agent` | `AgentConsole.tsx` | AI 研究助手 — ReAct Agent SSE 流式交互 |
| `/database` | `MolecularDatabase.tsx` | 分子数据库 — 名称/SMILES/CAS 搜索 |
| `/literature` | `LiteratureResearch.tsx` | 文献调研 — Semantic Scholar 论文搜索 |
| `/prediction` | `PropertyPrediction.tsx` | 性质预测 — RDKit 理化性质 + Lipinski 规则 |
| `/experiments` | `ChemistryToolbox.tsx` | 化学工具箱 — 摩尔质量计算/溶液配制/pH/单位换算/周期表 |

### API 路由前缀

| 模块 | 前缀 | 文件 |
|------|------|------|
| Data Infra | `/api/v1/data` | `ai4s/data_infra/api.py` |
| Agent Runtime | `/api/v1/agent` | `ai4s/agent_runtime/api.py` |
| Agent Research | `/api/agent` | `ai4s/agent/router.py` |
| RLHF | `/api/v1/rlhf` | `ai4s/rlhf/api.py` (可选) |
| HPC Fusion | `/api/v1/hpc` | `ai4s/hpc_fusion/api.py` (可选) |

前端 API 客户端封装在 `frontend/src/api/client.ts` 中，使用 `/api/v1` 基础路径。

## 开发注意事项

### 新增工具的方法

1. 在 `ai4s/agent/orchestrator.py` 的 `TOOL_DEFINITIONS` 中添加工具 schema
2. 编写对应的 `_execute_<tool_name>` 异步/同步函数
3. 在 `TOOL_EXECUTORS` 字典中注册
4. 在 `AgentConsole.tsx` 的 `TOOL_LABELS` 中添加中文标签（可选，前端显示用）

### 代码风格

- Python: `ruff` (line-length 100), target `py310`
- TypeScript/React: strict mode
- 后端所有 API 使用 Pydantic v2 请求/响应模型
- 前端使用 Tailwind CSS + lucide-react 图标

### 常见问题

- **DeepSeek API 密钥缺失**: Agent 启动时报错 "DeepSeek API key 未配置"，需设置 `DEEPSEEK_API_KEY` 环境变量
- **RDKit 未安装**: 分子性质预测和 SMILES 渲染功能会降级，可通过 `pip install rdkit` 安装
- **CORS**: 开发时允许所有来源；生产环境需在 `main.py` 中限制 `allow_origins`
- **端口冲突**: 后端 8000，前端 3000，可在 `.env` 或 `vite.config.ts` 中修改
- **Windows 编码**: Agent 输出包含 Unicode 字符时使用 `_safe_print_json()` 兼容 GBK 编码

### 基础架构模块

`agent_runtime/`、`data_infra/`、`hpc_fusion/`、`rlhf/` 四个模块是底层基础架构，各自独立可插拔，由 `main.py` 统一挂载。科研 Agent 位于 `agent/` 目录，直接面向用户交互。
