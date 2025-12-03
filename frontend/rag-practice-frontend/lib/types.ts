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
  knowledge_id: number;
  user_id: number;
  created_at: string;
  updated_at: string;
}

export interface Source {
  filename: string;
  page?: number;
  content: string;
  score?: number;
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
}