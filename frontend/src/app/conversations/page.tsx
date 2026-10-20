"use client";

import * as React from "react";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import { apiClient } from "@/lib/api-client";
import type { ChatMessage, ThreadItem, ThreadMode } from "@/lib/types";
import { ThreadList } from "@/components/conversations/thread-list";
import { ChatViewport } from "@/components/conversations/chat-viewport";
import { CustomerPanel } from "@/components/conversations/customer-panel";
import { Skeleton } from "@/components/ui/skeleton";

function ConversationsContent() {
  const searchParams = useSearchParams();
  const queryThreadId = searchParams.get("thread");

  const { data: threads, isLoading: loadingThreads } = useSWR<ThreadItem[]>(
    "/admin/threads",
    swrFetcher,
    { refreshInterval: 4000 }
  );

  const [selectedThreadId, setSelectedThreadId] = React.useState<string | null>(
    queryThreadId || null
  );

  React.useEffect(() => {
    if (queryThreadId) {
      setSelectedThreadId(queryThreadId);
    } else if (threads && threads.length > 0 && !selectedThreadId) {
      setSelectedThreadId(threads[0].id);
    }
  }, [queryThreadId, threads, selectedThreadId]);

  const {
    data: messages,
    isLoading: loadingMessages,
    mutate: mutateMessages,
  } = useSWR<ChatMessage[]>(
    selectedThreadId
      ? `/admin/threads/${encodeURIComponent(selectedThreadId)}/messages`
      : null,
    swrFetcher,
    { refreshInterval: 3000 }
  );

  const { mutate } = useSWRConfig();

  const selectedThread =
    threads?.find((t) => t.id === selectedThreadId) || null;

  const handleToggleHandoff = async (newMode: ThreadMode) => {
    if (!selectedThreadId) return;

    // Optimistic UI update in thread list
    if (threads) {
      const updated = threads.map((t) =>
        t.id === selectedThreadId ? { ...t, mode: newMode } : t
      );
      mutate("/admin/threads", updated, false);
    }

    try {
      await apiClient.setThreadHandoff(selectedThreadId, newMode);
      mutate("/admin/threads");
      mutate(`/admin/threads/${encodeURIComponent(selectedThreadId)}/facts`);
    } catch (err) {
      mutate("/admin/threads");
      alert(`Falha ao alterar modo de atendimento: ${err}`);
    }
  };

  const handleSendMessage = async (text: string) => {
    if (!selectedThreadId) return;

    const optimisticMsg: ChatMessage = {
      id: `temp_${Date.now()}`,
      thread_id: selectedThreadId,
      role: "assistant",
      content: text,
      created_at: new Date().toISOString(),
    };

    if (messages) {
      mutateMessages([...messages, optimisticMsg], false);
    }

    try {
      await apiClient.sendOperatorMessage(selectedThreadId, text);
      mutateMessages();
      mutate("/admin/threads");
    } catch (err) {
      mutateMessages();
      alert(`Erro ao enviar mensagem: ${err}`);
    }
  };

  return (
    <div className="flex h-full border border-slate-800 rounded-md overflow-hidden bg-slate-950">
      {/* Col 1: Thread List */}
      <ThreadList
        threads={threads || []}
        selectedThreadId={selectedThreadId}
        onSelectThread={(id) => setSelectedThreadId(id)}
        isLoading={loadingThreads}
      />

      {/* Col 2: Chat Viewport */}
      <ChatViewport
        thread={selectedThread}
        messages={messages || []}
        isLoading={loadingMessages}
        onToggleHandoff={handleToggleHandoff}
        onSendMessage={handleSendMessage}
      />

      {/* Col 3: Customer Intelligence Panel */}
      <CustomerPanel threadId={selectedThreadId} />
    </div>
  );
}

export default function ConversationsPage() {
  return (
    <Suspense
      fallback={
        <div className="h-full flex items-center justify-center p-8 bg-slate-950 border border-slate-800 rounded-md">
          <Skeleton className="h-12 w-64" />
        </div>
      }
    >
      <ConversationsContent />
    </Suspense>
  );
}

