-- Joblyst database schema (Postgres / Supabase).
-- Only needed when DATABASE_URL is set; without it the API keeps sessions in memory.
-- Run once, e.g. in Supabase's SQL editor. LangGraph's checkpoint tables are created
-- by the app itself on startup (PostgresSaver.setup()).

-- What the API learns from a CV upload, kept between requests: the CV text and the
-- extracted profile, looked up by the thread_id the client got back from the upload.
create table if not exists candidate_sessions (
    thread_id  uuid        primary key,
    cv_text    text        not null,
    profile    jsonb       not null,
    created_at timestamptz not null default now(),
    -- CVs are personal data: a session stops working after 7 days
    -- (sessions.get only reads rows where expires_at > now()).
    expires_at timestamptz not null default now() + interval '7 days'
);

-- Supabase exposes every table through its public REST API. RLS on with no policies
-- blocks that API completely; the server connects as the table owner, which RLS
-- does not restrict.
alter table candidate_sessions enable row level security;
