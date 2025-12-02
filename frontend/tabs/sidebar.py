# frontend/tabs/sidebar.py
import streamlit as st
import time
import api

def render_sidebar():
    """
    渲染侧边栏，返回:
    - selected_kb: 当前选中的知识库对象
    - current_session: 当前选中的会话对象 (可能为 None)
    """
    with st.sidebar:
        st.header("📚 知识库与会话")
        
        # ==========================================
        # 1. 知识库选择区
        # ==========================================
        kb_list = api.get_knowledges()
        selected_kb = None
        
        if not kb_list:
            st.info("暂无知识库")
        else:
            # 使用 selectbox 节省空间
            kb_options = {k["name"]: k for k in kb_list}
            kb_name = st.selectbox("当前知识库", list(kb_options.keys()))
            selected_kb = kb_options[kb_name]
            
            if selected_kb.get("status") == "DELETING":
                st.warning("🔴 此知识库正在删除中...")

        with st.expander("➕ 新建知识库"):
            with st.form("create_kb_form"):
                new_name = st.text_input("名称", key="new_kb_name")
                new_desc = st.text_input("描述", key="new_kb_desc")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    new_embed = st.selectbox("Embedding", ["text-embedding-v4", "text-embedding-v3"])
                with col_c2:
                    new_chunk_size = st.number_input("Chunk Size", value=500, step=100)
                
                if st.form_submit_button("创建"):
                    if new_name:
                        payload = {
                            "name": new_name, "description": new_desc,
                            "embed_model": new_embed, "chunk_size": new_chunk_size
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

        # ==========================================
        # 2. 会话管理区 (依赖选中的 KB)
        # ==========================================
        current_session = None
        
        if selected_kb:
            st.subheader("💬 会话列表")
            
            # 获取所有会话
            all_sessions = api.get_sessions()
            # 过滤出属于当前 KB 的会话
            kb_sessions = [s for s in all_sessions if s["knowledge_id"] == selected_kb["id"]]
            
            # 新建会话按钮
            if st.button("➕ 新对话", use_container_width=True):
                success, res = api.create_session(selected_kb["id"], title="新对话")
                if success:
                    st.session_state["active_session_id"] = res["id"] # 自动选中新建的
                    st.rerun()
                else:
                    st.error(f"创建失败: {res}")
            
            # 会话列表渲染
            if not kb_sessions:
                st.caption("暂无历史会话")
            else:
                # 确保 session_state 中有 active_session_id
                if "active_session_id" not in st.session_state:
                    st.session_state["active_session_id"] = kb_sessions[0]["id"]
                
                # 检查 active_session_id 是否还在当前列表中 (可能切换了KB)
                active_id = st.session_state["active_session_id"]
                if not any(s["id"] == active_id for s in kb_sessions):
                    active_id = kb_sessions[0]["id"]
                    st.session_state["active_session_id"] = active_id
                
                # 渲染单选列表 (用 Radio 或 Button 模拟)
                # 为了美观，这里用 Radio
                session_options = {s["id"]: f"{s['title'][:15]}" for s in kb_sessions}
                
                # 为了让Radio默认选中，我们需要找到 label
                # 反向查找 label
                active_label = session_options.get(active_id)
                
                selected_label = st.radio(
                    "历史记录", 
                    list(session_options.values()),
                    index=list(session_options.values()).index(active_label) if active_label in session_options.values() else 0,
                    label_visibility="collapsed"
                )
                
                # 根据 Label 找回 ID
                # (这里可能有同名 Title 的风险，生产环境建议自定义 Component 或用 key 区分)
                # 简单做法：遍历 map
                selected_id = next((k for k, v in session_options.items() if v == selected_label), None)
                
                if selected_id:
                    st.session_state["active_session_id"] = selected_id
                    # 找到对应的 session 对象
                    current_session = next((s for s in kb_sessions if s["id"] == selected_id), None)
                    
                    # 删除会话按钮
                    if st.button("🗑️ 删除当前会话", key=f"del_sess_{selected_id}"):
                        api.delete_session(selected_id)
                        st.session_state.pop("active_session_id", None)
                        st.rerun()

        return selected_kb, current_session