# frontend/api.py
import httpx
import json
import logging
import streamlit as st
from typing import Optional, Generator, Any, List, Dict

# 自动检测 API Base URL
API_BASE_URL = "http://api:8000" 
try:
    httpx.get("http://localhost:8000", timeout=1)
    API_BASE_URL = "http://localhost:8000"
except:
    API_BASE_URL = "http://api:8000"

logger = logging.getLogger(__name__)

# --- Helper: Auth Headers & Error Handling ---

def _get_headers():
    headers = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _handle_response(res, success_status=200):
    if res.status_code == success_status:
        return True, res.json() if res.content else "Success"
    
    if res.status_code == 401:
        st.warning("会话已过期，请重新登录。")
        st.session_state.pop("token", None)
        st.session_state.pop("user_info", None)
        st.rerun()
        return False, "Unauthorized"
    
    try:
        detail = res.json().get("detail", res.text)
    except:
        detail = res.text
    return False, detail

# --- Authentication (保持不变) ---
def login(username, password):
    try:
        data = {"username": username, "password": password}
        res = httpx.post(f"{API_BASE_URL}/auth/access-token", data=data)
        if res.status_code == 200:
            return True, res.json()
        else:
            return False, res.json().get("detail", "登录失败")
    except Exception as e:
        return False, str(e)

def register(email, password, full_name=None):
    try:
        payload = {"email": email, "password": password, "full_name": full_name}
        res = httpx.post(f"{API_BASE_URL}/auth/register", json=payload)
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def get_current_user_info():
    try:
        res = httpx.post(f"{API_BASE_URL}/auth/test-token", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return None

# --- Knowledge Base (参数适配) ---
# 后端现在自动从 Token 获取 User，前端只需传 Header 即可，无需改动 Payload

def get_knowledges():
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
             _handle_response(res)
    except Exception as e:
        logger.error(f"API Error: {e}")
    return []

def create_knowledge(payload: dict):
    try:
        res = httpx.post(f"{API_BASE_URL}/knowledge/knowledges", json=payload, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def delete_knowledge(kb_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def update_knowledge(kb_id: int, name: str, desc: str):
    try:
        res = httpx.put(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}", json={
            "name": name, "description": desc
        }, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

# --- Documents (保持不变) ---
def get_documents(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}/documents", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except: pass
    return []

def upload_file(kb_id: int, files: dict):
    try:
        res = httpx.post(
            f"{API_BASE_URL}/knowledge/{kb_id}/upload", 
            files=files, timeout=60.0, headers=_get_headers()
        )
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def delete_document(doc_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/documents/{doc_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def get_document_status(doc_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/documents/{doc_id}", headers=_get_headers())
        if res.status_code == 200:
            return res.json().get("status")
    except: pass
    return None

# --- [NEW] Chat Sessions & Messages ---

def get_sessions():
    """获取当前用户的会话列表"""
    try:
        res = httpx.get(f"{API_BASE_URL}/chat/sessions", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except Exception as e:
        logger.error(f"API Error: {e}")
    return []

def create_session(knowledge_id: int, title: str = "New Chat"):
    """创建新会话"""
    try:
        payload = {"knowledge_id": knowledge_id, "title": title}
        res = httpx.post(f"{API_BASE_URL}/chat/sessions", json=payload, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def delete_session(session_id: str):
    """删除会话"""
    try:
        res = httpx.delete(f"{API_BASE_URL}/chat/sessions/{session_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def get_session_messages(session_id: str):
    """获取会话历史消息"""
    try:
        res = httpx.get(f"{API_BASE_URL}/chat/sessions/{session_id}/messages", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except: pass
    return []

def chat_completion_stream(session_id: str, payload: dict) -> Generator[Any, None, None]:
    """
    [Core] 流式对话接口
    payload: {query, top_k, llm_model, stream=True}
    """
    try:
        headers = _get_headers()
        url = f"{API_BASE_URL}/chat/sessions/{session_id}/completion"
        
        with httpx.Client(timeout=60.0, headers=headers) as client:
            with client.stream("POST", url, json=payload) as response:
                if response.status_code == 401:
                    yield {"error": "Unauthorized"}
                    st.session_state.pop("token", None)
                    st.rerun()
                    return
                
                if response.status_code != 200:
                    yield {"error": f"Error {response.status_code}: {response.text}"}
                    return

                current_event = None
                for line in response.iter_lines():
                    if not line: continue
                    
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_content = line[5:].strip()
                        
                        if current_event == "sources":
                            try:
                                yield {"type": "sources", "data": json.loads(data_content)}
                            except: pass
                        
                        elif current_event == "message":
                            try:
                                # 尝试解析 JSON token
                                token = json.loads(data_content)
                                yield {"type": "message", "data": token}
                            except:
                                yield {"type": "message", "data": data_content}
    except Exception as e:
        yield {"error": str(e)}

# --- Evaluation (保持不变) ---
def get_testsets():
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets", headers=_get_headers())
        return res.json() if res.status_code == 200 else []
    except: return []

def create_testset(name, doc_ids, model):
    try:
        res = httpx.post(f"{API_BASE_URL}/evaluation/testsets", json={
            "name": name, "source_doc_ids": doc_ids, "generator_llm": model
        }, headers=_get_headers())
        return _handle_response(res)
    except Exception as e: return False, str(e)

def get_testset_status(ts_id):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets/{ts_id}", headers=_get_headers())
        return res.json().get("status") if res.status_code == 200 else None
    except: return None

def delete_testset(ts_id):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/testsets/{ts_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e: return False, str(e)

def get_experiments(kb_id):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments", params={"knowledge_id": kb_id}, headers=_get_headers())
        return res.json() if res.status_code == 200 else []
    except: return []

def run_experiment(kb_id, ts_id, params):
    try:
        res = httpx.post(f"{API_BASE_URL}/evaluation/experiments", json={
            "knowledge_id": kb_id, "testset_id": ts_id, "runtime_params": params
        }, headers=_get_headers())
        return _handle_response(res)
    except Exception as e: return False, str(e)

def get_experiment_detail(exp_id):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments/{exp_id}", headers=_get_headers())
        return res.json() if res.status_code == 200 else None
    except: return None

def delete_experiment(exp_id):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/experiments/{exp_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e: return False, str(e)


def get_members(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/{kb_id}/members", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except Exception as e:
        pass
    return []

def add_member(kb_id: int, email: str, role: str):
    try:
        payload = {"email": email, "role": role}
        res = httpx.post(f"{API_BASE_URL}/knowledge/{kb_id}/members", json=payload, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def remove_member(kb_id: int, user_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/{kb_id}/members/{user_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)