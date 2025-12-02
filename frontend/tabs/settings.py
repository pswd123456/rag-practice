# frontend/tabs/settings.py
import streamlit as st
import api
import time

def render_settings_tab(selected_kb):
    role = selected_kb.get('role', 'VIEWER')
    st.info(f"当前身份: **{role}**")

    # ==========================================
    # 1. 基本信息 (EDITOR / OWNER 可见)
    # ==========================================
    if role in ['OWNER', 'EDITOR']:
        st.subheader("⚙️ 基本信息修改")
        with st.form("update_kb_form"):
            new_kb_name = st.text_input("名称", value=selected_kb['name'])
            new_kb_desc = st.text_input("描述", value=selected_kb['description'])
            
            # 只有 OWNER 能改重要配置吗？这里假设 EDITOR 也可以改描述
            if st.form_submit_button("💾 保存修改"):
                success, msg = api.update_knowledge(selected_kb['id'], new_kb_name, new_kb_desc)
                if success:
                    st.success("修改成功！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"修改失败: {msg}")
    else:
        st.subheader("⚙️ 基本信息")
        st.text(f"名称: {selected_kb['name']}")
        st.text(f"描述: {selected_kb['description']}")
        st.caption("您没有权限修改此知识库信息。")

    st.divider()

    # ==========================================
    # 2. 成员管理 (仅 OWNER 可见)
    # ==========================================
    if role == 'OWNER':
        st.subheader("👥 成员管理")
        
        # 2.1 邀请表单
        with st.expander("➕ 邀请新成员"):
            c1, c2, c3 = st.columns([3, 2, 1])
            new_email = c1.text_input("用户邮箱", placeholder="user@example.com")
            new_role = c2.selectbox("分配权限", ["EDITOR", "VIEWER"], index=1)
            if c3.button("邀请", type="primary", use_container_width=True):
                if new_email:
                    success, msg = api.add_member(selected_kb['id'], new_email, new_role)
                    if success:
                        st.success(f"已邀请 {new_email}")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
        
        # 2.2 成员列表
        members = api.get_members(selected_kb['id'])
        if members:
            st.markdown("#### 现有成员")
            for m in members:
                col_m1, col_m2, col_m3, col_m4 = st.columns([2, 2, 1, 1])
                col_m1.text(m['full_name'] or "Unknown")
                col_m2.caption(m['email'])
                
                # 角色徽章
                role_color = "red" if m['role'] == "OWNER" else ("blue" if m['role'] == "EDITOR" else "grey")
                col_m3.markdown(f":{role_color}[{m['role']}]")
                
                # 操作 (不能删除自己)
                if m['role'] != 'OWNER':
                    if col_m4.button("移除", key=f"rm_mem_{m['user_id']}"):
                        success, msg = api.remove_member(selected_kb['id'], m['user_id'])
                        if success:
                            st.toast(f"已移除成员 {m['email']}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(msg)
                else:
                    col_m4.caption("-")
                st.divider()

    # ==========================================
    # 3. 危险区域 (仅 OWNER 可见)
    # ==========================================
    if role == 'OWNER':
        st.subheader("⚠️ 危险区域")
        if "confirm_delete" not in st.session_state:
            st.session_state.confirm_delete = False
            
        if not st.session_state.confirm_delete:
            if st.button("🗑️ 删除此知识库", type="primary"):
                st.session_state.confirm_delete = True
                st.rerun()
        else:
            st.error(f"确定删除 {selected_kb['name']} 吗？此操作不可逆！")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                if st.button("✅ 确认删除"):
                    success, msg = api.delete_knowledge(selected_kb['id'])
                    if success:
                        st.success(msg)
                        st.session_state.confirm_delete = False
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
            with col_d2:
                if st.button("❌ 取消"):
                    st.session_state.confirm_delete = False
                    st.rerun()