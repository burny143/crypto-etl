import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = "https://ymnlqggxeeyqvrojsrzh.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InltbmxxZ2d4ZWV5cXZyb2pzcnpoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM3NjQ2NDQsImV4cCI6MjA5OTM0MDY0NH0.wsO53Ninsb_9Mxt0Me5q3vYuQMr5XFUASYgdBzeHfbQ";

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
