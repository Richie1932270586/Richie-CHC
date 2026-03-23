# Factory Exception Agent

一个面向厂内物流、仓储、线边补料、质检协同场景的 AI Agent demo。

它优先解决厂内物流场景里的 SOP 查询和异常处理，也保留了基础聊天引导能力：

用户输入异常描述 -> Agent 判断问题类型 -> 检索 SOP/规则 -> 查询本地表格 -> 给出处理建议 -> 生成工单/通知/记录草稿 -> 命中敏感动作时要求人工确认。

这是一个产品 demo，不是企业级正式系统。当前版本没有接入真实 ERP / WMS / IM / 工单系统，所有动作都停留在“草稿生成”和“确认提示”层。

## 项目简介

### 这是一个什么 Agent

这是一个“厂内物流异常处理 Agent”。它把三个能力揉在一起：

1. 本地知识检索（RAG）
2. 本地结构化查表（inventory / incidents / owners / templates）
3. 动作草稿生成 + 人工确认

### 解决什么业务问题

v1 主要解决以下异常咨询：

- 短缺
- 错发
- 不良品
- 批次异常
- 库位异常
- 高优先级停线风险

### v1 的能力边界

当前版本可以：

- 判断问题类型
- 检索本地 SOP / 规定 / FAQ / 作业说明
- 查询本地 mock 表格
- 在同一会话里保留上下文，支持继续追问“下一步呢 / 注意什么 / 为什么要这样做”
- 支持前端多会话切换，适合同时测不同 SOP 或异常场景
- 对“你好 / 你能做什么 / 谢谢”这类普通聊天做基本响应
- 输出结论、处理步骤、风险提醒、引用来源
- 生成工单草稿、升级通知草稿、处理记录草稿
- 对报废、停线风险升级、责任归属、对外通知要求人工确认

当前版本不做：

- 真实消息发送
- 真实权限控制
- 真实 ERP / WMS / IM 集成
- 严格评测和线上监控

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（只在你想用 Vite + React 前端开发模式时需要）

### 安装依赖

后端依赖：

```bash
cd projects/factory-exception-agent
python -m pip install -r apps/api/requirements.txt
```

前端依赖，仅开发 React 源码时需要：

```bash
cd projects/factory-exception-agent/apps/web
npm install
```

### 配置 .env

先复制示例配置：

```bash
cd projects/factory-exception-agent
copy .env.example .env
```

如果你在 PowerShell 中，也可以用：

```powershell
Copy-Item .env.example .env
```

### 如何用 mock mode 跑起来

默认就是 mock mode。`.env` 中这两个配置保持如下即可：

```env
MOCK_MODE=true
LLM_PROVIDER=mock
```

注意：
- 这个模式不是“真实大模型聊天”，而是“本地语义匹配 + RAG 检索 + 规则编排”。
- 它适合演示 SOP 检索、异常处理链路和工具调用，不适合拿来评估真实闲聊能力。
- 如果你要测试“像 ChatGPT 一样的日常对话”和更自然的总结能力，请切到下面的真实模型模式。

然后执行：

```bash
cd projects/factory-exception-agent
python scripts/reset_demo_data.py
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
```

启动后打开：

- Demo UI: `http://127.0.0.1:8000`
- API 健康检查: `http://127.0.0.1:8000/health`
- 已索引文档列表: `http://127.0.0.1:8000/api/rag/documents`

### 如何启动前后端

最简单的演示方式：

1. 只启动后端
2. 使用后端内置静态页面
3. 打开 `http://127.0.0.1:8000`

如果你想继续改 React 页面，再额外启动前端开发服务：

```bash
cd projects/factory-exception-agent/apps/web
npm run dev
```

此时前端开发地址一般是：

- `http://127.0.0.1:5173`

### 如何导入本地 Office SOP 文件夹

现在项目已经支持直接导入本地文件夹中的：

- `.docx`
- `.xlsx`
- `.pptx`

有两种方式：

方式 A：用前端页面导入

1. 启动后端
2. 打开 `http://127.0.0.1:8000`
3. 在页面里的“Office 文件导入 RAG”面板输入本地文件夹路径
4. 点击“导入文件夹到 RAG”

方式 B：用脚本导入

```bash
python scripts/import_office_folder.py "E:\实习工作\中都物流-小米工作文件\小米汽车作业标准流程"
```

导入后，系统会把提取出来的文本写入：

- `data/knowledge_base/imported_office/`

并自动重建索引。

### 如何切换真实模型

当前项目默认推荐：

- 本地 `Ollama`
- 千问 3.5，默认按 `qwen3.5:9b` 配置

说明：

