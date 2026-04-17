"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";

export default function UploadPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const router = useRouter();

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    const pdfFile = files.find(file => file.type === 'application/pdf');

    if (pdfFile) {
      setSelectedFile(pdfFile);
    } else {
      alert('Please upload a PDF file only.');
    }
  }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
    } else if (file) {
      alert('Please select a PDF file only.');
    }
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);

    try {
      // TODO: Implement actual upload logic
      // For now, just simulate upload and redirect
      await new Promise(resolve => setTimeout(resolve, 2000));

      // Redirect to practice plan page or show success
      router.push('/practice-plan');
    } catch (error) {
      console.error('Upload failed:', error);
      alert('Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const openFileDialog = () => {
    document.getElementById('file-input')?.click();
  };

  return (
    <main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <div className="text-center">
          <h1 className="text-4xl font-semibold tracking-tight text-white">Upload Sheet Music</h1>
          <p className="mt-4 text-lg text-zinc-400">
            Drop your PDF sheet music here or click to browse. We'll analyze it and create a personalized practice plan.
          </p>
        </div>

        <div
          className={`relative rounded-[2rem] border-2 border-dashed p-12 text-center transition-all duration-200 ${
            isDragOver
              ? 'border-indigo-400 bg-indigo-500/10'
              : 'border-zinc-600 bg-zinc-900/50'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            id="file-input"
            type="file"
            accept=".pdf"
            onChange={handleFileSelect}
            className="hidden"
          />

          <div className="flex flex-col items-center gap-6">
            <div className="text-6xl">📄</div>

            {selectedFile ? (
              <div className="space-y-2">
                <p className="text-lg font-medium text-white">{selectedFile.name}</p>
                <p className="text-sm text-zinc-400">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-xl font-medium text-white">
                  {isDragOver ? 'Drop your PDF here' : 'Drag & drop your PDF'}
                </p>
                <p className="text-sm text-zinc-400">or</p>
              </div>
            )}

            <button
              onClick={openFileDialog}
              className="rounded-2xl bg-zinc-800 px-6 py-3 text-sm font-semibold text-white transition hover:bg-zinc-700 cursor-pointer"
            >
              Browse Files
            </button>
          </div>
        </div>

        <div className="flex justify-center">
          <button
            onClick={handleUpload}
            disabled={!selectedFile || isUploading}
            className={`rounded-2xl px-8 py-4 text-lg font-semibold transition ${
              selectedFile && !isUploading
                ? 'bg-indigo-500 text-white hover:bg-indigo-400 cursor-pointer'
                : 'bg-zinc-800 text-zinc-500 cursor-not-allowed'
            }`}
          >
            {isUploading ? 'Analyzing...' : 'Upload & Analyze'}
          </button>
        </div>

        <div className="text-center text-sm text-zinc-500">
          <p>Supported format: PDF only</p>
          <p className="mt-1">Maximum file size: 50MB</p>
        </div>
      </div>
    </main>
  );
}