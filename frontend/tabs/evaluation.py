import streamlit as st
import time
import api
import utils

def render_evaluation_tab(selected_kb):
    st.caption("在此处管理测试集并运行对比实验。")
    eval_tab1, eval_tab2 = st.tabs(["🧪 实验看板", "📝 测试集管理"])
    
    # === 子标签 1: 实验看板 ===
    with eval_tab1:
        col_e1, col_e2 = st.columns([1, 3])
        with col_e1:
            st.subheader("🚀 发起新实验")
            testsets = api.get_testsets()
            # 过滤：只保留 COMPLETED 的测试集
            ready_testsets = [ts for ts in testsets if ts.get('status') == 'COMPLETED']
            
            if not ready_testsets:
                if testsets:
                    st.warning("有测试集正在生成中，请稍候...")
                else:
                    st.warning("请先在“测试集管理”中生成测试集")
            else:
                with st.form("run_exp_form"):
                    ts_options = {f"{ts['name']} (ID:{ts['id']})": ts['id'] for ts in ready_testsets}
                    selected_ts_name = st.selectbox("选择测试集", list(ts_options.keys()))
                    
                    if selected_ts_name:
                        selected_ts_id = ts_options[selected_ts_name]
                    else:
                            selected_ts_id = None

                    st.markdown("**运行时参数**")
                    exp_top_k = st.number_input("Top K", min_value=1, max_value=50, value=3, step=1)
                    exp_strategy = st.selectbox("检索策略", ["default", "hybrid", "rerank"])
                    exp_llm = st.selectbox("学生 LLM", ["qwen-flash", "qwen-turbo", "qwen-plus"])
                    
                    if st.form_submit_button("开始评估", type="primary"):
                        if selected_ts_id:
                            params = {"top_k": exp_top_k, "strategy": exp_strategy, "llm": exp_llm}
                            success, result = api.run_experiment(selected_kb['id'], selected_ts_id, params)
                            
                            if success:
                                exp_id = result # result 是 ID
                                st.toast(f"实验已提交 (ID: {exp_id})，开始运行...", icon="🏃")
                                
                                # --- 实时进度可视化 ---
                                with st.status("🧪 正在运行评估 (这可能需要几分钟)...", expanded=True) as status:
                                    st.write("🚀 初始化实验环境...")
                                    status_placeholder = st.empty()
                                    time.sleep(1)
                                    
                                    while True:
                                        exp_data = api.get_experiment_detail(exp_id)
                                        if not exp_data:
                                            status_placeholder.error("无法获取实验详情。")
                                            break
                                            
                                        exp_status = exp_data.get("status")
                                        
                                        if exp_status == "COMPLETED":
                                            status_placeholder.empty()
                                            status.update(label="✅ 评估完成！", state="complete", expanded=False)
                                            
                                            st.success("评估成功！结果如下：")
                                            
                                            # 准备指标数据
                                            metrics = {
                                                "Faithfulness": exp_data.get("faithfulness", 0),
                                                "Relevancy": exp_data.get("answer_relevancy", 0),
                                                "Recall": exp_data.get("context_recall", 0),
                                                "Precision": exp_data.get("context_precision", 0)
                                            }
                                            
                                            # 绘制雷达图
                                            fig = utils.plot_radar_chart(metrics)
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
                                            status_placeholder.empty()
                                            status.update(label="❌ 评估失败", state="error", expanded=True)
                                            st.error(f"错误详情: {exp_data.get('error_message')}")
                                            break
                                        
                                        elif exp_status == "RUNNING":
                                            status_placeholder.markdown("🔄 正在生成回答并计算指标 (Ragas)...")
                                        
                                        elif exp_status == "PENDING":
                                            status_placeholder.markdown("⏳ 正在排队中...")
                                        
                                        time.sleep(3) # 轮询间隔
                            else:
                                st.error(result)
                        else:
                            st.error("请选择一个有效的测试集")
        
        with col_e2:
            st.subheader("📈 历史实验记录")
            experiments = api.get_experiments(selected_kb['id'])
            if experiments:
                h1, h2, h3, h4, h5 = st.columns([0.5, 1.5, 4.5, 2, 1])
                h1.markdown("**ID**")
                h2.markdown("**状态**")
                h3.markdown("**各项指标 (DB字段)**")
                h4.markdown("**参数**")
                h5.markdown("**操作**")
                st.divider()

                for exp in experiments:
                    c1, c2, c3, c4, c5 = st.columns([0.5, 1.5, 4.5, 2, 1])
                    
                    c1.text(f"#{exp['id']}")
                    
                    status = exp['status']
                    if status == "COMPLETED":
                        c2.success("✅ 完成")
                    elif status == "FAILED":
                        c2.error("❌ 失败")
                    else:
                        c2.warning(f"⏳ {status}")
                        
                    if status == "COMPLETED":
                        metrics_display = f"""
                        **faithfulness**: {exp.get('faithfulness', 0):.4f}  
                        **answer_relevancy**: {exp.get('answer_relevancy', 0):.4f}  
                        **context_recall**: {exp.get('context_recall', 0):.4f}  
                        **context_precision**: {exp.get('context_precision', 0):.4f}
                        """
                        c3.markdown(metrics_display)
                    else:
                        c3.caption("-")
                        
                    params = exp.get("runtime_params", {}) or {}
                    param_str = f"TopK:{params.get('top_k')} | {params.get('strategy')}"
                    c4.text(param_str)
                    
                    if c5.button("🗑️", key=f"del_exp_{exp['id']}"):
                        success, msg = api.delete_experiment(exp['id'])
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
            current_docs = api.get_documents(selected_kb['id'])
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
                            success, msg = api.create_testset(ts_name, selected_doc_ids)
                            if success:
                                ts_id = msg
                                st.toast(f"任务已提交 (ID: {ts_id})，开始生成...", icon="🚀")
                                
                                with st.status("正在生成测试集 (这可能需要几分钟)...", expanded=True) as status:
                                    while True:
                                        ts_status = api.get_testset_status(ts_id)
                                        
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
                                        
                                        time.sleep(2)
                            else:
                                st.error(msg)
        
        st.divider()
        st.subheader("📚 已有测试集")
        ts_list = api.get_testsets()
        if ts_list:
            for ts in ts_list:
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                with col1:
                    st.markdown(f"**{ts['name']}** (ID: {ts['id']})")
                    st.caption(f"路径: `{ts['file_path']}`")
                with col2:
                    status = ts.get('status', 'COMPLETED')
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
                
                with col4:
                        if st.button("🗑️", key=f"del_ts_{ts['id']}", help="删除此测试集"):
                            success, msg = api.delete_testset(ts['id'])
                            if success:
                                st.toast(f"测试集 {ts['name']} 已删除")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(msg)

                st.divider()