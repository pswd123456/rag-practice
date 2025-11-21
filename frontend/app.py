import streamlit as st
import httpx
import pandas as pd
from datetime import datetime
import time
import matplotlib.pyplot as plt
import numpy as np
import json

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

# ================== 辅助绘图函数 ==================
def plot_radar_chart(metrics_dict):
    """
    绘制 RAGAS 指标雷达图
    metrics_dict: {'Faithfulness': 0.8, 'Relevancy': 0.7, ...}
    """
    # 准备数据
    labels = list(metrics_dict.keys())
    stats = list(metrics_dict.values())
    
    # 闭合圆环
    stats = np.concatenate((stats,[stats[0]]))
    angles = np.linspace(0, 2*np.pi, len(labels), endpoint=False)
    angles = np.concatenate((angles,[angles[0]]))

    fig, ax = plt.subplots(figsize=(4, 4), subplot_kw=dict(polar=True))
    ax.fill(angles, stats, color='skyblue', alpha=0.25)
    ax.plot(angles, stats, color='skyblue', linewidth=2)
    
    ax.set_yticklabels([])
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=10)
    ax.set_ylim(0, 1)
    plt.title("Ragas Metrics", size=12, y=1.1)
    return fig

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

def delete_testset(ts_id):
    """[新增] 删除测试集"""
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/testsets/{ts_id}")
        return res.status_code == 200, res.text
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

def get_experiment_detail(exp_id):
    """[新增] 获取实验详情"""
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments/{exp_id}")
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return None

