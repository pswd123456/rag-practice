export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="h-full w-full relative flex flex-col">
      {children}
    </div>
  );
}