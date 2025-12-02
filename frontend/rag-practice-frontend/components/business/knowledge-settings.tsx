"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { toast } from "sonner";
import { Loader2, UserPlus, Trash2, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

import { knowledgeService, Member } from "@/lib/services/knowledge";
import { Knowledge, UserKnowledgeRole } from "@/lib/types";

// --- Schema Definitions ---
const updateSchema = z.object({
  name: z.string().min(2, "名称至少 2 个字符"),
  description: z.string().optional(),
});

const memberSchema = z.object({
  email: z.string().email("请输入有效的邮箱"),
  role: z.enum([UserKnowledgeRole.EDITOR, UserKnowledgeRole.VIEWER]),
});

// --- Component 1: Basic Settings ---

interface KnowledgeBasicFormProps {
  knowledge: Knowledge;
  onUpdate: () => void;
}

export function KnowledgeBasicForm({ knowledge, onUpdate }: KnowledgeBasicFormProps) {
  const isOwner = knowledge.role === UserKnowledgeRole.OWNER;
  const isEditor = knowledge.role === UserKnowledgeRole.EDITOR;
  const canEdit = isOwner || isEditor;

  const form = useForm<z.infer<typeof updateSchema>>({
    resolver: zodResolver(updateSchema),
    defaultValues: {
      name: knowledge.name,
      description: knowledge.description || "",
    },
  });

  // 监听 knowledge 变化，更新表单默认值
  useEffect(() => {
    form.reset({
      name: knowledge.name,
      description: knowledge.description || "",
    });
  }, [knowledge, form]);

  const onSubmit = async (values: z.infer<typeof updateSchema>) => {
    try {
      await knowledgeService.update(knowledge.id, values);
      toast.success("基本信息已更新");
      onUpdate(); // 触发父组件刷新数据
    } catch (error: any) {
      console.error(error);
      toast.error("更新失败: " + (error.response?.data?.detail || "未知错误"));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>基本设置</CardTitle>
        <CardDescription>修改知识库的名称和描述信息。</CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>名称</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={!canEdit} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>描述</FormLabel>
                  <FormControl>
                    <Textarea {...field} disabled={!canEdit} className="resize-none min-h-[100px]" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {canEdit && (
              <div className="flex justify-end">
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  保存修改
                </Button>
              </div>
            )}
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

// --- Component 2: Member Management ---

interface MemberManagementProps {
  knowledge: Knowledge;
}

export function MemberManagement({ knowledge }: MemberManagementProps) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(false);
  const isOwner = knowledge.role === UserKnowledgeRole.OWNER;

  const form = useForm<z.infer<typeof memberSchema>>({
    resolver: zodResolver(memberSchema),
    defaultValues: {
      email: "",
      role: UserKnowledgeRole.VIEWER,
    },
  });

  const fetchMembers = async () => {
    try {
      setLoading(true);
      const data = await knowledgeService.getMembers(knowledge.id);
      setMembers(data);
    } catch (e) {
      console.error(e);
      toast.error("获取成员列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMembers();
  }, [knowledge.id]);

  const onAddMember = async (values: z.infer<typeof memberSchema>) => {
    try {
      await knowledgeService.addMember(knowledge.id, values.email, values.role);
      toast.success(`已邀请 ${values.email}`);
      form.reset();
      fetchMembers();
    } catch (error: any) {
      const msg = error.response?.data?.detail || "邀请失败";
      toast.error(msg);
    }
  };

  const onRemoveMember = async (userId: number) => {
    try {
      await knowledgeService.removeMember(knowledge.id, userId);
      toast.success("成员已移除");
      fetchMembers();
    } catch (error) {
      toast.error("移除失败");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>成员管理</CardTitle>
        <CardDescription>查看和管理拥有此知识库访问权限的用户。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 邀请表单 (仅 Owner 可见) */}
        {isOwner ? (
          <div className="flex gap-4 items-start border-b pb-6">
            <Form {...form}>
              <form 
                onSubmit={form.handleSubmit(onAddMember)} 
                className="flex-1 flex flex-col md:flex-row gap-3 items-start md:items-end"
              >
                <FormField
                  control={form.control}
                  name="email"
                  render={({ field }) => (
                    <FormItem className="flex-1 w-full">
                      <FormLabel>邀请新成员 (邮箱)</FormLabel>
                      <FormControl>
                        <Input placeholder="user@example.com" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="role"
                  render={({ field }) => (
                    <FormItem className="w-full md:w-[140px]">
                      <FormLabel>权限</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={UserKnowledgeRole.EDITOR}>协作者</SelectItem>
                          <SelectItem value={UserKnowledgeRole.VIEWER}>访客</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
                <Button type="submit" className="mb-0.5" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4 mr-2" />}
                  邀请
                </Button>
              </form>
            </Form>
          </div>
        ) : (
          <div className="bg-muted/30 p-3 rounded-md text-sm text-muted-foreground text-center">
            您是协作者或访客，暂无权限邀请新成员。
          </div>
        )}

        {/* 成员列表 */}
        <div className="space-y-4">
          {loading ? (
            <div className="text-center py-4 text-muted-foreground">加载中...</div>
          ) : (
            members.map((member) => (
              <div key={member.user_id} className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/30 transition-colors">
                <div className="flex items-center gap-3">
                  <Avatar className="h-9 w-9">
                    <AvatarFallback className="bg-primary/10 text-primary font-medium">
                      {member.full_name?.slice(0, 1) || member.email.slice(0, 1).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="text-sm font-medium leading-none">{member.full_name || "用户"}</p>
                    <p className="text-sm text-muted-foreground">{member.email}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={member.role === UserKnowledgeRole.OWNER ? "default" : "secondary"}>
                    {member.role === UserKnowledgeRole.OWNER ? "所有者" : 
                     member.role === UserKnowledgeRole.EDITOR ? "协作者" : "访客"}
                  </Badge>
                  
                  {isOwner && member.role !== UserKnowledgeRole.OWNER && (
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      className="text-muted-foreground hover:text-destructive h-8 w-8"
                      onClick={() => onRemoveMember(member.user_id)}
                      title="移除成员"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
          {!loading && members.length === 0 && (
            <div className="text-center text-muted-foreground text-sm">暂无成员</div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}