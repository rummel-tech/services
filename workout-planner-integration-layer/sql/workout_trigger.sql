-- Trigger: On new workout ingestion, call Edge Function

create or replace function notify_new_workout()
returns trigger language plpgsql as $$
declare
    payload json;
begin
    payload = json_build_object(
        'user_id', NEW.user_id,
        'workout_id', NEW.id,
        'source', 'workout_ingest'
    );
    perform
        net.http_post(
            url := current_setting('app.settings.edge_url') || '/ai-orchestrator',
            body := payload::text,
            headers := '{"Content-Type": "application/json"}'
        );
    return NEW;
end;
$$;

drop trigger if exists workout_ingest_trigger on workouts;
create trigger workout_ingest_trigger
after insert on workouts
for each row execute procedure notify_new_workout();
