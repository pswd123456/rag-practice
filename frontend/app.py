import streamlit as st
import httpx
import pandas as pd
from datetime import datetime
import time

API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="RAG 知识库管理台", layout="wide", page_icon="🗂️")

st.title("🗂️ RAG Practice 综合管理台")

# ================== 核心逻辑函数 ==================
def get_knowledges():
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges")
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def get_documents(kb_id):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}/documents")
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def get_document_status(doc_id):
    """查询单个文档的状态"""
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/documents/{doc_id}")
        if res.status_code == 200:
            return res.json().get("status")
    except:
        pass
    return None

def delete_document(doc_id):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/documents/{doc_id}")
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

def delete_knowledge(kb_id):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}")
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

def update_knowledge(kb_id, name, desc):
    try:
        res = httpx.put(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}", json={
            "name": name, "description": desc
        })
        return res.status_code == 200, res.json()
    except Exception as e:
        return False, str(e)

# ================== 侧边栏：知识库导航 ==================
with st.sidebar:
    st.header("📚 知识库列表")
    
    # 1. 创建区
    with st.expander("➕ 新建知识库", expanded=False):
        new_name = st.text_input("名称 (Unique)", key="new_kb_name")
        new_desc = st.text_input("描述", key="new_kb_desc")
        if st.button("立即创建"):
            if new_name:
                res = httpx.post(f"{API_BASE_URL}/knowledge/knowledges", json={"name": new_name, "description": new_desc})
                if res.status_code == 200:
                    st.success("创建成功")
                    st.rerun()
                else:
                    st.error(res.text)

    st.divider()

    # 2. 列表区
    kb_list = get_knowledges()
    if not kb_list:
        st.info("暂无知识库，请先创建")
        selected_kb = None
    else:
        # --- 修改开始 ---
        # 构造显示名称，如果正在删除，加上醒目标记
        kb_options = {}
        for k in kb_list:
            display_name = k["name"]
            # 后端返回的 dict 里现在会有 "status" 字段
            if k.get("status") == "DELETING":
                display_name = f"🔴 {display_name} (删除中...)"
            
            kb_options[display_name] = k

        # 使用处理过的 key 作为选项
        selected_option = st.radio("选择知识库", list(kb_options.keys()))
        selected_kb = kb_options[selected_option]

# ================== 主界面：Tab 页签管理 ==================

