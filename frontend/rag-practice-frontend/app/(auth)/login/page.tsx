"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import api from "@/lib/api";
import { useAuthStore } from "@/lib/store";

// 表单验证 Schema
const formSchema = z.object({
  email: z.string().email({ message: "请输入有效的邮箱地址" }),
  password: z.string().min(1, { message: "密码不能为空" }),
});

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuthStore();
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
      // 1. 获取 Token
      // 后端 OAuth2PasswordRequestForm 需要 form-urlencoded 格式
      const params = new URLSearchParams();
      params.append("username", values.email); // OAuth2 标准字段是 username
      params.append("password", values.password);

      const tokenRes = await api.post("/auth/access-token", params, {
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
      });

      const { access_token } = tokenRes.data;

      // 暂时先手动存入 store 以便后续请求带上 token
      // 注意：这里我们还没获取完整的 User 信息，稍后获取
      // 为了不破坏 store 类型，我们需要先获取用户信息再调用 store.login
      // 或者 store.login 支持先只存 token。根据目前的 store.ts，需要传入 user 对象。
      
      // 临时保存 token 到 API header (虽然拦截器会读 store，但 store 还没更新)
      // 我们手动发一个带 Header 的请求获取用户信息
      const userRes = await api.post("/auth/test-token", null, {
        headers: { Authorization: `Bearer ${access_token}` },
      });

      const user = userRes.data;

      // 2. 更新全局状态
      login(access_token, user);

      toast.success("登录成功");
      router.push("/knowledge"); // 登录后跳转到知识库列表
    } catch (error: any) {
      console.error(error);
      const msg = error.response?.data?.detail || "登录失败，请检查账号密码";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>登录账号</CardTitle>
        <CardDescription>请输入您的邮箱和密码以继续</CardDescription>
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
                    <Input placeholder="name@example.com" {...field} />
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
                    <Input type="password" placeholder="******" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button className="w-full" type="submit" disabled={isLoading}>
              {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              登录
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
            去注册
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}