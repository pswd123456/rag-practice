"use client";

import { MessageSquareDashed } from "lucide-react";

export default function ChatPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center p-8 text-center animate-in fade-in duration-500">
      <div className="rounded-full bg-muted/50 p-6 mb-4">
        <MessageSquareDashed className="h-10 w-10 text-muted-foreground" />
      </div>
      <h3 className="text-xl font-semibold">欢迎来到 RAG 助手</h3>
      <p className="mt-2 text-muted-foreground max-w-sm">
        请在左侧选择一个历史会话，或者点击“新建对话”开始提问。
      </p>
    </div>
  );
}