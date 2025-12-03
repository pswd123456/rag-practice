import { useState } from "react";
import ReactMarkdown from "react-markdown"; // 假设用户已安装
import { Bot, User, FileText, ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Message, Source } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "flex w-full gap-4 p-4 md:p-6",
        isUser ? "flex-row-reverse bg-muted/30" : "bg-background"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full border",
          isUser ? "bg-primary text-primary-foreground" : "bg-zinc-100 dark:bg-zinc-800"
        )}
      >
        {isUser ? <User className="h-5 w-5" /> : <Bot className="h-5 w-5" />}
      </div>

      {/* Content Area */}
      <div className={cn("flex-1 space-y-2 overflow-hidden", isUser ? "text-right" : "text-left")}>
        {/* Name & Time */}
        <div className={cn("flex items-center gap-2 text-xs text-muted-foreground", isUser && "flex-row-reverse")}>
          <span className="font-semibold">{isUser ? "You" : "RAG Assistant"}</span>
          {/* <span>{message.created_at ? format(new Date(message.created_at), "HH:mm") : ""}</span> */}
        </div>

        {/* Message Body */}
        <div className={cn("prose dark:prose-invert max-w-none text-sm break-words", isUser && "ml-auto")}>
          {isUser ? (
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            <ReactMarkdown
              components={{
                // 自定义 Markdown 渲染以适配 Shadcn 风格
                p: ({ children }) => <p className="mb-2 last:mb-0 leading-7">{children}</p>,
                ul: ({ children }) => <ul className="my-2 ml-4 list-disc">{children}</ul>,
                ol: ({ children }) => <ol className="my-2 ml-4 list-decimal">{children}</ol>,
                li: ({ children }) => <li className="mt-1">{children}</li>,
                code: ({ className, children, ...props }) => {
                  const match = /language-(\w+)/.exec(className || "");
                  const isInline = !match;
                  return isInline ? (
                    <code className="bg-muted px-1.5 py-0.5 rounded font-mono text-xs" {...props}>
                      {children}
                    </code>
                  ) : (
                    <pre className="bg-zinc-950 text-zinc-50 p-4 rounded-lg overflow-x-auto my-4 text-xs">
                      <code className={className} {...props}>
                        {children}
                      </code>
                    </pre>
                  );
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          )}
        </div>

        {/* Actions (Copy, etc) */}
        {!isUser && !message.isStreaming && (
          <div className="flex items-center gap-2 pt-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCopy}>
              {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3 text-muted-foreground" />}
            </Button>
          </div>
        )}

        {/* Sources Accordion */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-4 rounded-md border bg-muted/20">
            <button
              onClick={() => setSourcesOpen(!sourcesOpen)}
              className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
            >
              <div className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5" />
                <span>参考来源 ({message.sources.length})</span>
              </div>
              {sourcesOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            </button>
            
            {sourcesOpen && (
              <div className="border-t px-3 py-2 space-y-2 animate-in slide-in-from-top-1 fade-in duration-200">
                {message.sources.map((source, idx) => (
                  <SourceItem key={idx} source={source} index={idx} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function SourceItem({ source, index }: { source: Source; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="group rounded border bg-background p-2 text-xs shadow-sm transition-all">
      <div 
        className="flex cursor-pointer items-start justify-between gap-2"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2 overflow-hidden">
          <Badge variant="outline" className="h-5 min-w-5 px-1 text-[10px] text-muted-foreground">
            {index + 1}
          </Badge>
          <span className="font-medium truncate text-primary/80" title={source.filename}>
            {source.filename}
          </span>
          {source.score && (
            <span className="text-[10px] text-muted-foreground shrink-0">
              ({(source.score * 100).toFixed(1)}%)
            </span>
          )}
        </div>
      </div>
      
      {/* 始终渲染内容，通过 CSS 控制显示，或者条件渲染 */}
      {expanded && (
        <div className="mt-2 border-t pt-2 text-muted-foreground/80 leading-relaxed bg-muted/10 p-1.5 rounded">
          {source.content}
          {source.page && (
            <div className="mt-1 text-[10px] text-right text-muted-foreground/60">
              Page: {source.page}
            </div>
          )}
        </div>
      )}
    </div>
  );
}