import streamlit as st
import time
import api

def render_sidebar():
    """
    渲染侧边栏，返回当前选中的知识库对象 (dict) 或 None
    """
    with st.sidebar:
        st.header("📚 知识库列表")
        
        # 1. 创建区
        with st.expander("➕ 新建知识库", expanded=False):
            with st.form("create_kb_form"):
                new_name = st.text_input("名称 (Unique)", key="new_kb_name")
                new_desc = st.text_input("描述", key="new_kb_desc")
                
                st.caption("🔧 构建配置 (创建后不可修改)")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    new_embed = st.selectbox("Embedding", ["text-embedding-v4", "text-embedding-v3"])
                with col_c2:
                    new_chunk_size = st.number_input("Chunk Size", value=500, step=100)
                    new_overlap = st.number_input("Overlap", value=50)
                
                if st.form_submit_button("立即创建"):
                    if new_name:
                        payload = {
                            "name": new_name, "description": new_desc,
                            "embed_model": new_embed,
                            "chunk_size": new_chunk_size,
                            "chunk_overlap": new_overlap
                        }
                        success, msg = api.create_knowledge(payload)
                        if success:
                            st.success("创建成功")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.error("名称不能为空")

        st.divider()

        # 2. 列表区
        kb_list = api.get_knowledges()
        if not kb_list:
            st.info("暂无知识库，请先创建")
            selected_kb = None
        else:
            kb_options = {}
            for k in kb_list:
                display_name = k["name"]
                if k.get("status") == "DELETING":
                    display_name = f"🔴 {display_name} (删除中...)"
                kb_options[display_name] = k

            selected_option = st.radio("选择知识库", list(kb_options.keys()))
            selected_kb = kb_options[selected_option]
            
        return selected_kb