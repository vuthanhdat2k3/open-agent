"""Deterministic Customer Intelligence company fixtures for eval/demo runs.

This module is deliberately under ``app.evals``: the six-company dataset is
not part of the production company database and must never be used to invent
records for arbitrary names.
"""

from __future__ import annotations

from app.customer_intelligence.contracts import CompanyRecord

FIXTURE_COMPANIES: dict[str, CompanyRecord] = {
    "fpt software": CompanyRecord(
        company_id="fixture-fpt-software",
        canonical_name="FPT Software",
        aliases=["FPT", "FPT Software JSC"],
        industry="Information technology services",
        products=["Digital transformation", "Software development", "Cloud services"],
        contacts=[{"name": "FPT Software", "role": "Corporate contact", "email": "info@fptsoftware.com"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="fptsoftware.com",
    ),
    "vinamilk": CompanyRecord(
        company_id="fixture-vinamilk",
        canonical_name="Vinamilk",
        aliases=["Vietnam Dairy Products JSC", "VNM"],
        industry="Dairy and consumer goods",
        products=["Milk", "Yogurt", "Dairy nutrition"],
        contacts=[{"name": "Vinamilk", "role": "Corporate contact", "email": "info@vinamilk.com.vn"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="vinamilk.com.vn",
    ),
    "samsung vietnam": CompanyRecord(
        company_id="fixture-samsung-vietnam",
        canonical_name="Samsung Vietnam",
        aliases=["Samsung Electronics Vietnam", "Samsung"],
        industry="Electronics and technology manufacturing",
        products=["Mobile devices", "Consumer electronics", "Semiconductors"],
        contacts=[{"name": "Samsung Vietnam", "role": "Corporate contact", "email": "info@samsung.com"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="samsung.com",
    ),
    "shopee vietnam": CompanyRecord(
        company_id="fixture-shopee-vietnam",
        canonical_name="Shopee Vietnam",
        aliases=["Shopee", "Sea Limited marketplace"],
        industry="E-commerce",
        products=["Online marketplace", "Digital payments", "Seller services"],
        contacts=[{"name": "Shopee Vietnam", "role": "Corporate contact", "email": "help@shopee.vn"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="shopee.vn",
    ),
    "viettel solutions": CompanyRecord(
        company_id="fixture-viettel-solutions",
        canonical_name="Viettel Solutions",
        aliases=["Viettel", "Viettel Business Solutions"],
        industry="Telecommunications and information technology",
        products=["Cloud computing", "Cybersecurity", "Digital government platforms"],
        contacts=[{"name": "Viettel Solutions", "role": "Corporate contact", "email": "info@viettel.com.vn"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="viettel.com.vn",
    ),
    "bosch": CompanyRecord(
        company_id="fixture-bosch",
        canonical_name="Bosch",
        aliases=["Robert Bosch", "Bosch Vietnam"],
        industry="Engineering and technology",
        products=["Mobility solutions", "Industrial technology", "Consumer goods"],
        contacts=[{"name": "Bosch Vietnam", "role": "Corporate contact", "email": "info@bosch.com"}],
        source="fixture:customer-intelligence-capstone",
        updated_at="2026-08-15T00:00:00Z",
        domain="bosch.com",
    ),
}
