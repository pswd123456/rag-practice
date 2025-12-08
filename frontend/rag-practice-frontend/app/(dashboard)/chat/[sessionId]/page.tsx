"use client";

import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { chatService } from "@/lib/services/chat";
import { Message, Source, ChatRequest, ChatSession } from "@/lib/types";
import { MessageBubble } from "@/components/business/chat/message-bubble";
import { ChatInput, ModelOption } from "@/components/business/chat/chat-input";
import { ChatSettings } from "@/components/business/chat/chat-settings";
import { useChatStore } from "@/lib/store";

const MODEL_OPTIONS: ModelOption[] = [
  { value: "qwen-flash", label: "Qwen Flash" },
  { value: "qwen-plus", label: "Qwen Plus" },
  { value: "qwen-max", label: "Qwen Max" },
  { value: "deepseek-chat", label: "DeepSeek V3" },
  { value: "deepseek-reasoner", label: "DeepSeek R1" },
  { value: "google/gemini-3-pro-preview-free", label: "Gemini Pro" },
];

export default function ChatSessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const { fetchSessions } = useChatStore();

  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingInitial, setLoadingInitial] = useState(true);
  const [streaming, setStreaming] = useState(false);
  
  const [selectedModel, setSelectedModel] = useState("qwen-max");
  
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (sessionId) {
      initSession();
    }
  }, [sessionId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streaming]);

  const initSession = async () => {
    setLoadingInitial(true);
    try {
      const [sessData, histData] = await Promise.all([
        chatService.getSession(sessionId),
        chatService.getHistory(sessionId)
      ]);
      setSession(sessData);
      setMessages(histData);
    } catch (error) {
      console.error(error);
      toast.error("加载会话失败");
    } finally {
      setLoadingInitial(false);
    }
  };

  const refreshSessionInfo = async () => {
    try {
      const data = await chatService.getSession(sessionId);
      setSession(data);
    } catch(e) {}
  };

  const handleSendMessage = async (input: string) => {
    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setStreaming(true);

    let assistantMsgContent = "";
    let assistantSources: Source[] = [];
    let tokenUsage = 0; // [New]
    
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", isStreaming: true },
    ]);

    const payload: ChatRequest = {
      query: input,
      top_k: session?.top_k || 3,
      stream: true,
      llm_model: selectedModel
    };

    await chatService.sendMessageStream(
      sessionId,
      payload,
      (chunk) => {
        assistantMsgContent += chunk;
        updateLastMessage(assistantMsgContent, assistantSources, tokenUsage);
      },
      (sources) => {
        assistantSources = sources;
        updateLastMessage(assistantMsgContent, assistantSources, tokenUsage);
      },
      // [New] Usage Callback
      (usage) => {
        // 如果后端返回了 total_tokens (通常是 input + output)
        tokenUsage = usage.total_tokens || (usage.input_tokens + usage.output_tokens);
        updateLastMessage(assistantMsgContent, assistantSources, tokenUsage);
      },
      (err: any) => {
        // [Fix] 针对 429 或其他错误的特定处理
        const errMsg = err.message || "";
        if (errMsg.includes("Daily request limit") || errMsg.includes("Daily token quota")) {
          toast.error("已达到每日限流配额", { description: errMsg });
        } else {
          toast.error("回复生成失败", { description: errMsg });
        }
        
        setStreaming(false);
        // 如果出错，移除最后一条空消息 (或者保留并显示错误状态，这里选择移除)
        setMessages((prev) => {
           const last = prev[prev.length - 1];
           if (last.role === "assistant" && !last.content) {
             return prev.slice(0, -1);
           }
           return prev;
        });
      },
      () => {
        setStreaming(false);
        if (session?.title === "New Chat" || session?.title === "新对话") {
           refreshSessionInfo();
           fetchSessions(); 
        }
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

  const updateLastMessage = (content: string, sources?: Source[], tokenUsage?: number) => {
    setMessages((prev) => {
      const newHistory = [...prev];
      const lastIndex = newHistory.length - 1;
      if (lastIndex >= 0 && newHistory[lastIndex].role === "assistant") {
        newHistory[lastIndex] = {
          ...newHistory[lastIndex],
          content: content,
          sources: sources,
          token_usage: tokenUsage || newHistory[lastIndex].token_usage, // [New]
        };
      }
      return newHistory;
    });
  };

  const handleStop = () => {
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
    <div className="relative flex flex-col h-full bg-zinc-50/50 dark:bg-zinc-950/50">
      {/* Header Bar */}
      <div className="flex items-center justify-between px-6 py-2 border-b bg-background/80 backdrop-blur-sm sticky top-0 z-10 h-14">
        <div className="flex items-center gap-4">
          <div>
            <h2 className="text-sm font-semibold">{session?.title}</h2>
            <div className="text-[10px] text-muted-foreground flex gap-2">
               <span>{messages.length} 消息</span>
               {session?.knowledge_ids && session.knowledge_ids.length > 1 && (
                 <span className="text-primary/80">({session.knowledge_ids.length} 知识库)</span>
               )}
               <span className="text-muted-foreground/60">· Top {session?.top_k || 3}</span>
            </div>
          </div>
        </div>

        <div>
          {session && <ChatSettings session={session} onUpdate={refreshSessionInfo} />}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 md:p-6 scroll-smooth">
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground py-20">
              <div className="mb-4 text-4xl">👋</div>
              <p>开始一个新的话题吧...</p>
            </div>
          ) : (
            messages.map((msg, index) => (
              <MessageBubble key={index} message={msg} />
            ))
          )}
          <div ref={scrollRef} className="h-px w-full" />
        </div>
      </div>

      {/* Input Area */}
      <div className="sticky bottom-0 bg-background/80 backdrop-blur-sm border-t pt-2 pb-4">
        <ChatInput 
          isLoading={streaming} 
          onSend={handleSendMessage} 
          onStop={handleStop}
          selectedModel={selectedModel}
          onModelChange={setSelectedModel}
          modelOptions={MODEL_OPTIONS}
        />
      </div>
    </div>
  );
}