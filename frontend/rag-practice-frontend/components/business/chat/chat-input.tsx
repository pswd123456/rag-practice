"use client";

import { useRef, useEffect, useState } from "react";
import { Send, StopCircle, ChevronDown, Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export interface ModelOption {
  value: string;
  label: string;
}

interface ChatInputProps {
  isLoading: boolean;
  onStop: () => void;
  onSend: (message: string) => void;
  selectedModel?: string;
  onModelChange?: (model: string) => void;
  modelOptions?: ModelOption[];
}

export function ChatInput({ 
  isLoading, 
  onStop, 
  onSend, 
  selectedModel,
  onModelChange,
  modelOptions = []
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
          
          {/* 左侧：模型选择器 */}
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