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
  embed_model?: string; // Although backend might restrict this, keeping schema consistent
  chunk_size?: number;
}