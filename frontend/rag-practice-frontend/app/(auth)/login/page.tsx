"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { toast } from "sonner";
import { Loader2, LogIn } from "lucide-react";

import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  CardHeader, 
  CardTitle, 
  CardDescription,
  CardFooter 
} from "@/components/ui/card";

// 定义表单验证规则
const formSchema = z.object({
  email: z.string().email("请输入有效的邮箱地址"),
  password: z.string().min(6, "密码至少 6 位"),
});

export default function LoginPage() {
  const router = useRouter();
  const loginStore = useAuthStore((state) => state.login);
  const [isLoading, setIsLoading] = useState(false);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  });

  async function onSubmit(values: z.infer<typeof formSchema>) {
    setIsLoading(true);
    try {
      // 1. 构造 x-www-form-urlencoded 数据
      const formData = new URLSearchParams();
      formData.append("username", values.email);
      formData.append("password", values.password);

      // 2. 发起登录请求
      const loginRes = await api.post("/auth/access-token", formData, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      });

      const { access_token, token_type } = loginRes.data;

      if (!access_token) {
        throw new Error("登录失败：未收到 Token");
      }

      // 3. 验证 Token 并获取用户信息
      const userRes = await api.post("/auth/test-token", null, {
        headers: { Authorization: `${token_type} ${access_token}` },
      });

      const user = userRes.data;

      // 4. 更新全局状态
      loginStore(access_token, user);

      toast.success("登录成功");
      router.push("/knowledge");
    } catch (error: any) {
      console.error("Login Error:", error);
      if (error.response?.status === 400 || error.response?.status === 422) {
        toast.error("邮箱或密码错误");
      } else {
        toast.error(error.message || "登录服务暂不可用");
      }
    } finally {
      setIsLoading(false);
    }
  }

  // 布局修复：移除外层 div 和重复的 Logo/Header，直接返回 Card 内容
  // 父级 layout (AuthLayout) 会处理居中和背景
  return (
    <>
      <Card>
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl text-center">欢迎回来</CardTitle>
          <CardDescription className="text-center">
            请输入您的账号信息以继续
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>邮箱</FormLabel>
                    <FormControl>
                      <Input 
                        placeholder="name@example.com" 
                        {...field} 
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>密码</FormLabel>
                    <FormControl>
                      <Input 
                        type="password" 
                        {...field} 
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <Button 
                type="submit" 
                className="w-full" 
                disabled={isLoading}
              >
                {isLoading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <LogIn className="mr-2 h-4 w-4" />
                )}
                登 录
              </Button>
            </form>
          </Form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            还没有账号?{" "}
            <Link
              href="/register"
              className="text-primary hover:underline font-medium"
            >
              立即注册
            </Link>
          </p>
        </CardFooter>
      </Card>
      
      {/* 底部版权 - 放在 Card 外部，作为 layout flex 的子元素 */}
      <div className="text-center text-xs text-muted-foreground">
        &copy; 2025 RAG Practice. All rights reserved.
      </div>
    </>
  );
}