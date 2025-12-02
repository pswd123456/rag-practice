import api from "@/lib/api";
import { Knowledge, KnowledgeCreate, KnowledgeUpdate } from "@/lib/types";

export const knowledgeService = {
  // 获取知识库列表
  getAll: async () => {
    const response = await api.get<Knowledge[]>("/knowledge/knowledges");
    return response.data;
  },

  // 获取单个知识库
  getById: async (id: number) => {
    const response = await api.get<Knowledge>(`/knowledge/knowledges/${id}`);
    return response.data;
  },

  // 创建知识库
  create: async (data: KnowledgeCreate) => {
    const response = await api.post<Knowledge>("/knowledge/knowledges", data);
    return response.data;
  },

  // 更新知识库
  update: async (id: number, data: KnowledgeUpdate) => {
    const response = await api.put<Knowledge>(`/knowledge/knowledges/${id}`, data);
    return response.data;
  },

  // 删除知识库
  delete: async (id: number) => {
    const response = await api.delete<{ message: string }>(`/knowledge/knowledges/${id}`);
    return response.data;
  },
};