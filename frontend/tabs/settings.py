import streamlit as st
import api

def render_settings_tab(selected_kb):
    st.subheader("⚙️ 基本信息修改")
    with st.form("update_kb_form"):
        new_kb_name = st.text_input("名称", value=selected_kb['name'])
        new_kb_desc = st.text_input("描述", value=selected_kb['description'])
        if st.form_submit_button("💾 保存修改"):
            success, msg = api.update_knowledge(selected_kb['id'], new_kb_name, new_kb_desc)
            if success:
                st.success("修改成功！")
                st.rerun()
            else:
                st.error(f"修改失败: {msg}")
    st.divider()
    st.subheader("⚠️ 危险区域")
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False
    if not st.session_state.confirm_delete:
        if st.button("🗑️ 删除此知识库", type="primary"):
            st.session_state.confirm_delete = True
            st.rerun()
    else:
        st.error(f"确定删除 {selected_kb['name']} 吗？")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if st.button("✅ 确认"):
                success, msg = api.delete_knowledge(selected_kb['id'])
                if success:
                    st.success(msg)
                    st.session_state.confirm_delete = False
                    st.rerun()
                else:
                    st.error(msg)
        with col_d2:
            if st.button("❌ 取消"):
                st.session_state.confirm_delete = False
                st.rerun()