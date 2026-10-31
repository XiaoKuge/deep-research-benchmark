# 16: 按登录后的真实调用修正 Google（agy）的调用方式

**What to build:** 15 号是在 agy 未登录时按帮助信息写的；登录后主会话做了几次真实调用（2026 年 10 月 31 日，模型 gemini-4-argon-low），查明以下事实，据此修正模型调用层里 google 一家，使它能真正用于"只给材料"一档，并在说明里如实写明。

已确认的事实：
1. `-p` 必须带值。提示词不能放命令行，要走流式输入：参数 `--input-format stream-json --output-format stream-json ... -p ""`（-p 给空串；用流式输入时命令行上给了提示词会报错退出）；标准输入写一行 JSON：`{"event":"user","message":{"role":"user","content":"提示词全文"}}`，后跟换行。字段名错了会报 `missing the "event" field` 或 `missing the "message" field`。
2. 输出事件的字段名是 `event`（不是 `type`），内容嵌在同名键里：`{"event":"init","init":{"model":…,"cwd":…,"tools":[…]}}`；`{"event":"step_update","step_update":{"step_index":…,"state":"ACTIVE|DONE","step_type":"user_input|agent_response|…","usage":{…}}}`；`{"event":"result","result":{"status":"SUCCESS|ERROR","response":"…","error":"…","num_turns":…,"usage":{…}}}`。
3. 启动事件里的 `tools` 是 agy 注册过的全部 60 个工具，无论用不用自定义智能体都一样，**不代表这个智能体能用的工具**，不能拿来核实工具限定。
4. 自定义智能体文件（`.agents/agents/<名字>/agent.md`，现有写法）是生效的：只给材料一档被要求读网页时回答"没有工具。"，输入词元 442（不用智能体文件时是 6926）。
5. 只读网页一档：被要求读网页时，`result.status` 为 SUCCESS 但 `response` 为空字符串（读取网页需要人批准，非交互运行被拒）。目前 google 不能用于只读网页一档。
6. agy 能用的模型不只 Gemini，还有 claude-opus-5-5-*、claude-sonnet-5-5-*、gpt-oss-120b-medium。用 agy 当"Google 评委"时必须是 Gemini 模型。

**Blocked by:** 15（已完成）

**Status:** resolved

- [x] 提示词按事实 1 走流式输入，参数含 `--input-format stream-json` 和空的 `-p`（有测试，假 agy 检查收到的参数和标准输入那一行 JSON）
- [x] 按事实 2 解析：回答取 `result.response`；`result.status` 不是 SUCCESS 时失败并带上 `result.error`；回答为空时失败（有测试）
- [x] 不再用启动事件的工具列表核实限定；改为：只给材料一档出现 user_input、agent_response 以外的步骤类型就判失败，并在原因里列出步骤类型（有测试）
- [x] 不指定模型时默认用 gemini-4-argon-medium；启动事件报告的模型不是以 gemini 开头就判失败（有测试）
- [x] 删掉按猜测写的 denied_actions、finished_reason 判断，以及"待登录后确认"的说法；说明的 google 一节改写为上面的事实（已用真实调用确认的日期、只读网页一档暂不可用、会话会被保存且关不掉、不用 --settings 和跳过权限确认的理由）
- [x] 其余三家的行为和测试不变；全部测试通过
