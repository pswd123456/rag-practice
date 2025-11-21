import streamlit as st
import httpx
import pandas as pd
from datetime import datetime
import time

API_BASE_URL = "http://api:8000" # Docker 内部通信用服务名，如果你在宿主机跑 Streamlit 改为 localhost:8000

# 注意：如果 Streamlit 也在 Docker 里，这里用 api:8000
# 如果你在本地直接 python frontend/app.py 跑，这里要改成 http://localhost:8000
# 为了兼容，我们可以尝试自动检测或你可以手动改
try:
    # 简单探测一下，如果 localhost 通就不改，不通就切 api
    httpx.get("http://localhost:8000", timeout=1)
    API_BASE_URL = "http://localhost:8000"
except:
    API_BASE_URL = "http://api:8000"

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
        # [新增] 如果是 404，说明文档没了
        elif res.status_code == 404:
            return "NOT_FOUND"
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
        return res.status_code == 200 or res.status_code == 202, res.text
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

# --- 评估相关 ---
def get_testsets():
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets")
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def get_testset_status(ts_id):
    """
    [新增] 查询单个测试集的状态
    """
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets/{ts_id}")
        if res.status_code == 200:
            return res.json().get("status")
        elif res.status_code == 404:
            return "NOT_FOUND"
    except:
        pass
    return None

def create_testset(name, doc_ids):
    try:
        res = httpx.post(f"{API_BASE_URL}/evaluation/testsets", json={
            "name": name, "source_doc_ids": doc_ids
        })
        # 返回 ID (int) 或 错误文本
        if res.status_code == 200:
            return True, res.text 
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def get_experiments(kb_id):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments", params={"knowledge_id": kb_id})
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def run_experiment(kb_id, testset_id, params):
    try:
        payload = {
            "knowledge_id": kb_id,
            "testset_id": testset_id,
            "runtime_params": params
        }
        res = httpx.post(f"{API_BASE_URL}/evaluation/experiments", json=payload, timeout=10.0)
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

# ================== 侧边栏：知识库导航 ==================
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
                    try:
                        res = httpx.post(f"{API_BASE_URL}/knowledge/knowledges", json=payload)
                        if res.status_code == 200:
                            st.success("创建成功")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(res.text)
                    except Exception as e:
                        st.error(str(e))

    st.divider()

    # 2. 列表区
    kb_list = get_knowledges()
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


# ================== 主界面 ==================

