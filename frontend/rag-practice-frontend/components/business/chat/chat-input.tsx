// frontend/rag-practice-frontend/components/business/chat/chat-input.tsx
"use client";

import { useRef, useEffect, useState } from "react";
import { Send, StopCircle, ChevronDown, Bot, FileText } from "lucide-react"; // 🟢 引入 FileText 图标
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface ModelOption {
  value: string;
  label: string;
}

// 🟢 [New] 预设 Prompt 列表
const PRESET_PROMPTS = [
  { value: "rag-default", label: "默认 (Default)" },
  { value: "rag-concise", label: "简炼 (Concise)" },
  { value: "rag-detailed", label: "详细 (Detailed)" },
  { value: "rag-creative", label: "创意 (Creative)" },
  { value: "rag-structure", label: "结构化 (Structure)" }
];

interface ChatInputProps {
  isLoading: boolean;
  onStop: () => void;
  onSend: (message: string) => void;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  modelOptions?: ModelOption[];
  // 🟢 [New] Prompt Props
  selectedPrompt?: string;
  onPromptChange?: (prompt: string) => void;
}

export function ChatInput({ 
  isLoading, 
  onStop, 
  onSend, 
  selectedModel,
  onModelChange,
  modelOptions = [],
  selectedPrompt, // 🟢
  onPromptChange  // 🟢
}: ChatInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize logic
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    onSend(input);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  // 获取当前模型名称
  const currentModelLabel = modelOptions.find(m => m.value === selectedModel)?.label || selectedModel;
  
  // 🟢 获取当前 Prompt 名称
  const currentPromptLabel = PRESET_PROMPTS.find(p => p.value === selectedPrompt)?.label || selectedPrompt || "Default";

  return (
    <div className="mx-auto w-full max-w-3xl p-4">
      <div className="relative flex flex-col gap-2 rounded-xl border bg-background p-3 shadow-sm focus-within:ring-1 focus-within:ring-ring">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入您的问题 (Shift + Enter 换行)..."
          className="min-h-[48px] w-full resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 p-1"
          rows={1}
        />
        
        {/* Footer Area: Model Selector & Actions */}
        <div className="flex justify-between items-center pt-2">
          
          <div className="flex gap-2 items-center">
            {/* 左侧 1：模型选择器 */}
            {onModelChange && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs text-muted-foreground hover:text-foreground px-2">
                    <Bot className="h-3.5 w-3.5" />
                    <span>{currentModelLabel}</span>
                    <ChevronDown className="h-3 w-3 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {modelOptions.map((model) => (
                    <DropdownMenuItem 
                      key={model.value} 
                      onClick={() => onModelChange(model.value)}
                      className={cn("text-xs cursor-pointer", selectedModel === model.value && "bg-accent")}
                    >
                      {model.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {/* 🟢 左侧 2：Prompt 选择器 */}
            {onPromptChange && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 gap-1 text-xs text-muted-foreground hover:text-foreground px-2">
                    <FileText className="h-3.5 w-3.5" />
                    <span className="truncate max-w-[100px]">{currentPromptLabel}</span>
                    <ChevronDown className="h-3 w-3 opacity-50" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-56">
                  <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">选择或输入 Prompt ID</DropdownMenuLabel>
                  
                  {/* 自定义输入区 */}
                  <div className="px-2 py-1.5 border-b mb-1">
                    <input 
                      className="w-full text-xs bg-muted/30 px-2 py-1 rounded border-transparent focus:border-primary focus:outline-none transition-colors" 
                      placeholder="自定义 (如 rag-v2-test)..."
                      value={selectedPrompt}
                      onChange={(e) => onPromptChange(e.target.value)}
                      onClick={(e) => e.stopPropagation()} // 防止点击输入框关闭菜单
                    />
                  </div>

                  {PRESET_PROMPTS.map((prompt) => (
                    <DropdownMenuItem 
                      key={prompt.value} 
                      onClick={() => onPromptChange(prompt.value)}
                      className={cn("text-xs cursor-pointer", selectedPrompt === prompt.value && "bg-accent")}
                    >
                      {prompt.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>

          {/* 右侧：发送按钮 */}
          <div>
            {isLoading ? (
              <Button
                size="icon"
                variant="destructive"
                className="h-8 w-8 rounded-lg"
                onClick={onStop}
              >
                <StopCircle className="h-4 w-4" />
              </Button>
            ) : (
              <Button
                size="icon"
                className="h-8 w-8 rounded-lg"
                onClick={handleSend}
                disabled={!input.trim()}
              >
                <Send className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </div>
      <div className="mt-2 text-center text-xs text-muted-foreground">
        RAG 可能会生成不准确的信息，请核对重要事实。
      </div>
    </div>
  );
}