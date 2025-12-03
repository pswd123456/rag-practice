"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { chatService } from "@/lib/services/chat";
import { Message, Source, ChatRequest } from "@/lib/types";
import { MessageBubble } from "@/components/business/chat/message-bubble";
import { ChatInput } from "@/components/business/chat/chat-input";
import { ScrollArea } from "@/components/ui/scroll-area"; // 假设有，如果没有可以用 div

export default function ChatSessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;

  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [streaming, setStreaming] = useState(false);
  
  // 滚动锚点
  const scrollRef = useRef<HTMLDivElement>(null);

  // 初始化加载历史记录
  useEffect(() => {
    if (sessionId) {
      loadHistory();
    }
  }, [sessionId]);

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streaming]);

  const loadHistory = async () => {
    setLoadingInitial(true);
    try {
      const history = await chatService.getHistory(sessionId);
      setMessages(history);
    } catch (error) {
      console.error(error);
      toast.error("加载历史消息失败");
    } finally {
      setLoadingInitial(false);
    }
  };

  const handleSendMessage = async (input: string) => {
    // 1. 乐观更新用户消息
    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    // 2. 准备 Assistant 消息占位符
    let assistantMsgContent = "";
    let assistantSources: Source[] = [];
    
    // 插入一个空的 Assistant 消息用于流式渲染
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", isStreaming: true },
    ]);

    // 3. 构建请求
    const payload: ChatRequest = {
      query: input,
      top_k: 5, // 默认配置，也可以从设置中读取
      stream: true,
    };

    // 4. 调用流式服务
    await chatService.sendMessageStream(
      sessionId,
      payload,
      // onMessage
      (chunk) => {
        assistantMsgContent += chunk;
        updateLastMessage(assistantMsgContent, assistantSources);
      },
      // onSources
      (sources) => {
        assistantSources = sources;
        updateLastMessage(assistantMsgContent, assistantSources);
      },
      // onError
      (err) => {
        toast.error("回复生成失败");
        setStreaming(false);
        // 移除最后一条错误的 loading 消息
        setMessages((prev) => prev.slice(0, -1));
      },
      // onFinish
      () => {
        setStreaming(false);
        // 更新最后一条消息状态为完成
        setMessages((prev) => {
          const newHistory = [...prev];
          const lastMsg = newHistory[newHistory.length - 1];
          if (lastMsg.role === "assistant") {
            lastMsg.isStreaming = false;
          }
          return newHistory;
        });
      }
    );
  };

  // 辅助函数：更新消息列表中的最后一条 (Assistant)
  const updateLastMessage = (content: string, sources?: Source[]) => {
    setMessages((prev) => {
      const newHistory = [...prev];
      const lastIndex = newHistory.length - 1;
      // 确保修改的是最后一条 Assistant 消息
      if (lastIndex >= 0 && newHistory[lastIndex].role === "assistant") {
        newHistory[lastIndex] = {
          ...newHistory[lastIndex],
          content: content,
          sources: sources,
        };
      }
      return newHistory;
    });
  };

  const handleStop = () => {
    // 简单实现：仅前端停止接收，实际上无法中断 Fetch 请求 (需要 AbortController)
    // 这里为了演示，简化为停止状态更新
    setStreaming(false);
    toast.info("已停止生成");
  };

  if (loadingInitial) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="relative flex flex-col h-full">
      {/* 消息列表区域 */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 scroll-smooth">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground py-20">
              开始一个新的话题吧...
            </div>
          ) : (
            messages.map((msg, index) => (
              <MessageBubble key={index} message={msg} />
            ))
          )}
          {/* 底部锚点 */}
          <div ref={scrollRef} className="h-px w-full" />
        </div>
      </div>

      {/* 底部输入框 */}
      <div className="sticky bottom-0 bg-background/80 backdrop-blur-sm border-t pt-2">
        <ChatInput 
          isLoading={streaming} 
          onSend={handleSendMessage} 
          onStop={handleStop} 
        />
      </div>
    </div>
  );
}