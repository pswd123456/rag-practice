import streamlit as st
from tabs import (
    render_sidebar, 
    render_chat_tab, 
    render_documents_tab, 
    render_evaluation_tab, 
    render_settings_tab
)

# 1. 页面基础配置
st.set_page_config(page_title="RAG 知识库管理台", layout="wide", page_icon="🗂️")
st.title("🗂️ RAG Practice 综合管理台")

# 2. 渲染侧边栏并获取选中的知识库
selected_kb = render_sidebar()

# 3. 渲染主界面
if selected_kb:
    # 状态拦截: 如果知识库正在删除中，阻止操作
    if selected_kb.get("status") == "DELETING":
        st.warning(f"⚠️ 知识库「{selected_kb['name']}」正在后台异步删除中。")
        st.info("请稍等片刻，或点击左上角手动刷新以查看最新状态。")
        st.stop()

    st.header(f"当前知识库: {selected_kb['name']}")
    st.caption(f"ID: {selected_kb['id']} | Embed: `{selected_kb.get('embed_model')}` | Chunk: `{selected_kb.get('chunk_size')}`")

    # 4. 创建 Tabs 并分发渲染逻辑
    tab1, tab2, tab3, tab4 = st.tabs(["💬 对话检索", "📄 文档管理", "📊 评估实验", "⚙️ 设置"])

    with tab1:
        render_chat_tab(selected_kb)
    
    with tab2:
        render_documents_tab(selected_kb)
    
    with tab3:
        render_evaluation_tab(selected_kb)
        
    with tab4:
        render_settings_tab(selected_kb)

else:
    st.markdown("👋 **欢迎使用 RAG 管理台**")
    st.markdown("请在左侧侧边栏 **新建** 或 **选择** 一个知识库以开始。")