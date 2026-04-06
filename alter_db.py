import sqlite3

def alter_db():
    conn = sqlite3.connect("atelier.db")
    c = conn.cursor()
    columns_to_add = [
        ("supplier", "VARCHAR"),
        ("supplier_reference", "VARCHAR"),
        ("cost_price", "FLOAT"),
        ("location", "VARCHAR"),
        ("color", "VARCHAR"),
        ("length_per_unit", "FLOAT")
    ]
    for col_name, col_type in columns_to_add:
        try:
            c.execute(f"ALTER TABLE stock_items ADD COLUMN {col_name} {col_type}")
            print(f"Added {col_name}")
        except sqlite3.OperationalError as e:
            print(f"Column {col_name} might already exist: {e}")
    conn.commit()
    conn.close()
    print("Database altered successfully !")

if __name__ == "__main__":
    alter_db()
