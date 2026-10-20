"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  MessageSquare,
  ListOrdered,
  ShieldAlert,
  Bot,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navigationItems = [
  {
    name: "Dashboard",
    href: "/",
    icon: LayoutDashboard,
  },
  {
    name: "Conversas",
    href: "/conversations",
    icon: MessageSquare,
  },
  {
    name: "Fila & DLQ",
    href: "/queue",
    icon: ListOrdered,
  },
  {
    name: "Segurança",
    href: "/security",
    icon: ShieldAlert,
  },
  {
    name: "Agentes",
    href: "/agents",
    icon: Bot,
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 shrink-0 border-r border-slate-800/80 bg-slate-950 flex flex-col justify-between select-none">
      <div>
        {/* Brand Header */}
        <div className="h-14 px-4 flex items-center gap-2.5 border-b border-slate-800/80">
          <div className="w-7 h-7 rounded bg-emerald-600/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-semibold tracking-tight text-slate-100 flex items-center gap-1.5">
              <span>Harness AI</span>
              <span className="text-[10px] px-1 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800/60 font-mono">
                v0.1
              </span>
            </div>
            <p className="text-[10px] text-slate-500 tracking-tight">WhatsApp Cockpit</p>
          </div>
        </div>

        {/* Nav Links */}
        <nav className="p-2 space-y-0.5">
          {navigationItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-md text-xs font-medium transition-colors",
                  isActive
                    ? "bg-slate-800/90 text-emerald-400 font-semibold border border-slate-700/60 shadow-xs"
                    : "text-slate-400 hover:text-slate-100 hover:bg-slate-900/80"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4",
                    isActive ? "text-emerald-400" : "text-slate-500"
                  )}
                />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Footer Info */}
      <div className="p-3 border-t border-slate-800/80 text-[11px] text-slate-500">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="font-mono text-[10px]">LangGraph Online</span>
        </div>
        <p className="mt-1 text-[10px] text-slate-600">Admin API :8001</p>
      </div>
    </aside>
  );
}

