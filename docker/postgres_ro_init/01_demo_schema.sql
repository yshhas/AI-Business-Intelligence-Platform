-- M3 Demo: enterprise data plane (separate from platform metadata DB).
-- Role aibi_ro is SELECT-only on public demo tables.

CREATE TABLE IF NOT EXISTS public.demo_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS public.demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES public.demo_customers (customer_id),
    product TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    order_date DATE NOT NULL
);

TRUNCATE public.demo_orders, public.demo_customers RESTART IDENTITY CASCADE;

INSERT INTO public.demo_customers (customer_id, customer_name, region) VALUES
    (1, 'Acme North', 'North'),
    (2, 'Beta South', 'South'),
    (3, 'Gamma East', 'East'),
    (4, 'Delta West', 'West');

INSERT INTO public.demo_orders (order_id, customer_id, product, amount, order_date) VALUES
    (101, 1, 'Widget', 1200.00, '2026-01-15'),
    (102, 1, 'Gadget', 800.50, '2026-02-03'),
    (103, 2, 'Widget', 450.00, '2026-01-20'),
    (104, 2, 'Service', 2100.00, '2026-03-01'),
    (105, 3, 'Gadget', 990.00, '2026-02-18'),
    (106, 3, 'Widget', 300.00, '2026-03-12'),
    (107, 4, 'Service', 1500.00, '2026-01-28'),
    (108, 4, 'Widget', 700.25, '2026-03-05');

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aibi_ro') THEN
        CREATE ROLE aibi_ro LOGIN PASSWORD 'aibi_ro_password';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE aibi_data TO aibi_ro;
GRANT USAGE ON SCHEMA public TO aibi_ro;
GRANT SELECT ON TABLE public.demo_customers, public.demo_orders TO aibi_ro;
