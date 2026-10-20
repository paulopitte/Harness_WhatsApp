import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "active" | "attention" | "critical" | "neutral";
}

export function Badge({ className, variant = "neutral", children, ...props }: BadgeProps) {
  const variantStyles = {
    active: "bg-emerald-950/80 text-emerald-400 border-emerald-800/80",
    attention: "bg-amber-950/80 text-amber-300 border-amber-800/80",
    critical: "bg-rose-950/80 text-rose-300 border-rose-800/80",
    neutral: "bg-slate-800/90 text-slate-300 border-slate-700/80",
  }[variant];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border font-mono tracking-tight",
        variantStyles,
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
}

