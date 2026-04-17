import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabaseClient";

export async function POST(req: Request) {
  const body = await req.json();
  const { userId, level, years } = body;

  // basic validation
  if (!userId || !level || years === undefined) {
    return NextResponse.json({ error: "Missing fields" }, { status: 400 });
  }

  if (years < 0 || years > 80) {
    return NextResponse.json({ error: "Invalid years" }, { status: 400 });
  }

  const { error } = await supabase
    .from("profiles")
    .update({
      piano_level: level,
      years_experience: years,
      onboarding_complete: true,
    })
    .eq("id", userId);

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}