- 截至 `2026-03-23`，Ollama 官方 `qwen3.5` 页面公开可见的 tag 包括 `0.8b / 2b / 4b / 9b / 27b / 35b / 122b`，默认 `latest` 指向 `9b`，没有公开列出 `14b`。
- 为了避免把项目默认改成一个拉取时可能失败的 tag，这里统一改成官方可验证、可直接通过 Ollama 使用的 `qwen3.5:9b`。
- 如果你本机已经手动创建或拉取了自定义 tag，例如 `qwen3.5:14b`，只改 `LLM_MODEL` 一项即可。

把 `.env` 改成：

```env
MOCK_MODE=false
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen3.5:9b
LLM_API_KEY=ollama
LLM_REASONING_EFFORT=none
LLM_MAX_TOKENS=480
```

如果你已经安装了 Ollama，先执行：

```bash
ollama pull qwen3.5:9b
ollama serve
```

说明：

- 这里用的是“OpenAI 兼容接口”写法，不把厂商写死
- 你也可以换成其他兼容 `/chat/completions` 的网关
- 如果你本机实际模型名不是 `qwen3.5:9b`，例如自定义成 `qwen3.5:14b`，改 `.env` 的 `LLM_MODEL` 即可
- 如果接入的是支持 thinking / reasoning 的模型，推荐保持 `LLM_REASONING_EFFORT=none`，避免普通问句长时间停在“思考中”
- 推荐显式设置 `LLM_MAX_TOKENS=480`，避免 OpenAI 兼容接口在某些本地模型上输出过长
- 即使真实模型调用失败，系统也会回退到本地 mock 格式化逻辑，不至于整个 demo 打不开

## 演示方法

下面这些输入可以直接复制到页面里测试：

1. `产线 A 反馈零件X 短缺，当前批次 B202603，应该怎么处理？`
2. `收货时发现一箱标签和实物不一致，是否需要升级？`
3. `有一批传感器Y 疑似不良品，先做隔离还是直接退库？`
4. `外壳P 批次 B202603 重复异常，是否需要升级质检？`
5. `系统显示轴承M 在 D-02-01，但现场找不到，算库位异常吗？`
6. `零件X 余量不够，2 小时内可能停线，要不要马上升级？`
7. `这批疑似不良品如果要报废，需要直接走报废流程吗？`
8. `需要通知供应商这次标签错贴问题吗？`
9. `指导进行冲压车间自制件返修作业`
10. `下一步呢？`
11. `注意什么？`
12. `为什么要扫描推荐库位码？`
13. `你好`
14. `你能做什么？`

## RAG 使用与增删方法

这一部分尽量按“产品同学也能照着做”的方式写。

### 1. 往知识库里新增文档

当前支持两类方式：

- 直接放入 `.md` / `.txt`
- 从本地 Office 文件夹批量导入 `.docx` / `.xlsx` / `.pptx`

把新的 `.md` 或 `.txt` 文件放进：

`data/knowledge_base/`

建议文件名带类型前缀，便于后续管理，例如：

- `SOP-new-inbound-check.md`
- `RULE-supplier-escalation.md`
- `FAQ-quality-hold.md`

然后重建索引：

```bash
python scripts/ingest_kb.py
```

如果你的知识库原始文件是 Office 格式，直接导入整个文件夹：

```bash
python scripts/import_office_folder.py "你的文件夹路径"
```

或者直接在页面里的“Office 文件导入 RAG”面板操作。

### 2. 删除某些文档

直接删掉 `data/knowledge_base/` 下不想保留的文件。

如果是通过 Office 导入生成的文档，通常在：

- `data/knowledge_base/imported_office/`

然后再次执行：

```bash
python scripts/ingest_kb.py
```

### 3. 重新构建索引

只重建知识库索引：

```bash
python scripts/ingest_kb.py
```

连同 demo 数据一起重置并重建：

```bash
python scripts/reset_demo_data.py
```

### 4. 临时关闭 RAG

有两种方式：

方式 A：页面里把 `启用 RAG` 关掉

方式 B：修改 `.env`

```env
RAG_ENABLED=false
```

然后重启后端。

### 5. 切换成 only-tool mode

把 `.env` 改成：

```env
AGENT_MODE=only-tool
```

或者直接在页面右上角把模式切成 `only-tool`。

这个模式下，Agent 不走知识检索，只查表和走规则。

### 6. 设置 light-RAG / full-RAG

修改 `.env`：

```env
RAG_PROFILE=light
```

或

```env
RAG_PROFILE=full
```

区别：

- `light`：更适合 demo 演示，返回更少更快
- `full`：召回更多，适合排查“为什么没命中文档”

### 7. 修改 top_k、chunk_size、chunk_overlap

在 `.env` 中改这些值：

```env
RAG_TOP_K=4
RAG_FULL_TOP_K=6
CHUNK_SIZE=260
CHUNK_OVERLAP=50
```

修改后重新执行：

```bash
python scripts/ingest_kb.py
```

然后重启后端。

