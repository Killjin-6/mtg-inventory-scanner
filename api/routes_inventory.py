from __future__ import annotations

from html import escape
from urllib.parse import urlparse

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import Select, select

from db.models import CardPrinting, InventoryItem
from db.repo import SessionLocal

router = APIRouter()

RARITY_OPTIONS = {"common", "uncommon", "rare", "mythic"}
COLOR_OPTIONS = {"W", "U", "B", "R", "G"}
CONDITION_OPTIONS = {"", "NM", "LP", "MP", "HP", "DMG"}

APP_SHELL_CSS = """
:root {
  color-scheme: light;
  --bg: #f4efe6;
  --bg-accent: #efe4d5;
  --surface: rgba(255, 251, 246, 0.82);
  --surface-strong: #fffaf4;
  --surface-muted: rgba(255, 255, 255, 0.68);
  --ink: #1f1a15;
  --muted: #6f655a;
  --line: rgba(101, 83, 59, 0.18);
  --line-strong: rgba(101, 83, 59, 0.28);
  --primary: #1f6a52;
  --primary-strong: #154c3b;
  --primary-soft: rgba(31, 106, 82, 0.11);
  --secondary: #f1e4d2;
  --secondary-ink: #4f4235;
  --danger: #a14c40;
  --danger-strong: #7f372e;
  --shadow: 0 24px 56px rgba(33, 25, 17, 0.12);
  --shadow-soft: 0 14px 30px rgba(33, 25, 17, 0.06);
  --chip-exact-bg: rgba(27, 122, 76, 0.12);
  --chip-exact-text: #176743;
  --chip-fallback-bg: rgba(176, 124, 25, 0.14);
  --chip-fallback-text: #8a5d08;
  --chip-unresolved-bg: rgba(96, 91, 84, 0.14);
  --chip-unresolved-text: #5c5750;
}

* {
  box-sizing: border-box;
}

html {
  background: linear-gradient(180deg, #f8f4ee, var(--bg));
}

body {
  margin: 0;
  min-height: 100vh;
  font-family: "Segoe UI", sans-serif;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(31, 106, 82, 0.16), transparent 32%),
    radial-gradient(circle at bottom right, rgba(161, 76, 64, 0.08), transparent 24%),
    linear-gradient(180deg, #faf7f2, var(--bg));
}

a {
  color: inherit;
}

button,
input,
select {
  font: inherit;
}

.app-shell {
  width: min(100%, 1100px);
  margin: 0 auto;
  padding: 16px;
}

.app-stack {
  display: grid;
  gap: 16px;
}

.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  padding-top: 10px;
}

.app-header-inner {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(255, 250, 244, 0.84);
  backdrop-filter: blur(18px);
  box-shadow: var(--shadow-soft);
}

.app-brand {
  display: grid;
  gap: 4px;
}

.app-kicker {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--primary);
}

.app-title {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 800;
  letter-spacing: -0.02em;
}

.app-subtitle {
  margin: 0;
  color: var(--muted);
  line-height: 1.5;
  font-size: 0.95rem;
}

.app-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.app-nav-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 42px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  color: var(--secondary-ink);
  text-decoration: none;
  font-weight: 700;
  box-shadow: var(--shadow-soft);
}

.app-nav-link.is-active {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  color: #fff;
  border-color: transparent;
}

.page-hero,
.app-card {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: var(--surface);
  backdrop-filter: blur(20px);
  box-shadow: var(--shadow);
}

.page-hero::before,
.app-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 120px;
  background:
    radial-gradient(circle at top left, rgba(31, 106, 82, 0.14), transparent 48%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.36), transparent);
  pointer-events: none;
}

.page-hero-inner,
.app-card-inner {
  position: relative;
  padding: 20px;
}

.page-hero-inner {
  display: grid;
  gap: 18px;
}

.eyebrow {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid var(--line);
  color: var(--primary);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-title {
  margin: 0;
  font-size: clamp(2rem, 6vw, 3rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
}

.page-copy {
  margin: 0;
  max-width: 56ch;
  color: var(--muted);
  line-height: 1.6;
}

.hero-metrics {
  display: grid;
  gap: 12px;
}

.metric-card {
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.7);
}

.metric-label {
  margin: 0 0 6px;
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.metric-value {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.45;
}

.section-head {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 16px;
}

.section-title {
  margin: 0;
  font-size: 1.12rem;
  letter-spacing: -0.02em;
}

.section-copy {
  margin: 0;
  color: var(--muted);
  line-height: 1.55;
  font-size: 0.95rem;
}

.toolbar-grid,
.form-grid {
  display: grid;
  gap: 12px;
}

.field {
  display: grid;
  gap: 6px;
}

.field-label {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}

.control,
.button {
  width: 100%;
  min-height: 46px;
  border-radius: 16px;
}

.control {
  padding: 12px 14px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
}

.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px 16px;
  border: 0;
  cursor: pointer;
  font-weight: 800;
  text-decoration: none;
  box-shadow: 0 14px 28px rgba(21, 76, 59, 0.18);
}

.button:disabled {
  cursor: default;
  opacity: 0.6;
  box-shadow: none;
}

.button.primary {
  background: linear-gradient(135deg, var(--primary), var(--primary-strong));
  color: #fff;
}

.button.secondary {
  background: linear-gradient(180deg, #f2e8dc, #e7d7c4);
  color: var(--secondary-ink);
  box-shadow: none;
  border: 1px solid rgba(101, 83, 59, 0.14);
}

.button.danger {
  background: linear-gradient(135deg, var(--danger), var(--danger-strong));
  color: #fff;
  box-shadow: none;
}

.button.small {
  width: auto;
  min-height: 40px;
  padding: 10px 12px;
  border-radius: 14px;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.82);
  color: var(--secondary-ink);
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: 0.02em;
  text-transform: capitalize;
}

.chip.exact {
  background: var(--chip-exact-bg);
  color: var(--chip-exact-text);
  border-color: rgba(23, 103, 67, 0.16);
}

.chip.fallback {
  background: var(--chip-fallback-bg);
  color: var(--chip-fallback-text);
  border-color: rgba(138, 93, 8, 0.16);
}

.chip.unresolved {
  background: var(--chip-unresolved-bg);
  color: var(--chip-unresolved-text);
  border-color: rgba(92, 87, 80, 0.16);
}

.chip.confirmed {
  background: var(--chip-exact-bg);
  color: var(--chip-exact-text);
}

.meta-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.table-wrap {
  overflow-x: auto;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.76);
}

.inventory-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 960px;
}

.inventory-table th,
.inventory-table td {
  padding: 14px 12px;
  border-bottom: 1px solid rgba(101, 83, 59, 0.12);
  text-align: left;
  vertical-align: top;
}

.inventory-table th {
  background: rgba(244, 237, 226, 0.94);
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.inventory-table tbody tr:last-child td {
  border-bottom: 0;
}

.cell-strong {
  font-weight: 700;
}

.actions-cell {
  min-width: 280px;
}

.edit-form {
  display: grid;
  gap: 8px;
}

.edit-form label {
  display: grid;
  gap: 5px;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
}

.edit-form input,
.edit-form select {
  min-width: 0;
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.row-actions form {
  margin: 0;
}

.empty-state {
  padding: 28px 18px;
  text-align: center;
  color: var(--muted);
}

@media (min-width: 760px) {
  .app-shell {
    padding: 20px;
  }

  .app-header-inner {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }

  .page-hero-inner {
    grid-template-columns: minmax(0, 1.35fr) minmax(240px, 0.65fr);
    align-items: start;
  }

  .toolbar-grid {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    align-items: end;
  }

  .edit-form {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    align-items: end;
  }
}

@media (max-width: 759px) {
  .inventory-table,
  .inventory-table thead,
  .inventory-table tbody,
  .inventory-table tr,
  .inventory-table td {
    display: block;
    min-width: 0;
  }

  .inventory-table {
    min-width: 0;
  }

  .inventory-table thead {
    display: none;
  }

  .inventory-table tbody {
    display: grid;
    gap: 12px;
    padding: 12px;
  }

  .inventory-table tr {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.9);
    overflow: hidden;
  }

  .inventory-table td {
    border-bottom: 1px solid rgba(101, 83, 59, 0.1);
    padding: 12px 14px;
  }

  .inventory-table td:last-child {
    border-bottom: 0;
  }

  .inventory-table td::before {
    content: attr(data-label);
    display: block;
    margin-bottom: 4px;
    color: var(--muted);
    font-size: 0.74rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .inventory-table td[data-label="Actions"]::before {
    margin-bottom: 10px;
  }
}
""".strip()


