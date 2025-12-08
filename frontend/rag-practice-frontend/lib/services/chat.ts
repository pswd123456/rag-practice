import api from "@/lib/api";
import { ChatSession, Message, ChatRequest, ChatSessionUpdate } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

export const chatService = {
  // === Sessions ===
  getSessions: async () => {
    const response = await api.get<ChatSession[]>("/chat/sessions");
    return response.data;
  },

  getSession: async (sessionId: string) => {
    const response = await api.get<ChatSession>(`/chat/sessions/${sessionId}`);
    return response.data;
  },

  createSession: async (knowledgeId: number) => {
    const response = await api.post<ChatSession>("/chat/sessions", {
      knowledge_id: knowledgeId,
      title: "New Chat",
      icon: "message-square"
    });
    return response.data;
  },

  updateSession: async (sessionId: string, data: ChatSessionUpdate) => {
    const response = await api.patch<ChatSession>(`/chat/sessions/${sessionId}`, data);
    return response.data;
  },

  deleteSession: async (sessionId: string) => {
    await api.delete(`/chat/sessions/${sessionId}`);
  },

  // === Messages ===
  getHistory: async (sessionId: string) => {
    const response = await api.get<Message[]>(`/chat/sessions/${sessionId}/messages`);
    return response.data;
  },

  sendMessageStream: async (
    sessionId: string,
    payload: ChatRequest,
    onMessageCallback: (text: string) => void,
    onSourcesCallback: (sources: any[]) => void,
    onUsageCallback: (usage: { input_tokens: number, output_tokens: number, total_tokens: number }) => void, // [New]
    onErrorCallback: (err: any) => void,
    onFinishCallback: () => void
  ) => {
    const token = useAuthStore.getState().token;
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    
    try {
      const response = await fetch(`${baseUrl}/chat/sessions/${sessionId}/completion`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`,
        },
        body: JSON.stringify({ ...payload, stream: true }),
      });

      if (!response.ok) {
        // [Fix] 尝试解析错误详情，特别是为了捕获 429 限流信息
        let errorMsg = `API Error: ${response.statusText}`;
        try {
          const errData = await response.json();
          if (errData.detail) errorMsg = errData.detail;
        } catch (e) {
          // ignore json parse error
        }
        throw new Error(errorMsg);
      }

      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const eventMatch = line.match(/^event: (.*)\ndata: (.*)/s);
          if (eventMatch) {
            const eventType = eventMatch[1].trim();
            const dataRaw = eventMatch[2].trim();

            if (eventType === "message") {
              try {
                const token = JSON.parse(dataRaw);
                onMessageCallback(token);
              } catch (e) {
                onMessageCallback(dataRaw);
              }
            } else if (eventType === "sources") {
              try {
                const sources = JSON.parse(dataRaw);
                onSourcesCallback(sources);
              } catch (e) {
                console.error("Failed to parse sources", e);
              }
            } else if (eventType === "usage") { // [New] 处理 usage 事件
              try {
                const usage = JSON.parse(dataRaw);
                onUsageCallback(usage);
              } catch (e) {
                console.error("Failed to parse usage", e);
              }
            }
          }
        }
      }
      onFinishCallback();
    } catch (error) {
      console.error("Stream error:", error);
      onErrorCallback(error);
    }
  },
};