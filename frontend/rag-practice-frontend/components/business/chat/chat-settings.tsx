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
  Check
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
import { Slider } from "@/components/ui/slider";
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
  top_k: z.coerce.number().min(1).max(20).default(5),
});

interface ChatSettingsProps {
  session: ChatSession;
  onUpdate: () => void;
}

export function ChatSettings({ session, onUpdate }: ChatSettingsProps) {
  const [open, setOpen] = useState(false);
  const [knowledges, setKnowledges] = useState<Knowledge[]>([]);
  const [isLoadingKB, setIsLoadingKB] = useState(false);

  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      title: session.title,
      icon: session.icon || "message-square",
      knowledge_ids: session.knowledge_ids || [session.knowledge_id],
      top_k: 5,
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
        top_k: 5,
      });
    }
  }, [open, session, form]);

  const onSubmit = async (values: z.infer<typeof formSchema>) => {
    try {
      // @ts-ignore
      await chatService.updateSession(session.id, values);
      toast.success("设置已更新");
      setOpen(false);
      onUpdate();
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
            修改当前会话的标题、图标及检索偏好。
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 py-4">
            
            {/* Top Row: Icon & Title */}
            <div className="flex gap-4">
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

            {/* Knowledge Bases Multi-select */}
            <FormField
              control={form.control}
              name="knowledge_ids"
              render={({ field }) => (
                <FormItem className="flex flex-col">
                  <FormLabel>关联知识库</FormLabel>
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
                                    const current = (field.value as number[]) || [];
                                    const isSelected = current.includes(kb.id);
                                    let next;
                                    if (isSelected) {
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
                                      ((field.value as number[]) || []).includes(kb.id)
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
                  
                  <div className="flex flex-wrap gap-2 mt-2">
                    {/* 显式转换类型以避免 TS 错误 */}
                    {(field.value as number[])?.map(id => {
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

            {/* Top K Slider */}
            <FormField
              control={form.control}
              name="top_k"
              render={({ field }) => (
                <FormItem>
                  <div className="flex justify-between items-center mb-1">
                    <FormLabel>单路召回数量 (Top K)</FormLabel>
                    <span className="text-sm font-medium text-muted-foreground w-8 text-right">
                      {/* 显式转换为 number 或 string */}
                      {field.value as number}
                    </span>
                  </div>
                  <FormControl>
                    <Slider
                      min={1}
                      max={20}
                      step={1}
                      // Slider 需要 number[]，这里将 unknown 强转
                      defaultValue={[field.value as number]}
                      onValueChange={(vals) => field.onChange(vals[0])}
                    />
                  </FormControl>
                  <FormDescription>
                    每次检索从向量库召回的切片数量，数量越多信息越全，但可能引入噪声。
                  </FormDescription>
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