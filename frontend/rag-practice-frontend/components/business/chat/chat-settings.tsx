"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { toast } from "sonner";
import { 
  Settings, 
  Save, 
  Loader2, 
  MessageSquare, 
  Bot, 
  Zap, 
  BookOpen,
  Search,
  Check,
  Sliders
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider"; // 假设有 Slider 组件，如果没有，需要用 Input type=number 替代
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

import { cn } from "@/lib/utils";
import { ChatSession, Knowledge } from "@/lib/types";
import { chatService } from "@/lib/services/chat";
import { knowledgeService } from "@/lib/services/knowledge";
import { useChatStore } from "@/lib/store"; // 🟢 引入

// 预设图标
const ICONS = [
  { value: "message-square", icon: MessageSquare },
  { value: "bot", icon: Bot },
  { value: "zap", icon: Zap },
  { value: "book-open", icon: BookOpen },
];

const formSchema = z.object({
  title: z.string().min(1, "标题不能为空").max(50, "标题过长"),
  icon: z.string(),
  knowledge_ids: z.array(z.number()).min(1, "至少选择一个知识库"),
  top_k: z.coerce.number().min(1).max(20), // [New] TopK 验证
});

interface ChatSettingsProps {
  session: ChatSession;
  onUpdate: () => void;
}

export function ChatSettings({ session, onUpdate }: ChatSettingsProps) {
  const [open, setOpen] = useState(false);
  const [knowledges, setKnowledges] = useState<Knowledge[]>([]);
  const [isLoadingKB, setIsLoadingKB] = useState(false);
  
  // 🟢 获取 Store action
  const updateSessionInList = useChatStore(state => state.updateSessionInList);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      title: session.title,
      icon: session.icon || "message-square",
      knowledge_ids: session.knowledge_ids || [session.knowledge_id],
      top_k: session.top_k || 3, // [New]
    },
  });

  // 加载知识库列表
  useEffect(() => {
    if (open) {
      const loadKB = async () => {
        setIsLoadingKB(true);
        try {
          const res = await knowledgeService.getAll();
          setKnowledges(res);
        } catch (error) {
          toast.error("加载知识库列表失败");
        } finally {
          setIsLoadingKB(false);
        }
      };
      loadKB();
      
      // Reset form with latest session data
      form.reset({
        title: session.title,
        icon: session.icon || "message-square",
        knowledge_ids: session.knowledge_ids || [session.knowledge_id],
        top_k: session.top_k || 3,
      });
    }
  }, [open, session, form]);

  const onSubmit = async (values: z.infer<typeof formSchema>) => {
    try {
      const updatedSession = await chatService.updateSession(session.id, values);
      
      toast.success("设置已更新");
      setOpen(false);
      
      // 1. 更新当前页面状态
      onUpdate(); 
      
      // 2. 🟢 更新全局列表状态 (SideBar)
      updateSessionInList(session.id, {
        title: updatedSession.title,
        icon: updatedSession.icon,
        updated_at: updatedSession.updated_at
      });
      
    } catch (error) {
      toast.error("更新失败");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" title="会话设置">
          <Settings className="h-4 w-4 text-muted-foreground" />
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>会话设置</DialogTitle>
          <DialogDescription>
            修改当前会话的标题、检索参数及关联知识库。
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 py-4">
            
            <div className="flex gap-4">
              {/* Icon Selector */}
              <FormField
                control={form.control}
                name="icon"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>图标</FormLabel>
                    <div className="flex gap-2">
                      {ICONS.map((item) => {
                        const Icon = item.icon;
                        return (
                          <div
                            key={item.value}
                            onClick={() => field.onChange(item.value)}
                            className={cn(
                              "flex h-9 w-9 cursor-pointer items-center justify-center rounded-md border transition-all hover:bg-muted",
                              field.value === item.value 
                                ? "border-primary bg-primary/10 text-primary" 
                                : "border-input bg-transparent"
                            )}
                          >
                            <Icon className="h-4 w-4" />
                          </div>
                        );
                      })}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />
              
              {/* Title Input */}
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormLabel>标题</FormLabel>
                    <FormControl>
                      <Input placeholder="输入会话标题..." {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Top K Slider [New] */}
            <FormField
              control={form.control}
              name="top_k"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="flex justify-between">
                    <span>单次检索切片数 (Top K)</span>
                    <span className="text-muted-foreground font-normal">{field.value}</span>
                  </FormLabel>
                  <FormControl>
                    {/* 使用 Input type=number 作为简单的替代，或者如果有 Slider 组件可以使用 */}
                    <div className="flex items-center gap-4">
                       <Sliders className="h-4 w-4 text-muted-foreground" />
                       <Input 
                         type="number" 
                         min={1} 
                         max={20} 
                         {...field} 
                         className="max-w-[100px]"
                       />
                       <span className="text-xs text-muted-foreground">建议值: 3-5</span>
                    </div>
                  </FormControl>
                  <FormDescription>
                    每次对话时，系统将从知识库中检索相关度最高的 K 个切片作为上下文。
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Knowledge Bases Multi-select */}
            <FormField
              control={form.control}
              name="knowledge_ids"
              render={({ field }) => (
                <FormItem className="flex flex-col">
                  <FormLabel>关联知识库 (支持多选)</FormLabel>
                  <Popover>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button
                          variant="outline"
                          role="combobox"
                          className={cn(
                            "w-full justify-between",
                            !field.value || field.value.length === 0 && "text-muted-foreground"
                          )}
                        >
                          {field.value && field.value.length > 0
                            ? `已选择 ${field.value.length} 个知识库`
                            : "选择知识库..."}
                          <Search className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-[460px] p-0" align="start">
                      <Command>
                        <CommandInput placeholder="搜索知识库..." />
                        <CommandList>
                          <CommandEmpty>未找到知识库。</CommandEmpty>
                          <CommandGroup>
                            {isLoadingKB ? (
                              <div className="p-4 text-center text-sm text-muted-foreground">加载中...</div>
                            ) : (
                              knowledges.map((kb) => (
                                <CommandItem
                                  value={kb.name}
                                  key={kb.id}
                                  onSelect={() => {
                                    const current = field.value || [];
                                    const isSelected = current.includes(kb.id);
                                    let next;
                                    if (isSelected) {
                                      // 至少保留一个
                                      if (current.length === 1) return; 
                                      next = current.filter((id) => id !== kb.id);
                                    } else {
                                      next = [...current, kb.id];
                                    }
                                    field.onChange(next);
                                  }}
                                >
                                  <div
                                    className={cn(
                                      "mr-2 flex h-4 w-4 items-center justify-center rounded-sm border border-primary",
                                      (field.value || []).includes(kb.id)
                                        ? "bg-primary text-primary-foreground"
                                        : "opacity-50 [&_svg]:invisible"
                                    )}
                                  >
                                    <Check className={cn("h-4 w-4")} />
                                  </div>
                                  <div className="flex flex-1 items-center justify-between">
                                    <span>{kb.name}</span>
                                    <Badge variant="outline" className="text-[10px] h-5">ID: {kb.id}</Badge>
                                  </div>
                                </CommandItem>
                              ))
                            )}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  <FormDescription>
                    选中多个知识库时，系统将同时在这些库中检索相关内容。
                  </FormDescription>
                  
                  {/* Selected Tags Display */}
                  <div className="flex flex-wrap gap-2 mt-2">
                    {field.value?.map(id => {
                      const kb = knowledges.find(k => k.id === id);
                      return kb ? (
                        <Badge key={id} variant="secondary" className="px-2 py-1">
                          {kb.name}
                        </Badge>
                      ) : null;
                    })}
                  </div>
                  
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="submit" disabled={form.formState.isSubmitting}>
                {form.formState.isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                <Save className="mr-2 h-4 w-4" /> 保存修改
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}