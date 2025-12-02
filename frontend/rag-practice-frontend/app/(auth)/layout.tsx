import React from "react";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-zinc-50 dark:bg-zinc-950 p-4">
      <div className="w-full max-w-md space-y-8">
        {/* 这里可以放 Logo */}
        <div className="text-center">
          <div className="mx-auto h-12 w-12 bg-primary rounded-lg flex items-center justify-center text-primary-foreground font-bold text-xl">
            RP
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-50">
            RAG Practice
          </h2>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
            企业级 RAG 知识库与评测系统
          </p>
        </div>
        {children}
      </div>
    </div>
  );
}