# 调优指南

## 先讲结论

对 demo 和大多数产品验证，优先做：

- prompt tuning
- retrieval tuning
- tool policy tuning

不要一上来就做训练式微调。

## 1. 修改 system prompt

文件：

- `prompts/system_prompt.md`

适合改什么：

- Agent 角色
- 能做什么 / 不能做什么
- 输出结构
- 风险边界

## 2. 调整工具策略

文件：

- `prompts/tool_policies.md`

当前文件里有一段 JSON 配置块，适合调整：

- `confirm_keywords`
- `high_risk_keywords`
- `always_consider_tools_for`
- `sensitive_action_types`

这类修改适合做“非训练式微调”。

## 3. 调整输出格式

文件：

- `prompts/response_style.md`

当前可调：

- 语气
- 步骤数
- 输出 section 顺序

## 4. 调整高风险动作策略

优先改两处：

- `prompts/tool_policies.md`
- `apps/api/app/services/drafts.py`

如果只是改阈值和关键词，先改 prompt/policy。
如果是要改动作逻辑，再改 Python 代码。

## 5. 切换模型

当前项目默认推荐本地模型配置：

- `Ollama`
- `qwen3.5:9b`

说明：

- 截至 `2026-03-23`，Ollama 官方 `qwen3.5` 页面公开 tag 不包含 `14b`，默认 `latest` 指向 `qwen3.5:9b`。
- 如果你本机已经有自定义的 `qwen3.5:14b`，直接改 `.env` 的 `LLM_MODEL` 即可，不需要改代码。

通过 `.env`：

```env
MOCK_MODE=false
LLM_PROVIDER=openai-compatible
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_MODEL=qwen3.5:9b
LLM_API_KEY=ollama
LLM_REASONING_EFFORT=none
LLM_MAX_TOKENS=480
```

建议先执行：

```bash
ollama pull qwen3.5:9b
ollama serve
```

模型调用入口：

- `apps/api/app/services/llm_client.py`

补充说明：

- 如果接的是 Qwen 这类带 reasoning / thinking 能力的模型，建议默认把 `LLM_REASONING_EFFORT` 设为 `none`
- 如果前端长时间停在“思考中”，优先检查 `LLM_MAX_TOKENS` 是否缺失或设置过大

## 6. 未来接入微调模型

建议保持接口不变：

- 仍通过 `.env` 控制 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL`
- 在 `llm_client.py` 中扩展 provider
- 在 `data/training/` 放训练样本

## 7. 区分三类调优

### Prompt tuning

改提示词、风格、边界、输出格式。

适合：

- demo 演示
- 回答风格统一
- 风险提示更强

### Retrieval tuning

改知识库、chunk、top_k、rerank 和召回规则。

适合：

- 回答没引用
- 引用不准
- SOP 命中率低

### Training fine-tuning

改模型参数，让模型更擅长特定任务。

适合：

- 异常分类稳定性
- 字段抽取一致性
- 固定模板生成

不适合：

- 最新知识问答
- 私有文档事实检索
- 高频变更规则
