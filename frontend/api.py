import httpx
import json
import logging
import streamlit as st # 引入 streamlit 以访问 session_state
from typing import Optional, Generator, Any

# 自动检测 API Base URL
API_BASE_URL = "http://api:8000" 
try:
    # 简单探测一下，如果 localhost 通就不改，不通就切 api (Docker内部)
    httpx.get("http://localhost:8000", timeout=1)
    API_BASE_URL = "http://localhost:8000"
except:
    API_BASE_URL = "http://api:8000"

logger = logging.getLogger(__name__)

# --- Helper: Auth Headers & Error Handling ---

def _get_headers():
    """
    自动从 Streamlit Session State 获取 Token 并构造 Header
    """
    headers = {}
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def _handle_response(res, success_status=200):
    """
    统一响应处理，包含 401 自动登出逻辑
    """
    if res.status_code == success_status:
        # 如果是 202 也算成功 (Accepted)
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

# --- Authentication ---

def login(username, password):
    """
    用户登录，换取 JWT
    """
    try:
        # OAuth2 规范要求使用 form-data 格式提交 username/password
        data = {"username": username, "password": password}
        res = httpx.post(f"{API_BASE_URL}/auth/access-token", data=data)
        
        if res.status_code == 200:
            return True, res.json() # {"access_token": "...", "token_type": "bearer"}
        else:
            return False, res.json().get("detail", "登录失败")
    except Exception as e:
        return False, str(e)

def register(email, password, full_name=None):
    """
    用户注册
    """
    try:
        payload = {"email": email, "password": password, "full_name": full_name}
        res = httpx.post(f"{API_BASE_URL}/auth/register", json=payload)
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def get_current_user_info():
    """
    使用当前 Token 获取用户信息
    """
    try:
        res = httpx.post(f"{API_BASE_URL}/auth/test-token", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return None

# --- Knowledge Base ---

def get_knowledges():
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
             _handle_response(res) # 触发登出
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

# --- Documents ---

def get_documents(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}/documents", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except Exception as e:
        logger.error(f"API Error: {e}")
    return []

def get_document_status(doc_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/documents/{doc_id}", headers=_get_headers())
        if res.status_code == 200:
            return res.json().get("status")
        elif res.status_code == 404:
            return "NOT_FOUND"
        elif res.status_code == 401:
            _handle_response(res)
    except:
        pass
    return None

def upload_file(kb_id: int, files: dict):
    """
    files 格式: {"file": (filename, file_obj, content_type)}
    """
    try:
        res = httpx.post(
            f"{API_BASE_URL}/knowledge/{kb_id}/upload", 
            files=files, 
            timeout=60.0,
            headers=_get_headers() # MinIO 上传也需要鉴权
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

# --- Chat ---

def chat_query(payload: dict):
    try:
        res = httpx.post(f"{API_BASE_URL}/chat/query", json=payload, timeout=60.0, headers=_get_headers())
        if res.status_code == 200:
            return True, res.json()
        else:
            return _handle_response(res)
    except Exception as e:
        return False, str(e)

def chat_stream(payload: dict) -> Generator[Any, None, None]:
    """
    生成器，返回 SSE 事件流的数据
    """
    try:
        headers = _get_headers()
        # 注意: httpx stream 模式也需要 headers
        with httpx.Client(timeout=60.0, headers=headers) as client:
            with client.stream("POST", f"{API_BASE_URL}/chat/stream", json=payload) as response:
                if response.status_code == 401:
                    yield {"error": "Unauthorized: Session expired."}
                    st.session_state.pop("token", None)
                    st.rerun()
                    return

                if response.status_code != 200:
                    yield {"error": f"Status Code: {response.status_code}"}
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
                            except json.JSONDecodeError:
                                yield {"type": "message", "data": data_content}
    except Exception as e:
        yield {"error": str(e)}

# --- Evaluation: Testsets ---

def get_testsets():
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except:
        pass
    return []

def get_testset_status(ts_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets/{ts_id}", headers=_get_headers())
        if res.status_code == 200:
            return res.json().get("status")
        elif res.status_code == 404:
            return "NOT_FOUND"
        elif res.status_code == 401:
            _handle_response(res)
    except:
        pass
    return None

def create_testset(name: str, doc_ids: list, generator_model: str = "qwen-max"):
    try:
        res = httpx.post(f"{API_BASE_URL}/evaluation/testsets", json={
            "name": name, 
            "source_doc_ids": doc_ids,
            "generator_llm": generator_model
        }, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def delete_testset(ts_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/testsets/{ts_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

# --- Evaluation: Experiments ---

def get_experiments(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments", params={"knowledge_id": kb_id}, headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except:
        pass
    return []

def get_experiment_detail(exp_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments/{exp_id}", headers=_get_headers())
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            _handle_response(res)
    except:
        pass
    return None

def run_experiment(kb_id: int, testset_id: int, params: dict):
    try:
        payload = {
            "knowledge_id": kb_id,
            "testset_id": testset_id,
            "runtime_params": params
        }
        res = httpx.post(f"{API_BASE_URL}/evaluation/experiments", json=payload, timeout=10.0, headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)

def delete_experiment(exp_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/experiments/{exp_id}", headers=_get_headers())
        return _handle_response(res)
    except Exception as e:
        return False, str(e)