# AGENTS.md

## 本项目目标

本项目是一个“产品 demo 级”的单 Agent 应用，用于演示厂内物流异常处理场景中的：

- 异常分类
- RAG 检索
- 本地查表 tools
- 草稿动作生成
- 人工确认

目标不是做复杂平台，而是保证：

- 结构清晰
- mock mode 可跑
- README 和 docs 完整
- 后续方便替换模型、prompt、知识库和业务场景

## 目录约定

- `apps/api/`：FastAPI 后端
- `apps/web/`：前端源码与内置 demo UI
- `data/knowledge_base/`：RAG 文档
- `data/mock_tables/`：CSV / JSON mock 表
- `data/eval_cases/`：评测样例
- `docs/`：产品和调优文档
- `prompts/`：system / policy / style prompt
- `scripts/`：重置 demo 数据、重建索引、跑评测

## 改代码时的原则

1. 优先保证 mock/demo 运行能力，不要因为接真实模型破坏本地可跑。
2. 优先保证 README、docs 和实际实现一致。
3. 优先做单 Agent + 多 tools，不要默认扩展成复杂多 Agent。
4. 新增配置优先放 `.env.example`，不要写死在代码里。
5. 涉及敏感动作时，不要改成自动执行，默认保持“草稿 + 人工确认”。

## 新增 skill 的方式

1. 先判断是不是一个独立工具能力
2. 如果是，优先在 `apps/api/app/services/` 新增单一职责模块
3. 在 `docs/tool-spec.md` 补充输入/输出/失败情况/敏感性
4. 必要时补 `data/mock_tables/` 或 `data/knowledge_base/`
5. 更新 README 的“如何扩展”部分

## 新增业务场景的方式

要切业务场景时，优先按这个顺序改：

1. `prompts/`
2. `data/knowledge_base/`
3. `data/mock_tables/`
4. `docs/PRD.md`
5. `docs/tool-spec.md`
6. `apps/api/app/services/classifier.py`
7. `apps/api/app/services/drafts.py`

## 不要破坏 mock/demo 运行能力

- 即使没有 API Key，也必须能启动后端和页面
- 即使真实模型不可用，也要 fallback 到本地 mock 回答
- 即使 RAG 关闭，也要保留 only-tool 路径

## 文档更新原则

每次改动后优先检查这些文件是否需要同步更新：

- `README.md`
- `docs/PRD.md`
- `docs/user-flow.md`
- `docs/tool-spec.md`
- `docs/rag-guide.md`
- `docs/tuning-guide.md`