if selected_kb:
    st.header(f"当前知识库: {selected_kb['name']}")
    st.caption(f"ID: {selected_kb['id']} | {selected_kb['description']}")

    # 使用 Tabs 分离功能，界面更清爽
    tab1, tab2, tab3 = st.tabs(["💬 对话检索", "📄 文档管理", "⚙️ 设置"])

    # ----------- Tab 1: 对话检索 (原功能) -----------
    with tab1:
        col_s1, col_s2 = st.columns([1, 4])
        with col_s1:
            strategy = st.selectbox("检索策略", ["default", "dense_only", "hybrid", "rerank"])
        
        # 初始化聊天
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        # 清空历史按钮
        if st.button("🧹 清空对话"):
            st.session_state.messages = []
            st.rerun()

        # 显示历史
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "sources" in msg and msg["sources"]:
                    with st.expander(f"📚 参考了 {len(msg['sources'])} 个切片"):
                        for idx, src in enumerate(msg["sources"]):
                            st.markdown(f"**[{idx+1}] {src['source_filename']}**")
                            st.caption(src['chunk_content'])

        # 输入框
        if prompt := st.chat_input("在这个知识库中搜索..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("思考中..."):
                    try:
                        payload = {
                            "query": prompt,
                            "knowledge_id": selected_kb['id'],
                            "strategy": strategy
                        }
                        res = httpx.post(f"{API_BASE_URL}/chat/query", json=payload, timeout=60.0)
                        if res.status_code == 200:
                            data = res.json()
                            st.markdown(data["answer"])
                            if data["sources"]:
                                with st.expander(f"📚 参考了 {len(data['sources'])} 个切片"):
                                    for idx, src in enumerate(data['sources']):
                                        st.markdown(f"**[{idx+1}] {src['source_filename']}**")
                                        st.caption(src['chunk_content'])
                            
                            # [FIX] 手动构造符合前端要求的字典
                            st.session_state.messages.append({
                                "role": "assistant",        # 补充 role
                                "content": data["answer"],  # 将 answer 映射为 content
                                "sources": data["sources"]  # 保留 sources
                            })
                        else:
                            st.error(res.text)
                    except Exception as e:
                        st.error(str(e))

    # ----------- Tab 2: 文档管理 (新增) -----------
    with tab2:
        # A. 上传区
        with st.container():
            st.subheader("📤 上传文件")
            uploaded_file = st.file_uploader("支持 PDF/TXT/MD", type=["pdf", "txt", "md"])
            if uploaded_file and st.button("开始上传", type="primary"):
                files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                
                # 1. 上传阶段
                with st.spinner("正在上传文件..."):
                    try:
                        res = httpx.post(f"{API_BASE_URL}/knowledge/{selected_kb['id']}/upload", files=files, timeout=60.0)
                        if res.status_code == 200:
                            doc_id = res.json() # 假设后端返回的是 int ID
                            st.toast(f"文件已上传 (ID: {doc_id})，开始后台处理...", icon="🚀")
                        else:
                            st.error(f"上传失败: {res.text}")
                            st.stop() # 停止后续执行
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.stop()

                # 2. 轮询阶段 (新增逻辑)
                # st.status 创建一个可折叠的状态框
                with st.status("正在解析与向量化...", expanded=True) as status:
                    st.write("Worker 正在努力工作中...")
                    
                    # 循环检查状态
                    while True:
                        current_status = get_document_status(doc_id)
                        
                        if current_status == "COMPLETED":
                            status.update(label="✅ 处理完成！", state="complete", expanded=False)
                            st.success(f"文档 {uploaded_file.name} 已成功入库！")
                            # 延迟 1 秒后刷新页面，让用户看清成功提示
                            time.sleep(1)
                            st.rerun()
                            break
                        
                        elif current_status == "FAILED":
                            status.update(label="❌ 处理失败", state="error", expanded=True)
                            st.error("后台处理发生错误，请检查 Worker 日志。")
                            break
                        
                        # 如果还在 PROCESSING 或 PENDING，等待 2 秒再查
                        time.sleep(2)

        st.divider()
        
        # B. 列表区
        st.subheader("📑 已收录文档")
        docs = get_documents(selected_kb['id'])
        
        if docs:
            # 表头
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.markdown("**文件名**")
            c2.markdown("**状态**")
            c3.markdown("**上传时间**")
            c4.markdown("**操作**")
            
            for doc in docs:
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                c1.text(doc['filename'])
                
                # 状态徽章
                status = doc['status']
                if status == "COMPLETED":
                    c2.success("✅ 完成")
                elif status == "FAILED":
                    c2.error("❌ 失败")
                else:
                    c2.warning(f"⏳ {status}")
                
                c3.text(doc['created_at'][:16].replace("T", " ")) # 简单格式化时间
                
                # 删除按钮 (使用 key 区分不同文档)
                if c4.button("🗑️", key=f"del_{doc['id']}", help="删除此文档"):
                    success, msg = delete_document(doc['id'])
                    if success:
                        st.toast(f"文档 {doc['filename']} 已删除")
                        # 延迟一点点刷新，让用户看到 toast
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                
                st.divider()
        else:
            st.info("当前知识库暂无文档。")

    # ----------- Tab 3: 知识库设置 (新增) -----------
    with tab3:
        st.subheader("⚙️ 基本信息修改")
        
        with st.form("update_kb_form"):
            new_kb_name = st.text_input("名称", value=selected_kb['name'])
            new_kb_desc = st.text_input("描述", value=selected_kb['description'])
            
            if st.form_submit_button("💾 保存修改"):
                success, msg = update_knowledge(selected_kb['id'], new_kb_name, new_kb_desc)
                if success:
                    st.success("修改成功！")
                    st.rerun()
                else:
                    st.error(f"修改失败: {msg}")
        
        st.divider()
        
        st.subheader("⚠️ 危险区域")
        st.warning("删除知识库将连带删除其下所有文档和向量数据，不可恢复！")
        
        # 二次确认逻辑
        if "confirm_delete" not in st.session_state:
            st.session_state.confirm_delete = False

        if not st.session_state.confirm_delete:
            if st.button("🗑️ 删除此知识库", type="primary"):
                st.session_state.confirm_delete = True
                st.rerun()
        else:
            st.error(f"你确定要删除 {selected_kb['name']} 吗？")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                if st.button("✅ 确认删除"):
                    success, msg = delete_knowledge(selected_kb['id'])
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

else:
    st.title("👋 欢迎使用 RAG 管理台")
    st.markdown("请在左侧新建或选择一个知识库开始。")