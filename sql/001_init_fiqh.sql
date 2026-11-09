-- 001_init_fiqh.sql — déjà appliqué sur le projet Supabase « nour » (2026-11-09)
-- Tables du fiqh, sécurité RLS, index vectoriel et fonction de recherche.

-- 1. pgvector : le type « vector » pour stocker les embeddings
create extension if not exists vector with schema extensions;

-- 2. Les livres (une ligne par matn)
create table public.matns (
  id        smallint generated always as identity primary key,
  madhhab   text not null check (madhhab in ('maliki','hanafi','shafii','hanbali')),
  titre     text not null,
  auteur    text not null,
  edition   text,
  source    text
);

-- 3. Les مسائل (une ligne par مسألة ou par partie)
create table public.fiqh_chunks (
  id               bigint generated always as identity primary key,
  matn_id          smallint not null references public.matns(id),
  kitab            text not null,
  bab              text not null,
  ordre_bab        smallint not null,
  section          text,
  ordre            int not null,
  partie           smallint not null default 1,
  page             int,
  texte_affichage  text not null,
  texte_recherche  text not null,
  texte_embedding  text not null,
  embedding        extensions.vector(1024),
  unique (matn_id, ordre, partie)
);

-- 4. Sécurité : tables fermées, seul le backend (clé secrète) y accède
alter table public.matns       enable row level security;
alter table public.fiqh_chunks enable row level security;

-- 5. Index vectoriel HNSW (distance cosinus)
create index fiqh_chunks_embedding_idx
  on public.fiqh_chunks using hnsw (embedding extensions.vector_cosine_ops);

-- 6. Recherche : les nb مسائل les plus proches d'une question, dans un madhhab
create or replace function public.chercher_fiqh(
  question_embedding extensions.vector(1024),
  p_madhhab text,
  nb int default 5
)
returns table (
  id bigint, matn_id smallint, titre text, kitab text, bab text, section text,
  ordre int, partie smallint, page int, texte_affichage text, similarite float
)
language sql stable
set search_path = public, extensions
as $$
  select c.id, c.matn_id, m.titre, c.kitab, c.bab, c.section,
         c.ordre, c.partie, c.page, c.texte_affichage,
         1 - (c.embedding <=> question_embedding) as similarite
  from public.fiqh_chunks c
  join public.matns m on m.id = c.matn_id
  where m.madhhab = p_madhhab and c.embedding is not null
  order by c.embedding <=> question_embedding
  limit nb;
$$;

revoke execute on function public.chercher_fiqh(extensions.vector, text, int) from public, anon, authenticated;

-- 7. Données : la Risala
insert into public.matns (madhhab, titre, auteur, edition, source) values
  ('maliki', 'الرسالة', 'ابن أبي زيد القيرواني',
   'نسخة التتائي، جمع وتحقيق إبراهيم أحمد إبراهيم السناري، معهد المخطوطات العربية، ١٤٤٢ هـ / 2021',
   'https://shamela.ws/book/1430');
