# RAG 使用指南

## 当前实现说明

当前 demo 使用的是轻量本地 RAG：

- 文档来源：`data/knowledge_base/`
- Office 导入中间文件：`data/knowledge_base/imported_office/`
- 索引文件：`data/indexes/kb_index.json`
- 导入记录：`data/indexes/import_manifest.json`
- 默认检索方式：本地 token 频次 + 简化 rerank

目标是先保证 demo 可跑和可解释，不追求企业级检索复杂度。

## 如何添加文档

1. 把 `.md` 或 `.txt` 文件放入 `data/knowledge_base/`
2. 文件名最好带类型前缀，例如 `SOP-`、`RULE-`、`FAQ-`
3. 执行：

```bash
python scripts/ingest_kb.py
```

4. 打开 `http://127.0.0.1:8000/api/rag/documents` 检查是否已被索引

## 如何导入 Office 文件夹

现在项目支持直接导入本地文件夹中的：

- `.docx`
- `.xlsx`
- `.pptx`

方式 1：页面导入

1. 启动后端并打开 `http://127.0.0.1:8000`
2. 在“Office 文件导入 RAG”面板里输入本地文件夹路径
3. 点击“导入文件夹到 RAG”

方式 2：脚本导入

```bash
python scripts/import_office_folder.py "E:\实习工作\中都物流-小米工作文件\小米汽车作业标准流程"
```

导入完成后：

- 原始 Office 文件不会被修改
- 提取后的文本会写入 `data/knowledge_base/imported_office/`
- 索引会自动重建

如果再次导入同一路径，默认会覆盖这一路径上次的导入结果。

## 如何删除文档

1. 删除 `data/knowledge_base/` 下对应文件
2. 如果要删除 Office 导入结果，删除 `data/knowledge_base/imported_office/` 下对应子目录
2. 重新执行：

```bash
python scripts/ingest_kb.py
```

## 如何重新 ingest

只重建索引：

```bash
python scripts/ingest_kb.py
```

同时重置 mock 数据并重建索引：

```bash
python scripts/reset_demo_data.py
```

如果只是重新导入 Office 文件夹，不需要单独执行 `ingest_kb.py`，导入动作本身会自动重建索引。

## 如何调整召回参数

在 `.env` 中调整：

```env
RAG_TOP_K=4
RAG_FULL_TOP_K=6
CHUNK_SIZE=260
CHUNK_OVERLAP=50
RAG_PROFILE=light
RERANK_ENABLED=true
```

修改参数后建议重新 ingest，再重启后端。

## 如何关闭 RAG

方式 1：页面里关闭 `启用 RAG`

方式 2：`.env` 中设置：

```env
RAG_ENABLED=false
```

## 如何仅保留 tools

`.env` 设置：

```env
AGENT_MODE=only-tool
```

此时不会检索知识库，只会查表 + 规则回答。

## 如何替换文档目录

如果后续知识库目录不想放在默认位置，可在 `.env` 里改：

```env
KB_DIR=data/knowledge_base
IMPORTED_KB_DIR=data/knowledge_base/imported_office
INDEX_FILE=data/indexes/kb_index.json
IMPORT_MANIFEST_FILE=data/indexes/import_manifest.json
```

然后重新 ingest。

## 如何排查检索不准

优先按这个顺序看：

1. 文档是否真的放在 `data/knowledge_base/`
2. 如果是 Office 文件夹，是否执行过页面导入或 `python scripts/import_office_folder.py`
3. `http://127.0.0.1:8000/api/rag/documents` 里是否看得到新文档
4. `data/indexes/import_manifest.json` 里是否有导入记录
5. `RAG_ENABLED` 是否被关掉
6. `AGENT_MODE` 是否被改成 `only-tool`
7. `RAG_PROFILE` 是否还是 `light`
8. `CHUNK_SIZE` 是否过大，导致召回片段太粗
9. `RAG_TOP_K` 是否太小

## 替换 embedding / rerank 的代码入口

- 检索主逻辑：`apps/api/app/services/retriever.py`
- 配置入口：`.env.example`

当前默认：

- `EMBEDDING_PROVIDER=local-bow`
- `EMBEDDING_MODEL=token-frequency-v1`
- `RERANK_ENABLED=true`

如果后续接入真实 embedding 或 reranker，建议优先保持 `.env` 配置名不变，只扩展实现。
