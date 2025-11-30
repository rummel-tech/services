// Edge Function: AI Orchestrator
// Gathers data from Supabase + calls Python AI engine
// Writes readiness, daily plan, insights back to Supabase

import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

serve(async (req: Request) => {
  try {
    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!
    );

    const body = await req.json();
    const { user_id } = body;

    // 1. Pull latest user metrics
    const { data: routine } = await supabase
      .from("morning_routine")
      .select("*")
      .eq("user_id", user_id)
      .order("created_at", { ascending: false })
      .limit(1)
      .single();

    const { data: latest_workout } = await supabase
      .from("workouts")
      .select("*")
      .eq("user_id", user_id)
      .order("start_time", { ascending: false })
      .limit(1)
      .single();

    // 2. Combine payload for AI
    const metrics = {
      hrv: routine?.hrv,
      sleep_hours: routine?.sleep_hours,
      resting_hr: routine?.resting_hr,
      latest_workout: latest_workout ?? null,
    };

    // 3. Call Python AI Engine
    const aiUrl = Deno.env.get("AI_SERVER_URL") + "/daily";

    const aiResp = await fetch(aiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(metrics),
    });

    const aiData = await aiResp.json();

    // 4. Write results back to Supabase
    await supabase.from("readiness_scores").insert({
      user_id,
      readiness: aiData.readiness,
      details: aiData,
    });

    await supabase.from("daily_plans").insert({
      user_id,
      plan: aiData.plan,
    });

    return new Response(JSON.stringify({ status: "ok", aiData }), {
      headers: { "Content-Type": "application/json" },
    });

  } catch (err) {
    console.error(err);
    return new Response("AI Orchestration Error", { status: 500 });
  }
});
