# Local Experiment Runner（后续阶段）

Runner 是 Web API 与真实计算实验之间的隔离边界。它不会在 Stage 0 中执行任何用户代码。

后续实现应提供类似下面的能力：

```text
validate_plan(spec)
estimate_resources(spec)
submit(spec) -> run_id
poll(run_id)
collect_artifacts(run_id)
verify_reproducibility(run_id)
```

首个适配器建议是受限 Docker Runner，要求：资源配额、超时、数据只读挂载、网络白名单、运行日志和产物哈希。物理实验设备适配器应在更后续阶段接入，并保留人工审批。
