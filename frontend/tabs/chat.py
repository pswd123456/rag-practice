import streamlit as st
import api

def render_chat_tab(selected_kb):
    # 1. 顶部配置区
    col_s1, col_s2, col_s3 = st.columns([1, 1, 3])
    with col_s1:
        # [修改] 添加模型选择
        llm_model = st.selectbox(
            "对话模型", 
            ["qwen-flash", "qwen-plus", "qwen-max", "google/gemini-3-pro-preview-free"],
            index=0
        )
    with col_s2:
        strategy = st.selectbox("检索策略", ["default", "dense_only", "hybrid", "rerank"])
    with col_s3:
        use_stream = st.checkbox("流式输出", value=True)
        # 稍微调整一下排版，让checkbox垂直居中
        st.write("") 
    
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
                        page_num = src.get("page_number")
                        page_info = f" (P{page_num})" if page_num else ""
                        st.markdown(f"**[{idx+1}] {src['source_filename']}{page_info}**")
                        st.caption(src['chunk_content'])

    # 3. 处理用户输入
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
                "strategy": strategy,
                "llm_model": llm_model # [新增] 传递选中的模型
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
                with st.spinner(f"正在思考 ({llm_model})..."):
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
                with st.expander(f"📚 参考了 {len(retrieved_sources)} 个切片"):
                    for idx, src in enumerate(retrieved_sources):
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