if selected_kb:
    # 状态拦截
    if selected_kb.get("status") == "DELETING":
        st.warning(f"⚠️ 知识库「{selected_kb['name']}」正在后台异步删除中。")
        st.info("请稍等片刻，或点击左上角手动刷新以查看最新状态。")
        st.stop()

    st.header(f"当前知识库: {selected_kb['name']}")
    # 显示配置标签
    st.caption(f"ID: {selected_kb['id']} | Embed: `{selected_kb.get('embed_model')}` | Chunk: `{selected_kb.get('chunk_size')}`")

    tab1, tab2, tab3, tab4 = st.tabs(["💬 对话检索", "📄 文档管理", "📊 评估实验", "⚙️ 设置"])

    # ----------- Tab 1: 对话检索 -----------
    with tab1:
        col_s1, col_s2 = st.columns([1, 4])
        with col_s1:
            strategy = st.selectbox("检索策略", ["default", "dense_only", "hybrid", "rerank"])
        
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        if st.button("🧹 清空对话"):
            st.session_state.messages = []
            st.rerun()

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "sources" in msg and msg["sources"]:
                    with st.expander(f"📚 参考了 {len(msg['sources'])} 个切片"):
                        for idx, src in enumerate(msg["sources"]):
                            st.markdown(f"**[{idx+1}] {src['source_filename']}**")
                            st.caption(src['chunk_content'])

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
                            
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": data["answer"],
                                "sources": data["sources"]
                            })
                        else:
                            st.error(res.text)
                    except Exception as e:
                        st.error(str(e))

    # ----------- Tab 2: 文档管理 -----------
    with tab2:
        with st.container():
            st.subheader("📤 上传文件")
            uploaded_file = st.file_uploader("支持 PDF/TXT/MD", type=["pdf", "txt", "md"])
            if uploaded_file and st.button("开始上传", type="primary"):
                files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                with st.spinner("正在上传文件..."):
                    try:
                        res = httpx.post(f"{API_BASE_URL}/knowledge/{selected_kb['id']}/upload", files=files, timeout=60.0)
                        if res.status_code == 200:
                            doc_id = res.json()
                            st.toast(f"文件已上传 (ID: {doc_id})，开始后台处理...", icon="🚀")
                        else:
                            st.error(f"上传失败: {res.text}")
                            st.stop()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        st.stop()

                with st.status("正在解析与向量化...", expanded=True) as status:
                    st.write("Worker 正在努力工作中...")
                    
                    # 循环检查状态
                    while True:
                        current_status = get_document_status(doc_id)
                        
                        if current_status == "COMPLETED":
                            status.update(label="✅ 处理完成！", state="complete", expanded=False)
                            st.success(f"文档 {uploaded_file.name} 已成功入库！")
                            time.sleep(1)
                            st.rerun()
                            break
                        
                        elif current_status == "FAILED":
                            status.update(label="❌ 处理失败", state="error", expanded=True)
                            st.error("后台处理发生错误，请检查 Worker 日志。")
                            break
                        
                        elif current_status == "NOT_FOUND":
                            status.update(label="⚠️ 文档丢失", state="error", expanded=True)
                            st.error(f"文档 {doc_id} 未找到，可能已被删除或数据库已重置。")
                            break
                        
                        # 如果还在 PROCESSING 或 PENDING，等待 2 秒再查
                        time.sleep(2)

        st.divider()
        
        st.subheader("📑 已收录文档")
        docs = get_documents(selected_kb['id'])
        if docs:
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            c1.markdown("**文件名**")
            c2.markdown("**状态**")
            c3.markdown("**上传时间**")
            c4.markdown("**操作**")
            for doc in docs:
                c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
                c1.text(doc['filename'])
                status = doc['status']
                if status == "COMPLETED":
                    c2.success("✅ 完成")
                elif status == "FAILED":
                    c2.error("❌ 失败")
                else:
                    c2.warning(f"⏳ {status}")
                c3.text(doc['created_at'][:16].replace("T", " "))
                if c4.button("🗑️", key=f"del_{doc['id']}", help="删除此文档"):
                    success, msg = delete_document(doc['id'])
                    if success:
                        st.toast(f"文档 {doc['filename']} 已删除")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(msg)
                st.divider()
        else:
            st.info("当前知识库暂无文档。")

    # ----------- Tab 3: 评估实验 -----------
    with tab3:
        st.caption("在此处管理测试集并运行对比实验。")
        eval_tab1, eval_tab2 = st.tabs(["🧪 实验看板", "📝 测试集管理"])
        
        # === 子标签 1: 实验看板 ===
        with eval_tab1:
            col_e1, col_e2 = st.columns([1, 3])
            with col_e1:
                st.subheader("🚀 发起新实验")
                testsets = get_testsets()
                # [新增] 过滤：只保留 COMPLETED 的测试集
                ready_testsets = [ts for ts in testsets if ts.get('status') == 'COMPLETED']
                
                if not ready_testsets:
                    if testsets:
                        st.warning("有测试集正在生成中，请稍候...")
                    else:
                        st.warning("请先在“测试集管理”中生成测试集")
                else:
                    with st.form("run_exp_form"):
                        # [修改] 使用过滤后的列表
                        ts_options = {f"{ts['name']} (ID:{ts['id']})": ts['id'] for ts in ready_testsets}
                        selected_ts_name = st.selectbox("选择测试集", list(ts_options.keys()))
                        
                        if selected_ts_name:
                            selected_ts_id = ts_options[selected_ts_name]
                        else:
                             selected_ts_id = None

                        st.markdown("**运行时参数**")
                        exp_top_k = st.slider("Top K", 1, 10, 3)
                        exp_strategy = st.selectbox("检索策略", ["default", "hybrid", "rerank"])
                        exp_llm = st.selectbox("学生 LLM", ["qwen-flash", "qwen-turbo", "qwen-plus"])
                        
                        if st.form_submit_button("开始评估", type="primary"):
                            if selected_ts_id:
                                params = {"top_k": exp_top_k, "strategy": exp_strategy, "llm": exp_llm}
                                success, msg = run_experiment(selected_kb['id'], selected_ts_id, params)
                                if success:
                                    st.toast("实验已提交后台运行！", icon="🏃")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(msg)
                            else:
                                st.error("请选择一个有效的测试集")
            
            with col_e2:
                st.subheader("📈 历史实验记录")
                experiments = get_experiments(selected_kb['id'])
                if experiments:
                    # 转为 DataFrame 展示
                    data = []
                    for exp in experiments:
                        params = exp.get("runtime_params", {}) or {}
                        data.append({
                            "ID": exp["id"],
                            "状态": exp["status"],
                            # [修改] 使用全称，并补全 Context Precision
                            "Faithfulness": round(exp.get("faithfulness", 0), 3),
                            "Answer Relevancy": round(exp.get("answer_relevancy", 0), 3),
                            "Context Recall": round(exp.get("context_recall", 0), 3),
                            "Context Precision": round(exp.get("context_precision", 0), 3),
                            # 参数列
                            "TopK": params.get("top_k"),
                            "Strategy": params.get("strategy"),
                            "LLM": params.get("llm"),
                            "时间": exp["created_at"][:16].replace("T", " ")
                        })
                    
                    df = pd.DataFrame(data)
                    
                    # [修改] 配置 4 个指标的进度条和全名标签
                    st.dataframe(
                        df, 
                        use_container_width=True,
                        column_config={
                            "Faithfulness": st.column_config.ProgressColumn(
                                "Faithfulness (忠实度)", 
                                help="答案是否忠实于上下文",
                                min_value=0, max_value=1, format="%.3f"
                            ),
                            "Answer Relevancy": st.column_config.ProgressColumn(
                                "Answer Relevancy (回答相关性)", 
                                help="回答是否直接回应了问题",
                                min_value=0, max_value=1, format="%.3f"
                            ),
                            "Context Recall": st.column_config.ProgressColumn(
                                "Context Recall (上下文召回率)", 
                                help="检索到的上下文是否包含所有必要信息",
                                min_value=0, max_value=1, format="%.3f"
                            ),
                            "Context Precision": st.column_config.ProgressColumn(
                                "Context Precision (上下文精度)", 
                                help="检索到的上下文中有多少是真正有用的",
                                min_value=0, max_value=1, format="%.3f"
                            ),
                        }
                    )
                    
                    if st.button("🔄 刷新列表"):
                        st.rerun()
                else:
                    st.info("当前知识库暂无实验记录。")

        # === 子标签 2: 测试集管理 ===
        with eval_tab2:
            st.info("基于当前知识库的文档生成测试集。")
            with st.expander("✨ 生成新测试集", expanded=True):
                current_docs = get_documents(selected_kb['id'])
                if not current_docs:
                    st.error("当前知识库没有文档，无法生成。")
                else:
                    with st.form("create_testset_form"):
                        ts_name = st.text_input("测试集名称", placeholder="例如: 2024财报-困难模式")
                        doc_options = {d['filename']: d['id'] for d in current_docs}
                        selected_docs = st.multiselect("选择源文档", list(doc_options.keys()))
                        selected_doc_ids = [doc_options[name] for name in selected_docs]
                        
                        if st.form_submit_button("提交生成任务"):
                            if not ts_name or not selected_doc_ids:
                                st.error("请填写名称并选择文档。")
                            else:
                                success, msg = create_testset(ts_name, selected_doc_ids)
                                if success:
                                    # msg 是返回的 ID (字符串)
                                    ts_id = msg
                                    st.toast(f"任务已提交 (ID: {ts_id})，开始生成...", icon="🚀")
                                    
                                    # [新增] 轮询逻辑
                                    with st.status("正在生成测试集 (这可能需要几分钟)...", expanded=True) as status:
                                        while True:
                                            ts_status = get_testset_status(ts_id)
                                            
                                            if ts_status == "COMPLETED":
                                                status.update(label="✅ 生成完成！", state="complete", expanded=False)
                                                st.success(f"测试集 {ts_name} 生成成功！")
                                                time.sleep(1)
                                                st.rerun()
                                                break
                                            
                                            elif ts_status == "FAILED":
                                                status.update(label="❌ 生成失败", state="error", expanded=True)
                                                st.error("后台任务失败，请查看列表中的错误详情。")
                                                break
                                            
                                            elif ts_status == "NOT_FOUND":
                                                status.update(label="⚠️ 未找到", state="error", expanded=True)
                                                st.error("测试集ID未找到。")
                                                break
                                            
                                            # 还在 GENERATING，等待 2s
                                            time.sleep(2)
                                else:
                                    st.error(msg)
            # B. 列表区
            st.divider()
            st.subheader("📚 已有测试集")
            ts_list = get_testsets()
            if ts_list:
                for ts in ts_list:
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.markdown(f"**{ts['name']}** (ID: {ts['id']})")
                        st.caption(f"路径: `{ts['file_path']}`")
                    with col2:
                        # [新增] 状态徽章
                        status = ts.get('status', 'COMPLETED') # 兼容旧数据
                        if status == 'COMPLETED':
                            st.success("✅ 就绪")
                        elif status == 'FAILED':
                            st.error(f"❌ 失败: {ts.get('error_message')}")
                        elif status == 'GENERATING':
                            st.warning("⏳ 生成中...")
                        else:
                            st.info(status)
                    with col3:
                        st.caption(ts['created_at'][:10])
                    st.divider()

    # ----------- Tab 4: 设置 -----------
    with tab4:
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