
-- Teams tabel
create table public.teams (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  owner_id uuid references auth.users(id) not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Team members tabel
create table public.team_members (
  id uuid default uuid_generate_v4() primary key,
  team_id uuid references public.teams(id) not null,
  user_email text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Search history tabel
create table public.search_history (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references auth.users(id) not null,
  search_data jsonb not null,
  timestamp timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Notes tabel
create table public.notes (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references auth.users(id) not null,
  locatie_id text not null,
  content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);
