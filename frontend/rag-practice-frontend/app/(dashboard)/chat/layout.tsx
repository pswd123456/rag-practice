export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // 移除原有的 flex 布局和 ChatSidebar
    // 直接返回 children，占满父容器的高度
    <div className="h-[calc(100vh-4rem)] w-full relative">
      {children}
    </div>
  );
}