import httpx
import json
import logging
from typing import Optional, Generator, Any

# 自动检测 API Base URL
API_BASE_URL = "http://api:8000" 
try:
    # 简单探测一下，如果 localhost 通就不改，不通就切 api
    httpx.get("http://localhost:8000", timeout=1)
    API_BASE_URL = "http://localhost:8000"
except:
    API_BASE_URL = "http://api:8000"

logger = logging.getLogger(__name__)

# --- Knowledge Base ---

def get_knowledges():
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.error(f"API Error: {e}")
    return []

def create_knowledge(payload: dict):
    try:
        res = httpx.post(f"{API_BASE_URL}/knowledge/knowledges", json=payload)
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

def delete_knowledge(kb_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}")
        return res.status_code == 200 or res.status_code == 202, res.text
    except Exception as e:
        return False, str(e)

def update_knowledge(kb_id: int, name: str, desc: str):
    try:
        res = httpx.put(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}", json={
            "name": name, "description": desc
        })
        return res.status_code == 200, res.json()
    except Exception as e:
        return False, str(e)

# --- Documents ---

def get_documents(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/knowledges/{kb_id}/documents")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        logger.error(f"API Error: {e}")
    return []

def get_document_status(doc_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/knowledge/documents/{doc_id}")
        if res.status_code == 200:
            return res.json().get("status")
        elif res.status_code == 404:
            return "NOT_FOUND"
    except:
        pass
    return None

def upload_file(kb_id: int, files: dict):
    """
    files 格式: {"file": (filename, file_obj, content_type)}
    """
    try:
        res = httpx.post(f"{API_BASE_URL}/knowledge/{kb_id}/upload", files=files, timeout=60.0)
        if res.status_code == 200:
            return True, res.json() # 返回 doc_id
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def delete_document(doc_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/knowledge/documents/{doc_id}")
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

# --- Chat ---

def chat_query(payload: dict):
    try:
        res = httpx.post(f"{API_BASE_URL}/chat/query", json=payload, timeout=60.0)
        if res.status_code == 200:
            return True, res.json()
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def chat_stream(payload: dict) -> Generator[Any, None, None]:
    """
    生成器，返回 SSE 事件流的数据
    """
    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("POST", f"{API_BASE_URL}/chat/stream", json=payload) as response:
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
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets")
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def get_testset_status(ts_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/testsets/{ts_id}")
        if res.status_code == 200:
            return res.json().get("status")
        elif res.status_code == 404:
            return "NOT_FOUND"
    except:
        pass
    return None

# [修改] 增加 generator_model 参数
def create_testset(name: str, doc_ids: list, generator_model: str = "qwen-max"):
    try:
        res = httpx.post(f"{API_BASE_URL}/evaluation/testsets", json={
            "name": name, 
            "source_doc_ids": doc_ids,
            "generator_llm": generator_model # [新增]
        })
        if res.status_code == 200:
            return True, res.text 
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def delete_testset(ts_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/testsets/{ts_id}")
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)

# --- Evaluation: Experiments ---

def get_experiments(kb_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments", params={"knowledge_id": kb_id})
        if res.status_code == 200:
            return res.json()
    except:
        pass
    return []

def get_experiment_detail(exp_id: int):
    try:
        res = httpx.get(f"{API_BASE_URL}/evaluation/experiments/{exp_id}")
        if res.status_code == 200:
            return res.json()
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
        res = httpx.post(f"{API_BASE_URL}/evaluation/experiments", json=payload, timeout=10.0)
        if res.status_code == 200:
            return True, res.json() # 返回 ID
        else:
            return False, res.text
    except Exception as e:
        return False, str(e)

def delete_experiment(exp_id: int):
    try:
        res = httpx.delete(f"{API_BASE_URL}/evaluation/experiments/{exp_id}")
        return res.status_code == 200, res.text
    except Exception as e:
        return False, str(e)