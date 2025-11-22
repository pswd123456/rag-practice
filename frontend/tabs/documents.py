import streamlit as st
import time
import api

def render_documents_tab(selected_kb):
    with st.container():
        st.subheader("📤 上传文件")
        uploaded_file = st.file_uploader("支持 PDF/TXT/MD", type=["pdf", "txt", "md"])
        if uploaded_file and st.button("开始上传", type="primary"):
            files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
            
            doc_id = None
            with st.spinner("正在上传文件..."):
                success, result = api.upload_file(selected_kb['id'], files)
                if success:
                    doc_id = result
                    st.toast(f"文件已上传 (ID: {doc_id})，开始后台处理...", icon="🚀")
                else:
                    st.error(f"上传失败: {result}")
                    st.stop()

            if doc_id:
                with st.status("正在解析与向量化...", expanded=True) as status:
                    st.write("Worker 正在努力工作中...")
                    
                    # 循环检查状态
                    while True:
                        current_status = api.get_document_status(doc_id)
                        
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
    docs = api.get_documents(selected_kb['id'])
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
                success, msg = api.delete_document(doc['id'])
                if success:
                    st.toast(f"文档 {doc['filename']} 已删除")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
            st.divider()
    else:
        st.info("当前知识库暂无文档。")