def render_app_nav(active_path: str) -> str:
    links = [
        ("/phone", "Phone Scan"),
        ("/inventory/view", "Inventory"),
        ("/scan-history", "Scan History"),
    ]
    rendered = []
    for href, label in links:
        classes = "app-nav-link"
        if href == active_path:
            classes += " is-active"
        rendered.append(f'<a class="{classes}" href="{href}">{escape(label)}</a>')
    return "\n".join(rendered)


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def build_inventory_query(
    q: str | None,
    color: str | None,
    rarity: str | None,
    set_code: str | None,
    limit: int,
) -> Select[tuple[InventoryItem, CardPrinting]]:
    statement = (
        select(InventoryItem, CardPrinting)
        .join(CardPrinting, CardPrinting.id == InventoryItem.card_printing_id)
        .order_by(InventoryItem.id.desc())
        .limit(limit)
    )

    if q:
        statement = statement.where(CardPrinting.name.ilike(f"%{q.strip()}%"))
    if color:
        statement = statement.where(CardPrinting.color_identity.ilike(f"%{color.upper()}%"))
    if rarity:
        statement = statement.where(CardPrinting.rarity == rarity.lower())
    if set_code:
        statement = statement.where(CardPrinting.set_code == set_code.strip().lower())

    return statement


def serialize_inventory_row(item: InventoryItem, card: CardPrinting) -> dict[str, object]:
    return {
        "name": card.name,
        "set_code": card.set_code,
        "collector_number": card.collector_number,
        "rarity": card.rarity,
        "color_identity": card.color_identity,
        "quantity": item.quantity,
        "reserved_quantity": item.reserved_quantity,
        "foil": item.foil,
        "condition": item.condition,
        "scryfall_id": card.scryfall_id,
        "image_uri": card.image_uri,
    }


