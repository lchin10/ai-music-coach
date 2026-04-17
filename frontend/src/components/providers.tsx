"use client";

import { Header } from "./header";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      {children}
    </>
  );
}