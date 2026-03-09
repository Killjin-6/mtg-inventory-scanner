import sqlite3
from pathlib import Path

db_path = Path("data/local.sqlite")
print("DB:", db_path.resolve())
if not db_path.exists():
    raise SystemExit(f"DB not found at {db_path.resolve()}")

con = sqlite3.connect(db_path)
cur = con.cursor()

cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity),0) FROM inventory_item;")
rows, copies = cur.fetchone()
print(f"Inventory rows: {rows}, total copies: {copies}")

cur.execute("""
SELECT cp.name, cp.set_code, cp.collector_number, cp.rarity, cp.color_identity,
       ii.quantity, ii.foil, ii.condition
FROM inventory_item ii
JOIN card_printing cp ON cp.id = ii.card_printing_id
ORDER BY ii.id DESC
LIMIT 25;
""")
print("\nLast 25 inventory items:")
for r in cur.fetchall():
    print(r)

cur.execute("SELECT COUNT(*) FROM card_printing;")
catalog_count = cur.fetchone()[0]
print(f"\nCatalog printings in card_printing: {catalog_count}")

con.close()