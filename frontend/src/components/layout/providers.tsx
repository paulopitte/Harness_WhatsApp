"use client";

import * as React from "react";
import { SWRConfig } from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher: swrFetcher,
        revalidateOnFocus: true,
        dedupingInterval: 3000,
      }}
    >
      {children}
    </SWRConfig>
  );
}

