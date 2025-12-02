# frontend/tabs/chat.py
import streamlit as st
import api

def render_chat_tab(selected_kb, current_session):
    """
    渲染对话界面
    """
    if not current_session:
        st.info("👈 请在左侧新建或选择一个会话以开始对话。")
        return

    # 1. 顶部配置
    col_s1, col_s2, col_s3 = st.columns([1.5, 1.5, 2])
    with col_s1:
        st.caption(f"当前会话: **{current_session['title']}**")
    with col_s2:
        llm_model = st.selectbox(
            "模型", 
            ["qwen-flash", "qwen-plus", "qwen-max", "deepseek-chat"],
            index=2,
            label_visibility="collapsed"
        )
    with col_s3:
        top_k = st.slider("Recall TopK", 1, 10, 5, label_visibility="collapsed")

    st.divider()

    # 2. 加载并显示历史消息
    # 不再依赖 st.session_state.messages 来持久化，而是每次重绘都从后端拉取
    # 但为了流式体验，我们可以用 session_state 做临时缓存，或者直接相信后端速度
    
    # 策略：初始化时拉取一次，后续流式追加到本地 state，rerun 后再次拉取覆盖
    if "messages" not in st.session_state or st.session_state.get("current_session_id") != current_session["id"]:
        # 会话切换了，重新拉取
        with st.spinner("正在加载历史记录..."):
            msgs = api.get_session_messages(current_session["id"])
            st.session_state.messages = msgs
            st.session_state.current_session_id = current_session["id"]
    
    # 渲染历史
    for msg in st.session_state.messages:
        role = msg["role"]
        content = msg["content"]
        sources = msg.get("sources", [])
        
        with st.chat_message(role):
            st.markdown(content)
            if sources:
                with st.expander(f"📚 参考了 {len(sources)} 个切片"):
                    for idx, src in enumerate(sources):
                        score = f"(Score: {src.get('score', 0):.2f})" if src.get('score') else ""
                        st.markdown(f"**[{idx+1}] {src['filename']}** {score}")
                        st.caption(src['content'])

    # 3. 处理输入
    if prompt := st.chat_input("输入问题..."):
        # 3.1 立即显示用户输入
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # 3.2 调用流式接口
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""
            retrieved_sources = []
            
            payload = {
                "query": prompt,
                "top_k": top_k,
                "llm_model": llm_model,
                "stream": True
            }
            
            # 使用生成器
            stream_gen = api.chat_completion_stream(current_session["id"], payload)
            
            try:
                for event in stream_gen:
                    if "error" in event:
                        st.error(event["error"])
                        break
                    
                    if event["type"] == "message":
                        chunk = event["data"]
                        full_response += chunk
                        message_placeholder.markdown(full_response + "▌")
                    
                    elif event["type"] == "sources":
                        retrieved_sources = event["data"]
            except Exception as e:
                st.error(f"Stream Error: {e}")

            message_placeholder.markdown(full_response)
            
            # 显示来源
            if retrieved_sources:
                with st.expander(f"📚 参考了 {len(retrieved_sources)} 个切片"):
                    for idx, src in enumerate(retrieved_sources):
                        st.markdown(f"**[{idx+1}] {src['filename']}**")
                        st.caption(src['content'])
            
            # 3.3 更新本地 State (防止用户手动刷新前数据丢失)
            st.session_state.messages.append({
                "role": "assistant",
                "content": full_response,
                "sources": retrieved_sources
            })