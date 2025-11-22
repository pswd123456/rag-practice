import matplotlib.pyplot as plt
import numpy as np

def plot_radar_chart(metrics_dict):
    """
    绘制 RAGAS 指标雷达图
    metrics_dict: {'Faithfulness': 0.8, 'Relevancy': 0.7, ...}
    """
    # 准备数据
    labels = list(metrics_dict.keys())
    stats = list(metrics_dict.values())
    
    # 闭合圆环
    stats = np.concatenate((stats,[stats[0]]))
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False)
    angles = np.concatenate((angles,[angles[0]]))

    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw=dict(polar=True))
    ax.fill(angles, stats, color='skyblue', alpha=0.25)
    ax.plot(angles, stats, color='skyblue', linewidth=2)
    
    ax.set_yticklabels([])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=10)
    ax.set_ylim(0, 1)
    plt.title("Ragas Metrics", size=12, y=1.1)
    return fig