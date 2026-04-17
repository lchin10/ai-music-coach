"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { redirectAfterAuth } from "@/lib/auth";

export default function OAuthReturn() {
  const router = useRouter();

  useEffect(() => {
    redirectAfterAuth(router);
  }, [router]);

  return <div className="p-6">Signing you in...</div>;
}