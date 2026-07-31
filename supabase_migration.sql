create table signals (
    id uuid primary key default gen_random_uuid(),
    timestamp timestamptz not null,
    symbol text not null,
    strategy text not null,
    direction text not null check (direction in ('BUY', 'SELL')),
    price numeric not null,
    strength numeric not null check (strength >= 0 and strength <= 1),
    metadata jsonb not null,
    research_sweep_id uuid,
    created_at timestamptz default now(),
    foreign key (research_sweep_id) references research_runs(run_id)
);

-- Indexes for performance
create index idx_signals_symbol on signals(symbol);
create index idx_signals_timestamp on signals(timestamp);
create index idx_signals_strategy on signals(strategy);