def safe_return_to(return_to: str | None) -> str:
    if not return_to:
        return "/inventory/view"
    parsed = urlparse(return_to)
    if parsed.scheme or parsed.netloc or not return_to.startswith("/"):
        return "/inventory/view"
    return return_to


def normalize_condition(condition: str | None) -> str | None:
    if condition is None:
        return None
    normalized = condition.strip().upper()
    if normalized not in CONDITION_OPTIONS:
        raise HTTPException(status_code=400, detail="Unsupported card condition.")
    return normalized or None


@router.get("/inventory")
async def inventory_rows(
    q: str | None = None,
    color: str | None = Query(default=None, pattern="^[WUBRGwubrg]$"),
    rarity: str | None = Query(default=None, pattern="^(common|uncommon|rare|mythic)$"),
    set: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, object]]:
    q = optional_str(q)
    color = optional_str(color)
    rarity = optional_str(rarity)
    set = optional_str(set)
    normalized_color = color.upper() if color else None
    normalized_rarity = rarity.lower() if rarity else None
    normalized_set = set.lower() if set else None

    with SessionLocal() as session:
        rows = session.execute(
            build_inventory_query(
                q=q,
                color=normalized_color if normalized_color in COLOR_OPTIONS else None,
                rarity=normalized_rarity if normalized_rarity in RARITY_OPTIONS else None,
                set_code=normalized_set,
                limit=limit,
            )
        ).all()

    return [serialize_inventory_row(item, card) for item, card in rows]


@router.post("/inventory/update")
async def inventory_update(
    scryfall_id: str = Form(...),
    action: str = Form(...),
    reserved_quantity: int | None = Form(default=None),
    foil: int | None = Form(default=None),
    condition: str | None = Form(default=None),
    return_to: str = Form("/inventory/view"),
) -> RedirectResponse:
    normalized_action = action.lower().strip()
    reserved_quantity = optional_int(reserved_quantity)
    foil = optional_int(foil)
    condition = optional_str(condition)
    if normalized_action not in {"increment", "decrement", "remove", "edit"}:
        raise HTTPException(status_code=400, detail="Unsupported inventory action.")

    if reserved_quantity is not None and reserved_quantity < 0:
        raise HTTPException(status_code=400, detail="Reserved quantity cannot be negative.")
    if foil is not None and foil not in {0, 1}:
        raise HTTPException(status_code=400, detail="Foil must be 0 or 1.")

    with SessionLocal() as session:
        row = session.execute(
            select(InventoryItem, CardPrinting)
            .join(CardPrinting, CardPrinting.id == InventoryItem.card_printing_id)
            .where(CardPrinting.scryfall_id == scryfall_id)
            .limit(1)
        ).first()

        if row is None:
            raise HTTPException(status_code=404, detail="Inventory row not found.")

        item, _ = row
        if normalized_action == "increment":
            item.quantity += 1
        elif normalized_action == "decrement":
            if item.quantity <= 1:
                session.delete(item)
            else:
                item.quantity -= 1
        elif normalized_action == "edit":
            if reserved_quantity is not None:
                item.reserved_quantity = reserved_quantity
            if foil is not None:
                item.foil = foil
            if condition is not None:
                item.condition = normalize_condition(condition)
        else:
            session.delete(item)

        session.commit()

    return RedirectResponse(url=safe_return_to(return_to), status_code=303)


