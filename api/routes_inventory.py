from __future__ import annotations

from html import escape

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import Select, select

from db.models import CardPrinting, InventoryItem
from db.repo import SessionLocal

router = APIRouter()

RARITY_OPTIONS = {"common", "uncommon", "rare", "mythic"}
COLOR_OPTIONS = {"W", "U", "B", "R", "G"}


def optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


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


@router.get("/inventory/view", response_class=HTMLResponse)
async def inventory_view(
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

    def selected(value: str | None, expected: str) -> str:
        return " selected" if (value or "").lower() == expected.lower() else ""

    table_rows = "\n".join(
        f"""
        <tr>
          <td>{escape(str(row["name"] or ""))}</td>
          <td>{escape(str(row["set_code"] or ""))}</td>
          <td>{escape(str(row["collector_number"] or ""))}</td>
          <td>{escape(str(row["rarity"] or ""))}</td>
          <td>{escape(str(row["color_identity"] or ""))}</td>
          <td>{escape(str(row["quantity"] or 0))}</td>
          <td>{escape(str(row["reserved_quantity"] or 0))}</td>
          <td>{'yes' if row["foil"] else 'no'}</td>
          <td>{escape(str(row["condition"] or ""))}</td>
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
  <title>Inventory Browser</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f1e8;
      --panel: #fffaf4;
      --ink: #201a14;
      --muted: #6f665b;
      --line: #d7cab8;
      --accent: #1f6b4f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #f8f4ec, var(--bg));
      color: var(--ink);
      padding: 16px;
    }}
    .panel {{
      max-width: 1100px;
      margin: 0 auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 14px 34px rgba(32, 26, 20, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 1.4rem;
    }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .back-link {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    form {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}
    input, select, button {{
      width: 100%;
      padding: 11px 12px;
      border-radius: 10px;
      border: 1px solid var(--line);
      font: inherit;
      background: white;
    }}
    button {{
      background: var(--accent);
      color: white;
      border: 0;
      font-weight: 600;
    }}
    .meta {{
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: white;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #ece3d6;
      text-align: left;
      font-size: 0.95rem;
    }}
    th {{
      background: #f4ede2;
      position: sticky;
      top: 0;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    @media (max-width: 640px) {{
      body {{
        padding: 10px;
      }}
      .panel {{
        padding: 12px;
      }}
      table {{
        min-width: 680px;
      }}
    }}
  </style>
</head>
<body>
  <main class="panel">
    <div class="topbar">
      <div>
        <h1>Inventory Browser</h1>
        <div class="meta">{len(rows)} result(s)</div>
      </div>
      <a class="back-link" href="/phone">Back to /phone</a>
    </div>
    <form method="get" action="/inventory/view">
      <input type="text" name="q" placeholder="Name contains" value="{escape(q or "")}">
      <select name="color">
        <option value="">Any color</option>
        <option value="W"{selected(color, "W")}>W</option>
        <option value="U"{selected(color, "U")}>U</option>
        <option value="B"{selected(color, "B")}>B</option>
        <option value="R"{selected(color, "R")}>R</option>
        <option value="G"{selected(color, "G")}>G</option>
      </select>
      <select name="rarity">
        <option value="">Any rarity</option>
        <option value="common"{selected(rarity, "common")}>common</option>
        <option value="uncommon"{selected(rarity, "uncommon")}>uncommon</option>
        <option value="rare"{selected(rarity, "rare")}>rare</option>
        <option value="mythic"{selected(rarity, "mythic")}>mythic</option>
      </select>
      <input type="text" name="set" placeholder="Set code" value="{escape(set or "")}">
      <input type="number" name="limit" min="1" max="1000" value="{limit}">
      <button type="submit">Filter</button>
    </form>
    <div class="table-wrap">
      <table>
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
          </tr>
        </thead>
        <tbody>
          {table_rows or '<tr><td colspan="9">No inventory rows matched the current filters.</td></tr>'}
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>
        """.strip()
    )
