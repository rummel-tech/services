-- Trigger: On new morning routine entry, call Edge Function

create or replace function notify_new_routine()
returns trigger language plpgsql as $$
declare
    payload json;
begin
    payload = json_build_object(
        'user_id', NEW.user_id,
        'routine_id', NEW.id,
        'source', 'morning_routine'
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

drop trigger if exists routine_trigger on morning_routine;
create trigger routine_trigger
after insert on morning_routine
for each row execute procedure notify_new_routine();
