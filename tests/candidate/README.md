# 共现候选冒烟

当前仅保留 general/频次筛选、PMI 与支持次数门槛、预算连续帧和离线导入的少量中性冒烟。旧可编辑 JSON 词库与槽位求解测试随实现移除。

在 Pictide 根目录按需运行相关文件，不运行完整回归：

```powershell
python -m unittest discover -s tests/candidate -p test_cooccurrence.py -v
python -m unittest discover -s tests -p test_cooccurrence_integration.py -v
```

样例使用临时 SQLite 和中性标签；集成使用模拟生图后端，不提交真实 GPU 任务。离线导入冒烟见[数据处理工具](../../docs/dev/corpus.md#验证)。浏览器与完整数据导入的实测记录放在 dev/verification/，不把模拟样例当作真实出图结论。
