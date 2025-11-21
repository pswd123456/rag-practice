# 实验日志 (Experiment Log)

记录每一次 RAG 优化的策略变更及其对 Ragas 指标的影响。

## 📊 实验汇总表

|ID|日期|实验名称/变更点|Faithfulness|Answer Relevancy|Context Recall|Context Precision|结论/备注|
|---|---|---|---|---|---|---|---|
|Exp-001|2025-11-20|Baseline (Naive RAG, TopK=3)|0.75|0.82|0.60|0.70|初始基线，召回率较低|
|Exp-002|2025-11-21|增大 Chunk Size (512 -> 1024)|0.78|0.85|0.75|0.65|Recall 提升，但 Precision 下降（噪音变多）|
|||||||||

## 📝 详细实验记录

### Exp-001: Baseline

- **Commit ID**: `init`
    
- **配置**:
    
    - Embedding: `text-embedding-v4`
        
    - LLM: `qwen-flash`
        
    - Chunk Size: 512, Overlap: 50
        
    - Top K: 3
        
    - Strategy: `default` (Dense Only)
        
- **分析**:
    
    - 对于简单的事实性问题回答尚可。
        
    - 对于跨段落的复杂问题，往往找不到完整的上下文。
        

### Exp-002: 增大 Chunk Size

- **变更**: 将切片大小从 512 增加到 1024。
    
- **假设**: 更大的切片能包含更完整的上下文，提升 Recall。
    
- **结果**:
    
    - Context Recall 显著提升 (+0.15)。
        
    - Context Precision 略有下降，因为检索回来的大段文本中包含了更多无关信息。
        
- **下一步计划**: 尝试引入 Rerank 模型来清洗无关内容，提升 Precision。