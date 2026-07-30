import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "https://dkzfrzwevnyzhcicmtda.supabase.co";
const supabaseAnonKey =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  "sb_publishable_7J6Pd6G8bAgJ5wEqVSpklQ_KJhQrZsa";

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
