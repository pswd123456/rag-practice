# 使用官方 Elasticsearch 8.17.0 镜像作为基础
# 注意：8.9+ 版本是使用 RRF (混合检索核心特性) 的最低要求
FROM elasticsearch:8.17.0

# 设置非交互前端，防止安装插件时卡住
ENV DEBIAN_FRONTEND=noninteractive

# 安装 analysis-ik 中文分词插件
# 修改说明：已切换下载源至 Infinilabs 官方 release 站点
RUN bin/elasticsearch-plugin install --batch https://release.infinilabs.com/analysis-ik/stable/elasticsearch-analysis-ik-8.17.0.zip

# (可选) 如果你需要安装其他插件，如拼音插件，建议也切换到对应的 release 站点
# RUN bin/elasticsearch-plugin install --batch https://release.infinilabs.com/analysis-pinyin/stable/elasticsearch-analysis-pinyin-8.17.0.zip