-- Teams tabel
create table public.teams (
  id uuid default uuid_generate_v4() primary key,
  name text not null,
  owner_id uuid references auth.users(id) not null,
  logo_url text,
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

-- App settings tabel
create table public.app_settings (
  id uuid default uuid_generate_v4() primary key,
  key text not null unique,
  value text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Voeg default login logo setting toe
insert into public.app_settings (key, value) 
values ('login_logo_url', 'https://raw.githubusercontent.com/streamlit/streamlit/develop/examples/streamlit_app_logos/logo_01.png');

-- Voeg default logo width setting toe
insert into public.app_settings (key, value) 
values ('login_logo_width', '200');
