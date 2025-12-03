import api from "@/lib/api";
import { Testset, TestsetCreate, Experiment, ExperimentCreate } from "@/lib/types";

export const evaluationService = {
  // === Testsets ===
  getTestsets: async () => {
    const response = await api.get<Testset[]>("/evaluation/testsets");
    return response.data;
  },

  createTestset: async (data: TestsetCreate) => {
    const response = await api.post<number>("/evaluation/testsets", data);
    return response.data;
  },

  deleteTestset: async (id: number) => {
    const response = await api.delete(`/evaluation/testsets/${id}`);
    return response.data;
  },

  getTestsetById: async (id: number) => {
    const response = await api.get<Testset>(`/evaluation/testsets/${id}`);
    return response.data;
  },

  // === Experiments ===
  getExperiments: async (knowledgeId?: number) => {
    const params = knowledgeId ? { knowledge_id: knowledgeId } : {};
    const response = await api.get<Experiment[]>("/evaluation/experiments", { params });
    return response.data;
  },

  createExperiment: async (data: ExperimentCreate) => {
    const response = await api.post<number>("/evaluation/experiments", data);
    return response.data;
  },

  deleteExperiment: async (id: number) => {
    const response = await api.delete(`/evaluation/experiments/${id}`);
    return response.data;
  },

  getExperimentById: async (id: number) => {
    const response = await api.get<Experiment>(`/evaluation/experiments/${id}`);
    return response.data;
  }
};