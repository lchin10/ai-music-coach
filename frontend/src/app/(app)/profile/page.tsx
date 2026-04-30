"use client";

import Link from "next/link";
import useSession from "@/lib/userSession";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";

type Profile = {
	name: string;
	piano_level: string;
	years_experience: number;
};

type Piece = {
	id: string;
	title: string;
	created_at: string;
	status: string;
};

export default function ProfilePage() {
	const { session, loading } = useSession();
	const router = useRouter();
	const [profile, setProfile] = useState<Profile | null>(null);
	const [editing, setEditing] = useState(false);
	const [level, setLevel] = useState(profile?.piano_level || "");
	const [yoe, setYoe] = useState(profile?.years_experience?.toString() || "");
	const [onboardingLoading, setOnboardingLoading] = useState(false);
	const [pieces, setPieces] = useState<Piece[]>([]);

	useEffect(() => {
		const fetchProfile = async () => {
			if (!session) return;

      // User info
			const { data: userData, error: userError } = await supabase.from("profiles").select("name, piano_level, years_experience").single();
			if (userError) {
				return;
			}
			const res = { profile: userData };
			setProfile(res.profile);

      // Pieces
      const { data: piecesData, error: piecesError } = await supabase.from("pieces").select("id, title, created_at, status").eq("user_id", session.user.id);
      if (piecesError) {
        return;
      }
      setPieces(piecesData);
		};

		fetchProfile();
	}, [session]);

	useEffect(() => {
		if (!editing) {
			setLevel(profile?.piano_level || "");
			setYoe(profile?.years_experience?.toString() || "");
		}
	}, [profile]);

	const handleUpdate = async () => {
		if (!session) return;

		setOnboardingLoading(true);

		const { error } = await supabase.from("profiles").update({
			piano_level: level.toLowerCase(),
			years_experience: Number(yoe),
			onboarding_complete: true,
		});

		setOnboardingLoading(false);

		if (error) {
			return;
		} else {
			setEditing(false);
		}
	};

	const handleEdit = () => {
		resetEditState();
		setEditing(true);
	};

	const resetEditState = () => {
		setLevel(profile?.piano_level || "");
		setYoe(profile?.years_experience?.toString() || "");
	};

	if (loading) {
		return null;
	}

	if (!session) {
		return (
			<main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
				<div className="mx-auto flex max-w-4xl flex-col items-center gap-6 rounded-[2rem] border border-white/10 bg-zinc-900/90 p-10 text-center shadow-xl shadow-black/30">
					<h1 className="text-4xl font-semibold">Sign in to view your profile</h1>
					<p className="max-w-2xl text-zinc-400">Your uploaded pieces and practice history are available after signing in.</p>
					<button
						type="button"
						onClick={() => router.push("/signin")}
						className="rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400 cursor-pointer"
					>
						Sign in
					</button>
				</div>
			</main>
		);
	}

	return (
		<main className="min-h-screen bg-zinc-950 text-white px-6 py-12">
			<div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
				<section className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-10 shadow-xl shadow-black/30 backdrop-blur-xl">
					<div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
						<div>
							<p className="text-sm uppercase tracking-[0.3em] text-indigo-300">Profile</p>
							<h1 className="text-4xl font-semibold text-white">{profile?.name || "Account"}</h1>
							<p className="text-sm text-zinc-400">{session.user?.email}</p>
						</div>
					</div>
				</section>

				<section className="rounded-[2rem] border border-white/10 bg-zinc-800/40 backdrop-blur-md p-10 shadow-xl shadow-black/30">
					<div className="flex justify-between items-start">
						<div className="space-y-3">
							{/* Piano Level */}
							<div>
								<p className="text-xs uppercase tracking-widest text-zinc-400">Piano level</p>

								{editing ? (
									<div className="flex gap-2">
										{["Beginner", "Intermediate", "Advanced"].map((option) => (
											<button
												key={option}
												type="button"
												onClick={() => setLevel(option.toLowerCase())}
												className={`px-4 py-2 rounded-xl text-sm font-medium border transition
                                    ${
																			level === option.toLowerCase()
																				? "bg-indigo-500 text-white border-indigo-500"
																				: "bg-zinc-900 text-zinc-300 border-zinc-700 hover:bg-zinc-800"
																		}`}
											>
												{option}
											</button>
										))}
									</div>
								) : (
									<p className="text-sm text-white capitalize">{level || "---"}</p>
								)}
							</div>

							{/* Years of Experience */}
							<div>
								<p className="text-xs uppercase tracking-widest text-zinc-400">Years of experience</p>

								{editing ? (
									<input
										type="number"
										min="0"
										placeholder="0"
										value={yoe}
										onChange={(e) => setYoe(e.target.value)}
										className="w-24 rounded-xl bg-zinc-900 border border-zinc-700 px-3 py-2 text-sm text-white outline-none focus:border-indigo-500"
									/>
								) : (
									<p className="text-sm text-white">{yoe ? yoe + " years" : "---"}</p>
								)}
							</div>
						</div>

						{/* Button */}
						<div className="flex gap-2">
							<button
								onClick={editing ? handleUpdate : handleEdit}
								disabled={onboardingLoading}
								className="rounded-xl bg-indigo-500 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-400 disabled:opacity-50 cursor-pointer"
							>
								{editing ? (onboardingLoading ? "Updating..." : "Update") : "Edit"}
							</button>

							{editing && (
								<button
									onClick={() => {
										resetEditState();
										setEditing(false);
									}}
									className="rounded-xl bg-zinc-800 px-4 py-2 text-sm font-semibold text-white hover:bg-zinc-700 cursor-pointer"
								>
									Cancel
								</button>
							)}
						</div>
					</div>
				</section>

				<section className="rounded-[2rem] border border-white/10 bg-zinc-900/90 p-8 shadow-lg shadow-black/20">
					<div className="flex items-center justify-between gap-4">
						<div>
							<h2 className="text-2xl font-semibold text-white">Your Pieces</h2>
						</div>
						<Link
							href="/upload"
							className="inline-flex items-center justify-center rounded-2xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white transition hover:bg-indigo-400"
						>
							Upload New Piece
						</Link>
					</div>

					<div className="mt-8 space-y-4">
						{pieces.length > 0 ? (
							<>
								{pieces.map((piece: Piece) => (
									<div key={piece.id} className="rounded-3xl border border-white/10 bg-zinc-950/70 p-4 sm:p-6">
										<div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
											<div>
												<p className="font-semibold text-white">{piece.title}</p>
												<p className="text-sm text-zinc-400">Uploaded: {piece.created_at}</p>
											</div>
											<span className="rounded-full bg-zinc-800 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-zinc-300">{piece.status}</span>
										</div>
									</div>
								))}
							</>
						) : (
							<div className="text-center text-zinc-400">Upload your first piece to get started!</div>
						)}
					</div>
				</section>
			</div>
		</main>
	);
}