### 8. 替换 embedding 配置

当前项目默认不是远程 embedding，而是本地的 `local-bow` 轻量检索方案。

你可以先在 `.env` 里改标识：

```env
EMBEDDING_PROVIDER=local-bow
EMBEDDING_MODEL=token-frequency-v1
```

如果后续要接入真实 embedding：

1. 在 `apps/api/app/services/retriever.py` 增加新的 provider 分支
2. 通过 `.env` 切换 `EMBEDDING_PROVIDER` 和 `EMBEDDING_MODEL`
3. 重新 ingest

这个 demo 先把接口和配置位留出来，默认实现仍是本地轻量方案。

### 9. 替换 rerank 配置

当前版本是简化 rerank，只做了规则加权。

通过 `.env` 可以先开关：

```env
RERANK_ENABLED=true
```

如果后续要换成真实 reranker，主要改：

- `apps/api/app/services/retriever.py`

### 10. 查看当前被索引了哪些文档

方法 1：打开接口

- `http://127.0.0.1:8000/api/rag/documents`

方法 2：直接看索引文件

- `data/indexes/kb_index.json`

方法 3：看 Office 导入记录

- `data/indexes/import_manifest.json`

## 微调说明

这里要区分两层含义。

### A. 非训练式微调

这是当前项目最推荐的调优方式，也是大多数产品 demo 最应该先做的。

你可以调这些内容：

- 修改 system prompt
- 修改回答风格
- 修改工具调用策略
- 修改高风险动作阈值
- 修改检索策略
- 调整输出模板

优先改这些文件：

- `prompts/system_prompt.md`
- `prompts/tool_policies.md`
- `prompts/response_style.md`
- `.env`
- `apps/api/app/services/agent.py`
- `apps/api/app/services/retriever.py`

结论很直接：

对于 demo 和大部分产品验证，优先做这类微调，不需要训练模型。

### B. 训练式微调

当前项目没有默认依赖训练式微调，但已经预留了后续切换真实模型的入口。

什么场景下才值得考虑训练式微调：

- 异常分类想要更稳定
- 字段抽取想要更统一
- 工单模板生成风格想强约束

适合微调的任务：

- 异常分类
- 字段抽取
- 工单模板生成风格统一

不适合微调的任务：

- 最新知识问答
- 强依赖私有文档的事实检索
- 高频变动规则的即时问答

如果后续要做 LoRA / QLoRA，建议：

1. 新建目录 `data/training/`
2. 把训练样本按任务拆开保存，例如 `classification.jsonl`、`extraction.jsonl`
3. 把推理模型切换仍统一走 `.env` 的 `LLM_MODEL` / `LLM_BASE_URL`
4. 若要新接本地微调模型，优先从 `apps/api/app/services/llm_client.py` 扩展 provider

当前项目明确不默认依赖训练式微调。

## 如何替换业务场景

如果以后不做“厂内物流异常处理”，而是要改成“司机运营活动 Agent”或“客服规则 Agent”，优先改这些位置：

- `prompts/`
- `data/knowledge_base/`
- `data/knowledge_base/imported_office/`
- `data/mock_tables/`
- `docs/PRD.md`
- `docs/tool-spec.md`

更具体地说：

1. 改 `prompts/`，把角色、边界、输出格式换成新场景
2. 改 `data/knowledge_base/`，换成新的 SOP / FAQ / 规则
3. 如果你是从 Office 文件夹导入，重新执行页面导入或 `scripts/import_office_folder.py`
4. 改 `data/mock_tables/`，换成本场景需要查的表
5. 改 `docs/PRD.md` 和 `docs/tool-spec.md`，保持产品文档与实现一致
6. 如有新的问题分类，再改 `apps/api/app/services/classifier.py`
7. 如有新的动作草稿，再改 `apps/api/app/services/drafts.py`

## 已知限制

- mock 数据有限
- 没有真实权限系统
- 没有接企业 IM / ERP / WMS
- 暂未做严谨评测
- 当前 RAG 是轻量本地实现，不是企业级向量库
- 当前“人工确认”是 UI 和接口层确认，不是审批流
- 当前普通聊天能力是产品 demo 级兜底，不等于通用大模型助手
- 当前普通聊天能力是产品 demo 级兜底，不等于通用大模型助手

## 目录结构

```text
factory-exception-agent/
├─ apps/
│  ├─ api/
│  └─ web/
├─ data/
│  ├─ knowledge_base/
│  ├─ mock_tables/
│  └─ eval_cases/
├─ docs/
├─ prompts/
├─ scripts/
├─ .env.example
├─ README.md
└─ AGENTS.md
```

## 常用命令

```bash
python scripts/reset_demo_data.py
python scripts/ingest_kb.py
python scripts/import_office_folder.py "你的本地文件夹路径"
python scripts/run_eval.py
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 --reload
```
