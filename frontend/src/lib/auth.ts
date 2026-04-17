import { supabase } from "@/lib/supabaseClient";

export async function signInWithGoogle() {
  await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${window.location.origin}/return`,
    },
  });
}

export async function redirectAfterAuth(router: any) {
  const { data } = await supabase.auth.getUser();
  const user = data.user;

  if (!user) {
    router.replace("/signin");
    return;
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("onboarding_complete")
    .eq("id", user.id)
    .single();

  if (!profile || profile.onboarding_complete === false) {
    router.replace("/onboarding");
  } else {
    router.replace("/");
  }
}