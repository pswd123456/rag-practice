import streamlit as st
import time
from tabs import (
    render_sidebar, 
    render_chat_tab, 
    render_documents_tab, 
    render_evaluation_tab, 
    render_settings_tab
)
import api

# 1. 页面基础配置 (必须是第一个 Streamlit 命令)
st.set_page_config(page_title="RAG 知识库管理台", layout="wide", page_icon="🔐")

# --- Authentication Logic ---

def render_login_page():
    """
    渲染登录/注册页面
    """
    st.title("🔐 RAG Practice 登录")
    
    tab1, tab2 = st.tabs(["登录", "注册新账号"])
    
    with tab1:
        with st.form("login_form"):
            email = st.text_input("邮箱 (Email)", placeholder="admin@example.com")
            password = st.text_input("密码 (Password)", type="password")
            submitted = st.form_submit_button("登录", type="primary")
            
            if submitted:
                if not email or not password:
                    st.error("请输入账号和密码")
                else:
                    with st.spinner("正在验证..."):
                        success, res = api.login(email, password)
                        if success:
                            # 登录成功：保存 Token 并刷新
                            st.session_state["token"] = res["access_token"]
                            # 获取用户信息用于展示
                            user_info = api.get_current_user_info()
                            if user_info:
                                st.session_state["user_info"] = user_info
                            
                            st.success("登录成功！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error(f"登录失败: {res}")

    with tab2:
        st.caption("注册一个新账号以开始使用。")
        with st.form("register_form"):
            new_email = st.text_input("邮箱", key="reg_email")
            new_name = st.text_input("昵称 (可选)", key="reg_name")
            new_pass = st.text_input("密码", type="password", key="reg_pass")
            new_pass_confirm = st.text_input("确认密码", type="password", key="reg_pass2")
            reg_submit = st.form_submit_button("注册")
            
            if reg_submit:
                if new_pass != new_pass_confirm:
                    st.error("两次输入的密码不一致")
                elif not new_email or not new_pass:
                    st.error("邮箱和密码为必填项")
                else:
                    with st.spinner("正在注册..."):
                        success, res = api.register(new_email, new_pass, new_name)
                        if success:
                            st.success("注册成功！请切换到“登录”标签页进行登录。")
                        else:
                            st.error(f"注册失败: {res}")

def render_main_app():
    # --- Sidebar ---
    # 这里接收新的返回值: (selected_kb, current_session)
    selected_kb, current_session = render_sidebar()

    st.title("🗂️ RAG Practice 综合管理台")

    if selected_kb:
        if selected_kb.get("status") == "DELETING":
            st.warning(f"⚠️ 知识库「{selected_kb['name']}」正在后台异步删除中。")
            st.stop()

        # 渲染 Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["💬 对话检索", "📄 文档管理", "📊 评估实验", "⚙️ 设置"])

        with tab1:
            # 传入 current_session
            render_chat_tab(selected_kb, current_session)
        
        with tab2:
            render_documents_tab(selected_kb)
        
        with tab3:
            render_evaluation_tab(selected_kb)
            
        with tab4:
            render_settings_tab(selected_kb)

    else:
        st.markdown("👋 **欢迎使用 RAG 管理台**")
        st.markdown("请在左侧侧边栏 **新建** 或 **选择** 一个知识库以开始。")

if __name__ == "__main__":
    if "token" not in st.session_state or not st.session_state["token"]:
        render_login_page()
    else:
        render_main_app()