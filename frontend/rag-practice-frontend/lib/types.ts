// lib/types.ts

// 对应后端 app/domain/schemas/token.py
export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// 对应后端 app/domain/schemas/user.py (UserRead)
export interface UserRead {
  id: number;
  email: string;
  full_name?: string;
  is_active: boolean;
  is_superuser: boolean; // [New]
}

// === Knowledge Base Types ===

export enum UserKnowledgeRole {
  OWNER = "OWNER",
  EDITOR = "EDITOR",
  VIEWER = "VIEWER",
}

export enum KnowledgeStatus {
  NORMAL = "NORMAL",
  DELETING = "DELETING",
  FAILED = "FAILED",
}

export interface Knowledge {
  id: number;
  name: string;
  description?: string;
  embed_model: string;
  chunk_size: number;
  chunk_overlap: number;
  status: KnowledgeStatus;
  role: UserKnowledgeRole;
  created_at?: string;
  updated_at?: string;
}

export interface KnowledgeCreate {
  name: string;
  description?: string;
  embed_model: string;
  chunk_size: number;
  chunk_overlap: number;
}

export interface KnowledgeUpdate {
  name?: string;
  description?: string;
  embed_model?: string;
  chunk_size?: number;
}

// === Chat Types ===

export interface ChatSession {
  id: string; // UUID
  title: string;
  icon: string; 
  top_k: number; // [New]
  knowledge_id: number;
  knowledge_ids: number[]; 
  user_id: number;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionUpdate {
  title?: string;
  icon?: string;
  top_k?: number; // [New]
  knowledge_ids?: number[];
}

export interface Source {
  filename: string;
  page?: number;
  content: string;
  score?: number;
  knowledge_id?: number;
}

export interface Message {
  id?: number; // 乐观更新时可能暂时没有 ID
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  created_at?: string;
  isStreaming?: boolean; // 前端辅助字段，标记是否正在流式生成
}

export interface ChatRequest {
  query: string;
  top_k?: number;
  llm_model?: string;
  rerank_model_name?: string;
  stream?: boolean;
  prompt_name?: string;
}

// === Evaluation Types [New] ===

export interface Testset {
  id: number;
  name: string;
  description?: string;
  file_path: string;
  status: "PENDING" | "GENERATING" | "COMPLETED" | "FAILED";
  error_message?: string;
  created_at: string;
}

export interface TestsetCreate {
  name: string;
  source_doc_ids: number[];
  generator_llm: string;
}

export interface Experiment {
  id: number;
  knowledge_id: number;
  testset_id: number;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  error_message?: string;
  created_at: string;
  
  // Metrics
  faithfulness: number;
  answer_relevancy: number;
  context_recall: number;
  context_precision: number;
  answer_accuracy: number;
  context_entities_recall: number;
  
  // Params
  runtime_params?: Record<string, any>;
}

export interface ExperimentCreate {
  knowledge_id: number;
  testset_id: number;
  runtime_params: Record<string, any>;
}