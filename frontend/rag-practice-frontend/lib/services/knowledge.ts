import api from "@/lib/api";
import { Knowledge, KnowledgeCreate, KnowledgeUpdate, UserKnowledgeRole } from "@/lib/types";

// 定义文档类型
export interface RAGDocument {
  id: number;
  knowledge_base_id: number;
  filename: string;
  file_path: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  error_message?: string;
  created_at: string;
  updated_at: string;
}

// 定义成员类型
export interface Member {
  user_id: number;
  email: string;
  full_name?: string;
  role: UserKnowledgeRole;
}

export const knowledgeService = {
  // === 基础 CRUD ===
  getAll: async () => {
    const response = await api.get<Knowledge[]>("/knowledge/knowledges");
    return response.data;
  },

  getById: async (id: number) => {
    const response = await api.get<Knowledge>(`/knowledge/knowledges/${id}`);
    return response.data;
  },

  create: async (data: KnowledgeCreate) => {
    const response = await api.post<Knowledge>("/knowledge/knowledges", data);
    return response.data;
  },

  update: async (id: number, data: KnowledgeUpdate) => {
    const response = await api.put<Knowledge>(`/knowledge/knowledges/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    const response = await api.delete<{ message: string }>(`/knowledge/knowledges/${id}`);
    return response.data;
  },

  // === 文档管理 ===
  getDocuments: async (knowledgeId: number) => {
    const response = await api.get<RAGDocument[]>(`/knowledge/knowledges/${knowledgeId}/documents`);
    return response.data;
  },

  uploadFile: async (knowledgeId: number, file: File, onUploadProgress?: (progressEvent: any) => void) => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await api.post<number>(`/knowledge/${knowledgeId}/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
      onUploadProgress,
    });
    return response.data; // 返回 doc_id
  },

  deleteDocument: async (docId: number) => {
    const response = await api.delete(`/knowledge/documents/${docId}`);
    return response.data;
  },

  getDocument: async (docId: number) => {
    const response = await api.get<RAGDocument>(`/knowledge/documents/${docId}`);
    return response.data;
  },

  // === 成员管理 ===
  getMembers: async (knowledgeId: number) => {
    const response = await api.get<Member[]>(`/knowledge/${knowledgeId}/members`);
    return response.data;
  },

  addMember: async (knowledgeId: number, email: string, role: UserKnowledgeRole) => {
    const response = await api.post<Member>(`/knowledge/${knowledgeId}/members`, { email, role });
    return response.data;
  },

  removeMember: async (knowledgeId: number, userId: number) => {
    const response = await api.delete(`/knowledge/${knowledgeId}/members/${userId}`);
    return response.data;
  },
};