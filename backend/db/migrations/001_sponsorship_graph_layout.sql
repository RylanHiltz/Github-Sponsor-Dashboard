ALTER TABLE public.sponsorship
ADD COLUMN IF NOT EXISTS created_at timestamp with time zone NOT NULL DEFAULT now();

CREATE INDEX IF NOT EXISTS idx_sponsorship_sponsor_id
ON public.sponsorship USING btree (sponsor_id);

CREATE INDEX IF NOT EXISTS idx_sponsorship_sponsored_id
ON public.sponsorship USING btree (sponsored_id);

CREATE TABLE IF NOT EXISTS public.sponsorship_graph_layout (
  user_id bigint NOT NULL,
  x real NOT NULL,
  y real NOT NULL,
  z real NOT NULL,
  updated_at timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT sponsorship_graph_layout_pkey PRIMARY KEY (user_id),
  CONSTRAINT sponsorship_graph_layout_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE
);
