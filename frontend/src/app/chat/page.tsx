import { Topbar } from "@/components/layout/Topbar";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { SemanticSearchPanel } from "@/components/search/SemanticSearchPanel";

export default function ChatPage() {
  return (
    <>
      <Topbar title="AI Assistant" />
      <main className="mx-auto flex h-[calc(100vh-69px)] w-full max-w-4xl animate-fade-in flex-col gap-4 overflow-y-auto p-6 sm:p-8">
        <p className="shrink-0 max-w-xl text-sm text-content-secondary">
          Ask questions about what you&apos;ve learned and get answers grounded in your saved
          resources, with citations linking back to the source.
        </p>

        <SemanticSearchPanel />

        <div className="min-h-[420px] flex-1">
          <ChatPanel />
        </div>
      </main>
    </>
  );
}
