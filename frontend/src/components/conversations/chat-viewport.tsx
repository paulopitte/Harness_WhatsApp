"use client";

import * as React from "react";
import type { ChatMessage, ThreadItem, ThreadMode } from "@/lib/types";
import { formatPhoneNumber, formatTimestamp, cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Bot, UserCheck, Send, AlertCircle } from "lucide-react";

interface ChatViewportProps {
  thread: ThreadItem | null;
  messages: ChatMessage[];
  isLoading: boolean;
  onToggleHandoff: (newMode: ThreadMode) => Promise<void>;
  onSendMessage: (text: string) => Promise<void>;
}

export function ChatViewport({
  thread,
  messages,
  isLoading,
  onToggleHandoff,
  onSendMessage,
}: ChatViewportProps) {
  const [inputText, setInputText] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [toggling, setToggling] = React.useState(false);
  const scrollRef = React.useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (!thread) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#0b0f19]">
        <div className="w-12 h-12 rounded-full bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 mb-3">
          <Bot className="w-6 h-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-200">
          Nenhuma conversa selecionada
        </h3>
        <p className="text-xs text-slate-400 max-w-sm mt-1">
          Selecione uma conversa na lista ao lado para inspecionar o histórico e assumir o atendimento.
        </p>
      </div>
    );
  }

  const isHumanMode = thread.mode === "human";

  const handleToggle = async () => {
    try {
      setToggling(true);
      await onToggleHandoff(isHumanMode ? "bot" : "human");
    } finally {
      setToggling(false);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || sending) return;

    try {
      setSending(true);
      await onSendMessage(inputText.trim());
      setInputText("");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#0b0f19]">
      {/* Thread Header */}
      <div className="h-14 px-4 border-b border-slate-800/80 bg-slate-950/60 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-mono text-xs font-semibold text-slate-300">
            {thread.phone_number.slice(-2)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-semibold text-slate-100">
                {formatPhoneNumber(thread.phone_number)}
              </span>
              <Badge variant={isHumanMode ? "attention" : "active"}>
                {isHumanMode ? "Atendimento Humano" : "IA Ativa"}
              </Badge>
            </div>
            <p className="text-[10px] text-slate-500 font-mono">
              Thread ID: {thread.id}
            </p>
          </div>
        </div>

        {/* Handoff Toggle Button */}
        <div>
          <Button
            size="sm"
            variant={isHumanMode ? "primary" : "secondary"}
            onClick={handleToggle}
            disabled={toggling}
            className="text-xs flex items-center gap-1.5"
          >
            {isHumanMode ? (
              <>
                <Bot className="w-3.5 h-3.5 text-emerald-300" />
                <span>Devolver ao assistente</span>
              </>
            ) : (
              <>
                <UserCheck className="w-3.5 h-3.5 text-amber-400" />
                <span>Assumir conversa</span>
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Mode Banner Alert */}
      {isHumanMode ? (
        <div className="px-4 py-2 bg-amber-950/40 border-b border-amber-900/50 flex items-center justify-between text-xs text-amber-300">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
            <span>
              O bot está silenciado para este contato. As respostas enviadas aqui serão assinadas pelo operador humano.
            </span>
          </div>
        </div>
      ) : null}

      {/* Messages Scroll Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-3.5"
      >
        {isLoading ? (
          <div className="space-y-3 p-4">
            <div className="h-10 bg-slate-800/40 rounded w-2/3" />
            <div className="h-12 bg-slate-800/40 rounded w-3/4 ml-auto" />
            <div className="h-8 bg-slate-800/40 rounded w-1/2" />
          </div>
        ) : messages.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-500">
            Nenhuma mensagem neste histórico. O histórico deste cliente aparecerá aqui conforme a conversa progredir.
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.role === "user";
            return (
              <div
                key={msg.id}
                className={cn("flex flex-col max-w-[75%]", isUser ? "mr-auto" : "ml-auto")}
              >
                <div className="flex items-center gap-1.5 mb-1 px-1 text-[10px] text-slate-500 font-mono">
                  {isUser ? (
                    <span>Cliente ({formatPhoneNumber(thread.phone_number)})</span>
                  ) : (
                    <span className="flex items-center gap-1 text-emerald-400">
                      <Bot className="w-3 h-3" /> Assistente / IA
                    </span>
                  )}
                  <span>•</span>
                  <span>{formatTimestamp(msg.created_at).split(" ")[1]}</span>
                </div>

                <div
                  className={cn(
                    "p-3 rounded-lg text-xs leading-relaxed break-words shadow-xs border",
                    isUser
                      ? "bg-slate-900/90 text-slate-100 border-slate-800 rounded-tl-none"
                      : "bg-emerald-950/50 text-emerald-50 border-emerald-800/50 rounded-tr-none"
                  )}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Chat Composer */}
      <form
        onSubmit={handleSend}
        className="p-3 border-t border-slate-800/80 bg-slate-950/80 flex items-center gap-2"
      >
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={
            isHumanMode
              ? "Digite uma mensagem para responder como atendente humano..."
              : "Assuma a conversa para responder manualmente como operador..."
          }
          disabled={!isHumanMode || sending}
          className="flex-1 h-9 px-3 text-xs rounded-md bg-slate-900 border border-slate-800 text-slate-100 placeholder:text-slate-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <Button
          type="submit"
          size="sm"
          disabled={!isHumanMode || !inputText.trim() || sending}
          className="h-9 px-4 text-xs flex items-center gap-1.5"
        >
          <Send className="w-3.5 h-3.5" />
          <span>Enviar</span>
        </Button>
      </form>
    </div>
  );
}

