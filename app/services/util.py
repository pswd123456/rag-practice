# -*- coding: utf-8 -*-
"""
工具模块 (util.py)

负责配置和初始化项目所需的所有核心组件，
包括 LLM、Embedding 模型、文本分割器、PDF 加载器和向量数据库。
同时也负责管理路径和环境变量。
"""
from dotenv import load_dotenv
import logging
logger = logging.getLogger(__name__)




