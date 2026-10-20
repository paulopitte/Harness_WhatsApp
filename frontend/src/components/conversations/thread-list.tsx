"use client";

import * as React from "react";
import { Search, Bot, UserCheck, Phone } from "lucide-react";
import type { ThreadItem } from "@/lib/types";
import { formatPhoneNumber, formatTimestamp, cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";

interface ThreadListProps {
  threads: ThreadItem[];
  selectedThreadId: string | null;
  onSelectThread: (threadId: string) => void;
  isLoading: boolean;
}

export function ThreadList({
  threads,
  selectedThreadId,
  onSelectThread,
  isLoading,
}: ThreadListProps) {
  const [searchTerm, setSearchTerm] = React.useState("");
  const [filteredThreads, setFilteredThreads] = React.useState<ThreadItem[]>(threads);
  const [, startTransition] = React.useTransition();

  React.useEffect(() => {
    startTransition(() => {
      if (!searchTerm.trim()) {
        setFilteredThreads(threads);
      } else {
        const query = searchTerm.toLowerCase();
        setFilteredThreads(
          threads.filter(
            (t) =>
              t.phone_number.toLowerCase().includes(query) ||
              (t.last_message && t.last_message.toLowerCase().includes(query))
          )
        );
      }
    });
  }, [searchTerm, threads]);

  return (
    <aside className="w-80 shrink-0 border-r border-slate-800 bg-slate-950 flex flex-col h-full">
      {/* Search Header */}
      <div className="p-3 border-b border-slate-800/80">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <Input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Buscar por telefone ou texto..."
            className="pl-8 h-8 text-xs bg-slate-900 border-slate-800"
          />
        </div>
      </div>

      {/* List Viewport */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60 [content-visibility:auto]">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="animate-pulse space-y-2">
                <div className="h-3 bg-slate-800 rounded w-24" />
                <div className="h-2.5 bg-slate-800/60 rounded w-full" />
              </div>
            ))}
          </div>
        ) : filteredThreads.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            {searchTerm
              ? "Nenhuma conversa corresponde aos termos pesquisados."
              : "Nenhuma conversa pendente. Novas mensagens do WhatsApp aparecerão aqui automaticamente."}
          </div>
        ) : (
          filteredThreads.map((thread) => {
            const isSelected = thread.id === selectedThreadId;
            return (
              <button
                key={thread.id}
                onClick={() => onSelectThread(thread.id)}
                className={cn(
                  "w-full text-left p-3 transition-colors flex items-start gap-2.5 cursor-pointer",
                  isSelected
                    ? "bg-slate-800/90 border-l-2 border-emerald-500"
                    : "hover:bg-slate-900/60"
                )}
              >
                <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 shrink-0 mt-0.5">
                  <Phone className="w-3.5 h-3.5 text-slate-400" />
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs font-mono font-medium text-slate-200 truncate">
                      {formatPhoneNumber(thread.phone_number)}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500 shrink-0">
                      {formatTimestamp(thread.updated_at).split(" ")[0]}
                    </span>
                  </div>

                  <p className="text-[11px] text-slate-400 truncate mt-0.5">
                    {thread.last_message || "Sem mensagens registradas"}
                  </p>

                  <div className="flex items-center gap-1.5 mt-1.5">
                    <Badge
                      variant={
                        thread.mode === "bot"
                          ? "active"
                          : thread.mode === "human"
                          ? "attention"
                          : "neutral"
                      }
                      className="text-[10px] py-0 px-1.5"
                    >
                      {thread.mode === "bot" ? (
                        <>
                          <Bot className="w-2.5 h-2.5" /> IA Ativa
                        </>
                      ) : thread.mode === "human" ? (
                        <>
                          <UserCheck className="w-2.5 h-2.5" /> Humano
                        </>
                      ) : (
                        "Pausado"
                      )}
                    </Badge>
                  </div>
                </div>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}