@router.get("/inventory/view", response_class=HTMLResponse)
async def inventory_view(
    request: Request,
    q: str | None = None,
    color: str | None = Query(default=None, pattern="^[WUBRGwubrg]$"),
    rarity: str | None = Query(default=None, pattern="^(common|uncommon|rare|mythic)$"),
    set: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> HTMLResponse:
    q = optional_str(q)
    color = optional_str(color)
    rarity = optional_str(rarity)
    set = optional_str(set)
    rows = await inventory_rows(q=q, color=color, rarity=rarity, set=set, limit=limit)
    return_to = safe_return_to(str(request.url.path) + (f"?{request.url.query}" if request.url.query else ""))

    def selected(value: str | None, expected: str) -> str:
        return " selected" if (value or "").lower() == expected.lower() else ""

    def foil_chip(row: dict[str, object]) -> str:
        return '<span class="chip fallback">Foil</span>' if row["foil"] else '<span class="chip unresolved">Non-foil</span>'

    table_rows = "\n".join(
        f"""
        <tr>
          <td data-label="Name" class="cell-strong">{escape(str(row["name"] or ""))}</td>
          <td data-label="Set">{escape(str(row["set_code"] or ""))}</td>
          <td data-label="No.">{escape(str(row["collector_number"] or ""))}</td>
          <td data-label="Rarity">{escape(str(row["rarity"] or ""))}</td>
          <td data-label="Colors">{escape(str(row["color_identity"] or ""))}</td>
          <td data-label="Qty" class="cell-strong">{escape(str(row["quantity"] or 0))}</td>
          <td data-label="Reserved">{escape(str(row["reserved_quantity"] or 0))}</td>
          <td data-label="Foil">{foil_chip(row)}</td>
          <td data-label="Condition">{escape(str(row["condition"] or "")) or "Unset"}</td>
          <td data-label="Actions" class="actions-cell">
            <form method="post" action="/inventory/update" class="edit-form">
              <input type="hidden" name="scryfall_id" value="{escape(str(row["scryfall_id"] or ""))}">
              <input type="hidden" name="action" value="edit">
              <input type="hidden" name="return_to" value="{escape(return_to)}">
              <label>
                Reserved
                <input class="control" type="number" name="reserved_quantity" min="0" value="{escape(str(row["reserved_quantity"] or 0))}">
              </label>
              <label>
                Foil
                <select class="control" name="foil">
                  <option value="0"{' selected' if not row["foil"] else ''}>No</option>
                  <option value="1"{' selected' if row["foil"] else ''}>Yes</option>
                </select>
              </label>
              <label>
                Condition
                <select class="control" name="condition">
                  <option value=""{selected(str(row["condition"] or ""), "")}>Unset</option>
                  <option value="NM"{selected(str(row["condition"] or ""), "NM")}>NM</option>
                  <option value="LP"{selected(str(row["condition"] or ""), "LP")}>LP</option>
                  <option value="MP"{selected(str(row["condition"] or ""), "MP")}>MP</option>
                  <option value="HP"{selected(str(row["condition"] or ""), "HP")}>HP</option>
                  <option value="DMG"{selected(str(row["condition"] or ""), "DMG")}>DMG</option>
                </select>
              </label>
              <button type="submit" class="button primary small">Save</button>
            </form>
            <div class="row-actions">
              <form method="post" action="/inventory/update">
                <input type="hidden" name="scryfall_id" value="{escape(str(row["scryfall_id"] or ""))}">
                <input type="hidden" name="action" value="increment">
                <input type="hidden" name="return_to" value="{escape(return_to)}">
                <button type="submit" class="button primary small">+</button>
              </form>
              <form method="post" action="/inventory/update">
                <input type="hidden" name="scryfall_id" value="{escape(str(row["scryfall_id"] or ""))}">
                <input type="hidden" name="action" value="decrement">
                <input type="hidden" name="return_to" value="{escape(return_to)}">
                <button type="submit" class="button secondary small">-</button>
              </form>
              <form method="post" action="/inventory/update">
                <input type="hidden" name="scryfall_id" value="{escape(str(row["scryfall_id"] or ""))}">
                <input type="hidden" name="action" value="remove">
                <input type="hidden" name="return_to" value="{escape(return_to)}">
                <button type="submit" class="button danger small">Remove</button>
              </form>
            </div>
          </td>
        </tr>
        """.strip()
        for row in rows
    )

    return HTMLResponse(
        f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MTG Inventory</title>
  <style>
    {APP_SHELL_CSS}
  </style>
</head>
<body>
  <div class="app-shell app-stack">
    <header class="app-header">
      <div class="app-header-inner">
        <div class="app-brand">
          <div class="app-kicker">MTG Scanner</div>
          <p class="app-title">Collection App</p>
          <p class="app-subtitle">Shared mobile-first views for capture, review, and inventory editing.</p>
        </div>
        <nav class="app-nav" aria-label="Primary">
          {render_app_nav("/inventory/view")}
        </nav>
      </div>
    </header>

    <section class="page-hero">
      <div class="page-hero-inner">
        <div class="app-stack">
          <div class="eyebrow">Inventory Workspace</div>
          <h1 class="page-title">Inventory Browser</h1>
          <p class="page-copy">Review your local catalog, filter quickly, and keep all quantity and metadata controls in one consistent app shell.</p>
        </div>
        <aside class="hero-metrics">
          <div class="metric-card">
            <p class="metric-label">Results</p>
            <p class="metric-value">{len(rows)} row(s) shown</p>
          </div>
          <div class="metric-card">
            <p class="metric-label">Backend</p>
            <p class="metric-value">SQLite-backed inventory view</p>
          </div>
        </aside>
      </div>
    </section>

    <section class="app-card">
      <div class="app-card-inner">
        <div class="section-head">
          <h2 class="section-title">Filters</h2>
          <p class="section-copy">Existing query controls are unchanged. This layout just makes them easier to use on a phone.</p>
        </div>
        <form class="toolbar-grid" method="get" action="/inventory/view">
          <label class="field">
            <span class="field-label">Name</span>
            <input class="control" type="text" name="q" placeholder="Name contains" value="{escape(q or "")}">
          </label>
          <label class="field">
            <span class="field-label">Color</span>
            <select class="control" name="color">
              <option value="">Any color</option>
              <option value="W"{selected(color, "W")}>W</option>
              <option value="U"{selected(color, "U")}>U</option>
              <option value="B"{selected(color, "B")}>B</option>
              <option value="R"{selected(color, "R")}>R</option>
              <option value="G"{selected(color, "G")}>G</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">Rarity</span>
            <select class="control" name="rarity">
              <option value="">Any rarity</option>
              <option value="common"{selected(rarity, "common")}>common</option>
              <option value="uncommon"{selected(rarity, "uncommon")}>uncommon</option>
              <option value="rare"{selected(rarity, "rare")}>rare</option>
              <option value="mythic"{selected(rarity, "mythic")}>mythic</option>
            </select>
          </label>
          <label class="field">
            <span class="field-label">Set</span>
            <input class="control" type="text" name="set" placeholder="Set code" value="{escape(set or "")}">
          </label>
          <label class="field">
            <span class="field-label">Limit</span>
            <input class="control" type="number" name="limit" min="1" max="1000" value="{limit}">
          </label>
          <button class="button primary" type="submit">Apply Filters</button>
        </form>
      </div>
    </section>

    <section class="app-card">
      <div class="app-card-inner">
        <div class="section-head">
          <h2 class="section-title">Inventory Rows</h2>
          <p class="section-copy">Rows collapse into stacked cards on narrow screens and stay horizontally scrollable on larger tables when needed.</p>
        </div>
        <div class="meta-bar">
          <span class="chip unresolved">Local inventory</span>
          <span class="chip exact">Inline edits enabled</span>
        </div>
        <div class="table-wrap">
          <table class="inventory-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Set</th>
                <th>No.</th>
                <th>Rarity</th>
                <th>Colors</th>
                <th>Qty</th>
                <th>Reserved</th>
                <th>Foil</th>
                <th>Condition</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {table_rows or '<tr><td data-label="Status" colspan="10" class="empty-state">No inventory rows matched the current filters.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  </div>
</body>
</html>
        """.strip()
    )
