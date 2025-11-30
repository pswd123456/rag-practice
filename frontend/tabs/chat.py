import streamlit as st
import api

def render_chat_tab(selected_kb):
    # 1. 顶部配置区
    # [Modify] 调整列宽比例适配新控件
    col_s1, col_s2, col_s3 = st.columns([1.2, 1.2, 2.6])
    
    with col_s1:
        llm_model = st.selectbox(
            "对话模型 (Generator)", 
            [
                "qwen-flash", 
                "qwen-plus", 
                "qwen-max", 
                "deepseek-chat", 
                "deepseek-reasoner",
                "google/gemini-3-pro-preview-free"
            ],
            index=0,
            help="负责根据检索结果生成最终回答的模型"
        )
        
    with col_s2:
        # [Modify] 移除 Strategy 选择，改为 Final Top K 控制
        # 这是 Rerank 之后最终保留给 LLM 的文档数量
        top_k = st.number_input(
            "Final Top K", 
            min_value=1, 
            max_value=10, 
            value=5, 
            help="重排序后，最终保留并喂给 LLM 的文档数量 (Recall 默认为 50)"
        )

    with col_s3:
        # [Modify] 优化布局，显示 Rerank 状态
        use_stream = st.checkbox("流式输出", value=True)
        st.caption("🚀 Rerank: `Enabled` (bge-reranker-v2-m3)")
    
    st.divider()

    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    if st.button("🧹 清空对话"):
        st.session_state.messages = []
        st.rerun()

    # 2. 渲染历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sources" in msg and msg["sources"]:
                with st.expander(f"📚 参考了 {len(msg['sources'])} 个切片"):
                    for idx, src in enumerate(msg["sources"]):
                        # [Opt] 显示 Rerank 分数 (如果有)
                        score_info = ""
                        if "score" in src:
                            score_info = f" (Score: {src['score']:.4f})"
                            
                        page_num = src.get("page_number")
                        page_info = f" (P{page_num})" if page_num else ""
                        
                        st.markdown(f"**[{idx+1}] {src['source_filename']}{page_info}**{score_info}")
                        st.caption(src['chunk_content'])

    # 3. 处理用户输入
    if prompt := st.chat_input("在这个知识库中搜索..."):
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 显示助手响应
        with st.chat_message("assistant"):
            # [Modify] 构建新的 Payload，移除 strategy，添加 top_k
            payload = {
                "query": prompt,
                "knowledge_id": selected_kb['id'],
                "top_k": top_k,          # Rerank 后的截断数量
                "llm_model": llm_model   # 选中的生成模型
                # "rerank_model_name": ... # 可选，不传则使用后端默认配置
            }
            
            full_response = ""
            retrieved_sources = []

            # ================= A. 流式模式 =================
            if use_stream:
                message_placeholder = st.empty()
                stream_gen = api.chat_stream(payload)
                
                for event in stream_gen:
                    if "error" in event:
                        message_placeholder.error(event["error"])
                        full_response = "Error"
                        break
                    
                    if event["type"] == "sources":
                        retrieved_sources = event["data"]
                    
                    elif event["type"] == "message":
                        full_response += event["data"]
                        message_placeholder.markdown(full_response + "▌")
                
                if full_response != "Error":
                    message_placeholder.markdown(full_response)

            # ================= B. 普通模式 =================
            else:
                with st.spinner(f"正在检索与思考 ({llm_model})..."):
                    success, data = api.chat_query(payload)
                    if success:
                        full_response = data["answer"]
                        retrieved_sources = data["sources"]
                        st.markdown(full_response)
                    else:
                        st.error(data)
                        full_response = "Error"

            # ================= 公共逻辑：显示来源 =================
            if retrieved_sources:
                with st.expander(f"📚 参考了 {len(retrieved_sources)} 个切片 (Reranked)"):
                    for idx, src in enumerate(retrieved_sources):
                        # 尝试提取分数 (需确认 API 返回结构中是否包含了 score，可选)
                        # 如果后端 Source schema 没改，可能需要通过 extra 字段传递，这里暂时做个容错
                        score_display = ""
                        # if 'metadata' in src and 'rerank_score' in src['metadata']: ...
                        
                        page_num = src.get("page_number")
                        page_info = f" (P{page_num})" if page_num else ""
                        st.markdown(f"**[{idx+1}] {src['source_filename']}{page_info}**")
                        st.caption(src['chunk_content'])
            
            # 更新 Session State
            if full_response and full_response != "Error":
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_response,
                    "sources": retrieved_sources
                })