def run_experiment(kb_id, testset_id, params):
    try:
        payload = {
            "knowledge_id": kb_id,
            "testset_id": testset_id,
            "runtime_params": params
        }
        res = httpx.post(f"{API_BASE_URL}/evaluation/experiments", json=payload, timeout=10.0)
        # [修改] 成功时返回 (True, experiment_id)，失败返回 (False, error_msg)
        if res.status_code == 200:
            return True, res.json() # 这里直接返回 ID (int)
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def delete_experiment(exp_id):
    """[新增] 删除实验"""
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/experiments/{exp_id}")
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
            use_stream = st.checkbox("流式输出", value=True)
        
        if "messages" not in st.session_state:
            st.session_state.messages = []
            
        if st.button("🧹 清空对话"):
            st.session_state.messages = []
            st.rerun()

        # 1. 渲染历史消息
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if "sources" in msg and msg["sources"]:
                    with st.expander(f"📚 参考了 {len(msg['sources'])} 个切片"):
                        for idx, src in enumerate(msg["sources"]):
                            # 历史消息渲染时也加上页码逻辑
                            page_num = src.get("page_number")
                            page_info = f" (P{page_num})" if page_num else ""
                            st.markdown(f"**[{idx+1}] {src['source_filename']}{page_info}**")
                            st.caption(src['chunk_content'])

        # 2. 处理用户输入
        if prompt := st.chat_input("在这个知识库中搜索..."):
            # 显示用户消息
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # 显示助手响应
            with st.chat_message("assistant"):
                payload = {
                    "query": prompt,
                    "knowledge_id": selected_kb['id'],
                    "strategy": strategy
                }
                
                full_response = ""
                retrieved_sources = []

                # ================= A. 流式模式 =================
                if use_stream:
                    # 仅在流式模式下创建占位符
                    message_placeholder = st.empty()
                    
                    try:
                        with httpx.Client(timeout=60.0) as client:
                            with client.stream("POST", f"{API_BASE_URL}/chat/stream", json=payload) as response:
                                if response.status_code != 200:
                                    message_placeholder.error(f"Stream Error: {response.status_code}")
                                    full_response = "Error"
                                else:
                                    current_event = None
                                    for line in response.iter_lines():
                                        if not line: continue
                                        
                                        if line.startswith("event:"):
                                            current_event = line[6:].strip()
                                        elif line.startswith("data:"):
                                            data_content = line[5:].strip()
                                            
                                            if current_event == "sources":
                                                try:
                                                    retrieved_sources = json.loads(data_content)
                                                except: pass
                                            
                                            elif current_event == "message":
                                                full_response += data_content
                                                # 实时更新占位符
                                                message_placeholder.markdown(full_response + "▌")
                                    
                                    # 循环结束，用最终结果覆盖占位符 (移除光标)
                                    message_placeholder.markdown(full_response)

                    except Exception as e:
                        message_placeholder.error(f"Connection Error: {str(e)}")
                        full_response = str(e)

                # ================= B. 普通模式 =================
                else:
                    # 普通模式下完全不创建 st.empty()，直接显示 Spinner 和 Markdown
                    with st.spinner("思考中..."):
                        try:
                            res = httpx.post(f"{API_BASE_URL}/chat/query", json=payload, timeout=60.0)
                            if res.status_code == 200:
                                data = res.json()
                                full_response = data["answer"]
                                retrieved_sources = data["sources"]
                                # 直接输出结果
                                st.markdown(full_response)
                            else:
                                st.error(res.text)
                                full_response = "Error"
                        except Exception as e:
                            st.error(str(e))
                            full_response = str(e)

                # ================= 公共逻辑：显示来源 =================
                # 无论哪种模式，来源都在文本下方显示
                if retrieved_sources:
                    with st.expander(f"📚 参考了 {len(retrieved_sources)} 个切片"):
                        for idx, src in enumerate(retrieved_sources):
                            # [修复] 增加页码显示
                            page_num = src.get("page_number")
                            page_info = f" (P{page_num})" if page_num else ""
                            st.markdown(f"**[{idx+1}] {src['source_filename']}{page_info}**")
                            st.caption(src['chunk_content'])
                
                # 更新 Session State (不自动 Rerun，等待下一次交互)
                if full_response and full_response != "Error":
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": full_response,
                        "sources": retrieved_sources
                    })

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
                        # [修改] 替换 slider 为 number_input
                        exp_top_k = st.number_input("Top K", min_value=1, max_value=50, value=3, step=1)
                        exp_strategy = st.selectbox("检索策略", ["default", "hybrid", "rerank"])
                        exp_llm = st.selectbox("学生 LLM", ["qwen-flash", "qwen-turbo", "qwen-plus"])
                        
                        if st.form_submit_button("开始评估", type="primary"):
                            if selected_ts_id:
                                params = {"top_k": exp_top_k, "strategy": exp_strategy, "llm": exp_llm}
                                success, result = run_experiment(selected_kb['id'], selected_ts_id, params)
                                
                                if success:
                                    exp_id = result # result 是 ID
                                    st.toast(f"实验已提交 (ID: {exp_id})，开始运行...", icon="🏃")
                                    
                                    # --- 实时进度可视化 ---
                                    with st.status("🧪 正在运行评估 (这可能需要几分钟)...", expanded=True) as status:
                                        st.write("🚀 初始化实验环境...")
                                        # [Fix] 创建一个空的占位符用于后续更新状态文本
                                        status_placeholder = st.empty()
                                        time.sleep(1)
                                        
                                        while True:
                                            exp_data = get_experiment_detail(exp_id)
                                            if not exp_data:
                                                status_placeholder.error("无法获取实验详情。")
                                                break
                                                
                                            exp_status = exp_data.get("status")
                                            
                                            if exp_status == "COMPLETED":
                                                # [Fix] 完成时清空进度文本
                                                status_placeholder.empty()
                                                status.update(label="✅ 评估完成！", state="complete", expanded=False)
                                                
                                                # === 核心：立即绘制雷达图 ===
                                                st.success("评估成功！结果如下：")
                                                
                                                # 准备指标数据
                                                metrics = {
                                                    "Faithfulness": exp_data.get("faithfulness", 0),
                                                    "Relevancy": exp_data.get("answer_relevancy", 0),
                                                    "Recall": exp_data.get("context_recall", 0),
                                                    "Precision": exp_data.get("context_precision", 0)
                                                }
                                                
                                                # 使用 Matplotlib 绘制
                                                fig = plot_radar_chart(metrics)
                                                st.pyplot(fig, use_container_width=False)
                                                
                                                # 显示数值
                                                c_m1, c_m2, c_m3, c_m4 = st.columns(4)
                                                c_m1.metric("Faithfulness", f"{metrics['Faithfulness']:.3f}")
                                                c_m2.metric("Relevancy", f"{metrics['Relevancy']:.3f}")
                                                c_m3.metric("Recall", f"{metrics['Recall']:.3f}")
                                                c_m4.metric("Precision", f"{metrics['Precision']:.3f}")
                                                
                                                st.caption("提示：点击下方的刷新列表可将其归档。")
                                                break
                                            
                                            elif exp_status == "FAILED":
                                                # [Fix] 失败时清空进度文本
                                                status_placeholder.empty()
                                                status.update(label="❌ 评估失败", state="error", expanded=True)
                                                st.error(f"错误详情: {exp_data.get('error_message')}")
                                                break
                                            
                                            elif exp_status == "RUNNING":
                                                # [Fix] 使用 markdown 更新占位符，而不是 write 追加
                                                status_placeholder.markdown("🔄 正在生成回答并计算指标 (Ragas)...")
                                            
                                            elif exp_status == "PENDING":
                                                # [Fix] 使用 markdown 更新占位符
                                                status_placeholder.markdown("⏳ 正在排队中...")
                                            
                                            time.sleep(3) # 轮询间隔
                                else:
                                    st.error(result)
                            else:
                                st.error("请选择一个有效的测试集")
            
            with col_e2:
                st.subheader("📈 历史实验记录")
                experiments = get_experiments(selected_kb['id'])
                if experiments:
                    # [修改] 为了正确展示长名字指标，调整了列宽分配
                    # 表头
                    h1, h2, h3, h4, h5 = st.columns([0.5, 1.5, 4.5, 2, 1])
                    h1.markdown("**ID**")
                    h2.markdown("**状态**")
                    h3.markdown("**各项指标 (DB字段)**") # [修改] 标题更清晰
                    h4.markdown("**参数**")
                    h5.markdown("**操作**")
                    st.divider()

                    for exp in experiments:
                        c1, c2, c3, c4, c5 = st.columns([0.5, 1.5, 4.5, 2, 1])
                        
                        c1.text(f"#{exp['id']}")
                        
                        # 状态
                        status = exp['status']
                        if status == "COMPLETED":
                            c2.success("✅ 完成")
                        elif status == "FAILED":
                            c2.error("❌ 失败")
                        else:
                            c2.warning(f"⏳ {status}")
                            
                        # 得分 [修改] 垂直排列显示所有4个指标的DB原名
                        if status == "COMPLETED":
                            # 使用 markdown 换行符
                            metrics_display = f"""
                            **faithfulness**: {exp.get('faithfulness', 0):.4f}  
                            **answer_relevancy**: {exp.get('answer_relevancy', 0):.4f}  
                            **context_recall**: {exp.get('context_recall', 0):.4f}  
                            **context_precision**: {exp.get('context_precision', 0):.4f}
                            """
                            c3.markdown(metrics_display)
                        else:
                            c3.caption("-")
                            
                        # 参数
                        params = exp.get("runtime_params", {}) or {}
                        param_str = f"TopK:{params.get('top_k')} | {params.get('strategy')}"
                        c4.text(param_str)
                        
                        # 操作
                        if c5.button("🗑️", key=f"del_exp_{exp['id']}"):
                            success, msg = delete_experiment(exp['id'])
                            if success:
                                st.toast(f"实验 {exp['id']} 已删除")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)
                        
                        st.divider()
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
                    col1, col2, col3, col4 = st.columns([3, 2, 1, 1]) # [修改] 增加一列
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
                    
                    # [新增] 删除按钮
                    with col4:
                         if st.button("🗑️", key=f"del_ts_{ts['id']}", help="删除此测试集"):
                            success, msg = delete_testset(ts['id'])
                            if success:
                                st.toast(f"测试集 {ts['name']} 已删除")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)

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