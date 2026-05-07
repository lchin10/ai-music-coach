"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import useSession from "@/lib/userSession";

export default function UploadPage() {
	const { session, loading } = useSession();
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
		const pdfFile = files.find((file) => file.type === "application/pdf");

		if (pdfFile) {
			setSelectedFile(pdfFile);
		} else {
			alert("Please upload a PDF file only.");
		}
	}, []);

	const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
		const file = e.target.files?.[0];
		if (file && file.type === "application/pdf") {
			setSelectedFile(file);
		} else if (file) {
			alert("Please select a PDF file only.");
		}
	}, []);

	const handleUpload = async () => {
		if (!selectedFile) return;

		setIsUploading(true);

		try {
			// Check if the PDF file contains sheet music
			const formData = new FormData();
			formData.append("pdf_file", selectedFile);
			const SheetMusicDetectorResponse = await fetch("http://localhost:8000/sheet_music/detector/", {
				method: "POST",
				body: formData,
			});

			const detectorData = await SheetMusicDetectorResponse.json();
      const detectorBody = JSON.parse(detectorData.body);
			const isSheetMusic = detectorBody.sheet_music;

			if (!isSheetMusic) {
				throw new Error("Please submit a pdf with sheet music.");
			}
			// Add to supabase
			const file = formData.get("pdf_file") as File;
			const fileExt = file.name.split(".").pop();
			const fileName = `${crypto.randomUUID()}.${fileExt}`;
			const filePath = `${session?.user.id}/${fileName}`;

			// Pieces storage bucket
			const { error: uploadError } = await supabase.storage.from("pieces").upload(filePath, file);

			if (uploadError) {
				console.error(uploadError);
				alert("Upload failed. Please try again.");
				return;
			}

      // Pieces DB table
			const { error: dbError } = await supabase
        .from("pieces")
        .insert({
          id: crypto.randomUUID(),
          user_id: session?.user.id,
          title: file.name,
          file_path: filePath,
          status: "processing",
        });

			if (dbError) {
				console.error(dbError);
        // Clean storage
				await supabase.storage.from("pieces").remove([filePath]);
				alert("Something went wrong saving your file.");
				return;
			}

			router.push("/upload-confirmation");
		} catch (error) {
			console.error("Upload failed:", error);
			alert("Upload failed. Please try again.");
		} finally {
			setIsUploading(false);
		}
	};

	const openFileDialog = () => {
		document.getElementById("file-input")?.click();
	};

	return (
		<main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
			<div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
				<div className="text-center">
					<h1 className="text-4xl font-semibold tracking-tight text-white">Upload Sheet Music</h1>
					<p className="mt-4 text-lg text-zinc-300">
						Drop your PDF sheet music here or click to browse. We'll analyze it and create a personalized practice plan.
					</p>
					<p className="mt-4 text-sm text-zinc-500 italic">
						*Don't have sheet music in PDF form? Google search your desired piece name + 'imslp', find the right version, then download.
					</p>
				</div>

				<div
					className={`relative rounded-[2rem] border-2 border-dashed p-12 text-center transition-all duration-200 ${
						isDragOver ? "border-indigo-400 bg-indigo-500/10" : "border-zinc-600 bg-zinc-900/50"
					}`}
					onDragOver={handleDragOver}
					onDragLeave={handleDragLeave}
					onDrop={handleDrop}
				>
					<input id="file-input" type="file" accept=".pdf" onChange={handleFileSelect} className="hidden" />

					<div className="flex flex-col items-center gap-6">
						<div className="text-6xl">📄</div>

						{selectedFile ? (
							<div className="space-y-2">
								<p className="text-lg font-medium text-white">{selectedFile.name}</p>
								<p className="text-sm text-zinc-400">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
							</div>
						) : (
							<div className="space-y-2">
								<p className="text-xl font-medium text-white">{isDragOver ? "Drop your PDF here" : "Drag & drop your PDF"}</p>
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
							selectedFile && !isUploading ? "bg-indigo-500 text-white hover:bg-indigo-400 cursor-pointer" : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
						}`}
					>
						{isUploading ? "Analyzing..." : "Upload & Analyze"}
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
