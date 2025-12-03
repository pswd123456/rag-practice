import api from "@/lib/api";
import { ChatSession, Message, ChatRequest } from "@/lib/types";
import { useAuthStore } from "@/lib/store";

export const chatService = {
  // === Sessions ===
  getSessions: async () => {
    const response = await api.get<ChatSession[]>("/chat/sessions");
    return response.data;
  },

  createSession: async (knowledgeId: number) => {
    const response = await api.post<ChatSession>("/chat/sessions", {
      knowledge_id: knowledgeId,
      title: "New Chat",
    });
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

  /**
   * 发送消息并处理 SSE 流式响应
   * @param sessionId 会话ID
   * @param payload 请求体
   * @param onMessageCallback 接收文本块的回调
   * @param onSourcesCallback 接收引用源的回调
   * @param onErrorCallback 错误回调
   * @param onFinishCallback 完成回调
   */
  sendMessageStream: async (
    sessionId: string,
    payload: ChatRequest,
    onMessageCallback: (text: string) => void,
    onSourcesCallback: (sources: any[]) => void,
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
        throw new Error(`API Error: ${response.statusText}`);
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

        // 处理 buffer 中的 SSE 事件
        // 格式通常是:
        // event: message\n
        // data: "..."\n\n
        const lines = buffer.split("\n\n");
        // 保留最后一个可能不完整的块
        buffer = lines.pop() || "";

        for (const line of lines) {
          const eventMatch = line.match(/^event: (.*)\ndata: (.*)/s);
          if (eventMatch) {
            const eventType = eventMatch[1].trim();
            const dataRaw = eventMatch[2].trim();

            if (eventType === "message") {
              try {
                // 后端可能返回 JSON 字符串或直接字符串，根据后端实现调整
                // 这里假设 dataRaw 是 JSON 格式的字符串 token
                const token = JSON.parse(dataRaw);
                onMessageCallback(token);
              } catch (e) {
                // 如果不是 JSON，直接当文本
                onMessageCallback(dataRaw);
              }
            } else if (eventType === "sources") {
              try {
                const sources = JSON.parse(dataRaw);
                onSourcesCallback(sources);
              } catch (e) {
                console.error("Failed to parse sources", e);
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