"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";

export default function UploadConfirmationPage() {
  const router = useRouter();

  return (
    <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <p className="text-gray-300">Your PDF has been uploaded and is currently being processed. Check the status of your piece in your profile page</p>                 
        <button 
          className="w-full text-blue-500 hover:text-blue-700 mt-4 cursor-pointer"
          onClick={() => router.push('/profile')}
        >
          Go to Profile
        </button>
      </div>
    </main>
  );
}