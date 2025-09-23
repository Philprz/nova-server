--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4
-- Dumped by pg_dump version 17.4

-- Started on 2025-09-23 11:07:29

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

DROP DATABASE IF EXISTS nova_mcp;
--
-- TOC entry 4824 (class 1262 OID 16392)
-- Name: nova_mcp; Type: DATABASE; Schema: -; Owner: nova_user
--

CREATE DATABASE nova_mcp WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'fr-FR';


ALTER DATABASE nova_mcp OWNER TO nova_user;

\connect nova_mcp

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 2 (class 3079 OID 24626)
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- TOC entry 4825 (class 0 OID 0)
-- Dependencies: 2
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 220 (class 1259 OID 24621)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: nova_user
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO nova_user;

--
-- TOC entry 219 (class 1259 OID 24592)
-- Name: produits_sap; Type: TABLE; Schema: public; Owner: nova_user
--

CREATE TABLE public.produits_sap (
    id integer NOT NULL,
    item_code character varying(50) NOT NULL,
    item_name character varying(200) NOT NULL,
    u_description character varying(500),
    avg_price double precision,
    on_hand integer,
    items_group_code character varying(20),
    manufacturer character varying(100),
    bar_code character varying(50),
    valid boolean,
    sales_unit character varying(10),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.produits_sap OWNER TO nova_user;

--
-- TOC entry 218 (class 1259 OID 24591)
-- Name: produits_sap_id_seq; Type: SEQUENCE; Schema: public; Owner: nova_user
--

CREATE SEQUENCE public.produits_sap_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.produits_sap_id_seq OWNER TO nova_user;

--
-- TOC entry 4826 (class 0 OID 0)
-- Dependencies: 218
-- Name: produits_sap_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: nova_user
--

ALTER SEQUENCE public.produits_sap_id_seq OWNED BY public.produits_sap.id;


--
-- TOC entry 4664 (class 2604 OID 24595)
-- Name: produits_sap id; Type: DEFAULT; Schema: public; Owner: nova_user
--

ALTER TABLE ONLY public.produits_sap ALTER COLUMN id SET DEFAULT nextval('public.produits_sap_id_seq'::regclass);


--
-- TOC entry 4818 (class 0 OID 24621)
-- Dependencies: 220
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: nova_user
--

COPY public.alembic_version (version_num) FROM stdin;
08782712de79
\.


--
-- TOC entry 4817 (class 0 OID 24592)
-- Dependencies: 219
-- Data for Name: produits_sap; Type: TABLE DATA; Schema: public; Owner: nova_user
--

COPY public.produits_sap (id, item_code, item_name, u_description, avg_price, on_hand, items_group_code, manufacturer, bar_code, valid, sales_unit, created_at, updated_at) FROM stdin;
1	A00001	Imprimante IBM type Infoprint 1312		0	1130	101	4		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
2	A00002	Imprimante IBM type Infoprint 1222		0	1123	101	4		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
3	A00003	Imprimante IBM type Infoprint 1226		0	1157	101	4		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
4	A00004	Imprimante HP type Color Laser Jet 5		0	1129	102	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
5	A00005	Imprimante HP type Color Laser Jet 4		0	1231	102	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
6	A00006	Imprimante HP type 600 Series Inc		0	70	102	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
7	B10000	Etiquettes pour imprimante		0	500	100	3		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
8	C00001	Carte mère P4 Turbo		0	1511	100	5		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
9	C00002	Carte mère P4 Turbo - Asus Chipset		0	1488	100	5		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
10	C00003	Processeur Intel P4 2.4 GhZ		0	1167	100	6		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
11	C00004	Tour PC avec alimentation		0	1262	100	1		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
12	C00005	Carte WLAN		0	1181	100	1		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
13	C00006	Carte réseau 10/100		0	1147	100	1		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
14	C00007	Disque dur Seagate 400 GB		0	1200	100	1		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
15	C00008	Moniteur 19' TFT		0	1216	100	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
16	C00009	Clavier USB type Comfort		0	1183	100	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
17	C00010	Souris USB		0	1168	100	2		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
18	C00011	Barette mémoire DDR RAM 512 MB		0	1171	100	5		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
19	I00001	Pack de 10 disques DVD+R		0	1088	100	6		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
20	I00002	pack de 50 disques DVD+R		0	1016	100	6		t	UN	2025-08-29 16:45:38.22834	2025-08-29 16:45:38.22834
\.


--
-- TOC entry 4827 (class 0 OID 0)
-- Dependencies: 218
-- Name: produits_sap_id_seq; Type: SEQUENCE SET; Schema: public; Owner: nova_user
--

SELECT pg_catalog.setval('public.produits_sap_id_seq', 20, true);


--
-- TOC entry 4670 (class 2606 OID 24625)
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: nova_user
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- TOC entry 4668 (class 2606 OID 24599)
-- Name: produits_sap produits_sap_pkey; Type: CONSTRAINT; Schema: public; Owner: nova_user
--

ALTER TABLE ONLY public.produits_sap
    ADD CONSTRAINT produits_sap_pkey PRIMARY KEY (id);


--
-- TOC entry 4665 (class 1259 OID 24707)
-- Name: idx_produits_sap_name_trgm; Type: INDEX; Schema: public; Owner: nova_user
--

CREATE INDEX idx_produits_sap_name_trgm ON public.produits_sap USING gin (item_name public.gin_trgm_ops);


--
-- TOC entry 4666 (class 1259 OID 24600)
-- Name: ix_produits_sap_item_code; Type: INDEX; Schema: public; Owner: nova_user
--

CREATE UNIQUE INDEX ix_produits_sap_item_code ON public.produits_sap USING btree (item_code);


--
-- TOC entry 2096 (class 826 OID 16393)
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: -; Owner: postgres
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres GRANT ALL ON TABLES TO nova_user;


-- Completed on 2025-09-23 11:07:31

--
-- PostgreSQL database dump complete
--

