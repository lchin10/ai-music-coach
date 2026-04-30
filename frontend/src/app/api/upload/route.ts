import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabaseClient";

export async function POST(req: Request) {
  const userId = req.headers.get("x-user-id");
  const formData = await req.formData();
  const file = formData.get("pdf_file") as File;
  
  if (!userId) {
    return NextResponse.json({ error: "Missing userId" }, { status: 400 });
  }

  if (!file) {
    return NextResponse.json({ error: "Missing file" }, { status: 400 });
  }

  const fileExt = file.name.split(".").pop();
  const fileName = `${crypto.randomUUID()}.${fileExt}`;
  const filePath = `pdfs/${fileName}`;
  
  const { error } = await supabase.storage
    .from("pieces") // your bucket name
    .upload(filePath, file);

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
  
  return NextResponse.json({ success: true });
}