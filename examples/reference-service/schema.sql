--
-- PostgreSQL database dump
--




SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: order_lines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_lines (
    order_id uuid NOT NULL,
    line_number integer NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL,
    unit_amount numeric(14,2) NOT NULL,
    unit_currency character(3) NOT NULL,
    CONSTRAINT order_lines_quantity_positive CHECK ((quantity > 0)),
    CONSTRAINT order_lines_unit_amount_non_negative CHECK ((unit_amount >= (0)::numeric))
);


--
-- Name: orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.orders (
    id uuid NOT NULL,
    customer_id uuid NOT NULL,
    total_amount numeric(14,2) NOT NULL,
    total_currency character(3) NOT NULL,
    internal_note text,
    CONSTRAINT orders_total_amount_non_negative CHECK ((total_amount >= (0)::numeric))
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version bigint NOT NULL,
    dirty boolean NOT NULL
);


--
-- Name: order_lines order_lines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_lines
    ADD CONSTRAINT order_lines_pkey PRIMARY KEY (order_id, line_number);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: order_lines order_lines_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_lines
    ADD CONSTRAINT order_lines_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.orders(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--
