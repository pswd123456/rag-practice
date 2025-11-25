import streamlit as st
import time
import api
import utils

def render_evaluation_tab(selected_kb):
    st.caption("在此处管理测试集并运行对比实验。")
    eval_tab1, eval_tab2 = st.tabs(["🧪 实验看板", "📝 测试集管理"])
    
    # === 子标签 1: 实验看板 ===
    with eval_tab1:
        col_e1, col_e2 = st.columns([1, 2])
        with col_e1:
            st.subheader("🚀 发起新实验")
            testsets = api.get_testsets()
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
                    
                    # [修改] 学生模型 (Student Model) 添加 DeepSeek
                    exp_student_llm = st.selectbox(
                        "学生 LLM (回答者)", 
                        [
                            "qwen-flash", 
                            "qwen-plus", 
                            "qwen-max", 
                            "deepseek-chat",
                            "deepseek-reasoner",
                            "google/gemini-3-pro-preview-free"
                        ],
                        index=0
                    )
                    
                    # [修改] 裁判模型 (Judge Model)
                    exp_judge_llm = st.selectbox(
                        "裁判 LLM (评分者)", 
                        [
                            "qwen-flash", 
                            "qwen-plus", 
                            "qwen-max", 
                            "deepseek-chat",
                            "deepseek-reasoner",
                            "google/gemini-3-pro-preview-free"
                        ],
                        index=0,
                        help="Ragas 评估需要较强的推理能力，建议使用 Qwen-Max, DeepSeek-V3 或 Gemini-Pro"
                    )
                    
                    if st.form_submit_button("开始评估", type="primary"):
                        if selected_ts_id:
                            params = {
                                "top_k": exp_top_k, 
                                "strategy": exp_strategy, 
                                "student_model": exp_student_llm,
                                "judge_model": exp_judge_llm
                            }
                            success, result = api.run_experiment(selected_kb['id'], selected_ts_id, params)
                            
                            if success:
                                exp_id = result
                                st.toast(f"实验已提交 (ID: {exp_id})，开始运行...", icon="🏃")
                                
                                # --- 实时进度可视化 ---
                                with st.status(f"🧪 正在评估 ({exp_student_llm} vs {exp_judge_llm})...", expanded=True) as status:
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
                                            
                                            metrics = {
                                                "Faithfulness": exp_data.get("faithfulness", 0),
                                                "Relevancy": exp_data.get("answer_relevancy", 0),
                                                "Recall": exp_data.get("context_recall", 0),
                                                "Precision": exp_data.get("context_precision", 0)
                                            }
                                            
                                            fig = utils.plot_radar_chart(metrics)
                                            st.pyplot(fig, use_container_width=False)
                                            
                                            c_m1, c_m2, c_m3, c_m4 = st.columns(4)
                                            c_m1.metric("Faithfulness", f"{metrics['Faithfulness']:.3f}")
                                            c_m2.metric("Relevancy", f"{metrics['Relevancy']:.3f}")
                                            c_m3.metric("Recall", f"{metrics['Recall']:.3f}")
                                            c_m4.metric("Precision", f"{metrics['Precision']:.3f}")
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
                                        
                                        time.sleep(3)
                            else:
                                st.error(result)
                        else:
                            st.error("请选择一个有效的测试集")
        
        with col_e2:
            st.subheader("📈 历史实验记录")
            experiments = api.get_experiments(selected_kb['id'])
            if experiments:
                h1, h2, h3, h4, h5 = st.columns([0.5, 1.5, 4.5, 2.5, 1])
                h1.markdown("**ID**")
                h2.markdown("**状态**")
                h3.markdown("**各项指标**")
                h4.markdown("**模型配置**")
                h5.markdown("**操作**")
                st.divider()

                for exp in experiments:
                    c1, c2, c3, c4, c5 = st.columns([0.5, 1.5, 4.5, 2.5, 1])
                    
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
                        **Faithfulness**: {exp.get('faithfulness', 0):.3f}  
                        **Relevancy**: {exp.get('answer_relevancy', 0):.3f}  
                        **Recall**: {exp.get('context_recall', 0):.3f}  
                        **Precision**: {exp.get('context_precision', 0):.3f}
                        """
                        c3.markdown(metrics_display)
                    else:
                        c3.caption("-")
                        
                    params = exp.get("runtime_params", {}) or {}
                    student = params.get("student_model") or params.get("llm") or "qwen-flash"
                    judge = params.get("judge_model") or "qwen-max"
                    param_str = f"**Student**: {student}\n**Judge**: {judge}\nTopK: {params.get('top_k')}"
                    c4.markdown(param_str)
                    
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
                    
                    # [修改] 模型选择添加 DeepSeek
                    ts_generator_model = st.selectbox(
                        "生成模型 (Generator)", 
                        ["qwen-max", "qwen-plus", "deepseek-chat", "google/gemini-3-pro-preview-free"],
                        index=0,
                        help="推荐使用较强的模型 (如 Qwen-Max, DeepSeek-V3) 以保证数据质量。"
                    )
                    
                    if st.form_submit_button("提交生成任务"):
                        if not ts_name or not selected_doc_ids:
                            st.error("请填写名称并选择文档。")
                        else:
                            success, msg = api.create_testset(ts_name, selected_doc_ids, ts_generator_model)
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
                    st.caption(f"{ts.get('description', '')}")
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